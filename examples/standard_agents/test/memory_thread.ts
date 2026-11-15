/**
 * An in-memory stand-in for a runtime's `ThreadState`, for the tests.
 *
 * It implements the members this example uses with the behaviour the
 * Standard Agent Specification requires of them, and nothing else: the
 * durable key-value store (values round-trip as JSON; `null` deletes), the
 * thread file system, and the message queue. It is not a runtime: no model
 * runs, and hooks and endpoints are called by the tests directly.
 */
import type { QueueMessageInput, ThreadState, ThreadUser, ToolResult } from '@standardagents/spec';

/** A tool as `invokeTool` runs it: its `execute` with the thread's state. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Invocable = { execute: (state: ThreadState, args: any) => Promise<ToolResult> };

export interface MemoryThread {
  state: ThreadState;
  values: Map<string, string>;
  files: Map<string, string>;
  queued: QueueMessageInput[];
  /** Start a new execution, as when an idle thread runs again. */
  newExecution(): void;
  /** Start the execution's next model step (`stepCount` goes up by one). */
  nextStep(): void;
  /** Leave any execution: `state.execution` is null, as in a thread endpoint. */
  atRest(): void;
  /** The tools `state.invokeTool` can run, by name; a test fills it. */
  tools: Map<string, Invocable>;
  /** What `state.queueTool` was asked to run. */
  queuedTools: { name: string; args: Record<string, unknown> }[];
  /** Each `state.invokeTool` call the runtime received, in order. */
  invoked: { name: string; args: Record<string, unknown> }[];
  /** Awaited before the runtime runs an invoked tool, when a test sets it. */
  beforeInvoke?: (name: string, args: Record<string, unknown>) => Promise<void>;
  /**
   * A second state of the same thread outside any execution, as a thread
   * endpoint or an effect sees it, while the execution goes on.
   */
  endpointState(): ThreadState;
  /**
   * A top-level call of a tool in the current execution, made while another
   * call is awaited: a parallel tool call of the same model step.
   */
  siblingCall(name: string, args: Record<string, unknown>): Promise<ToolResult>;
}

export function memoryThread(): MemoryThread {
  const values = new Map<string, string>();
  const files = new Map<string, string>();
  const queued: QueueMessageInput[] = [];
  const tools = new Map<string, Invocable>();
  const queuedTools: { name: string; args: Record<string, unknown> }[] = [];
  const invoked: { name: string; args: Record<string, unknown> }[] = [];
  // eslint-disable-next-line prefer-const
  let thread: MemoryThread;

  let flow = 1;
  let step = 1;
  let executing = true;
  const implemented = {
    threadId: 'thread-1',
    agentId: 'config_steward',
    userId: 'owner',
    // Only the execution's identity and its model step are modelled.
    get execution() {
      return executing ? { flowId: `flow-${flow}`, stepCount: step } : null;
    },
    getValue: async <T>(key: string): Promise<T | null> => {
      const stored = values.get(key);
      return stored === undefined ? null : (JSON.parse(stored) as T);
    },
    setValue: async (key: string, value: unknown): Promise<void> => {
      if (value === null || value === undefined) values.delete(key);
      else values.set(key, JSON.stringify(value));
    },
    readFile: async (path: string): Promise<ArrayBuffer | null> => {
      const text = files.get(path);
      if (text === undefined) return null;
      const bytes = new TextEncoder().encode(text);
      return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
    },
    writeFile: async (path: string, data: ArrayBuffer | string): Promise<unknown> => {
      files.set(path, typeof data === 'string' ? data : new TextDecoder().decode(data));
      return { path };
    },
    queueMessage: async (message: QueueMessageInput): Promise<void> => {
      queued.push(message);
    },
    // The runtime runs the invoked tool in the same execution, with the
    // thread's state, and waits for it.
    invokeTool: async (name: string, args: Record<string, unknown> = {}): Promise<ToolResult> => {
      invoked.push({ name, args });
      const tool = tools.get(name);
      if (!tool) throw new Error(`memoryThread: no tool '${name}' to invoke`);
      await thread.beforeInvoke?.(name, args);
      return tool.execute(state, args);
    },
    queueTool: (name: string, args: Record<string, unknown> = {}): void => {
      queuedTools.push({ name, args });
    },
  };

  // Any other member is a mistake in a test, so it fails loudly.
  const state = new Proxy(implemented, {
    get(target, property, receiver) {
      if (typeof property === 'string' && !(property in target) && property !== 'then') {
        throw new Error(`memoryThread does not implement ThreadState.${property}`);
      }
      return Reflect.get(target, property, receiver) as unknown;
    },
  }) as unknown as ThreadState;

  // The same thread outside any execution: every member as above, but
  // `execution` is null.
  const endpoint = new Proxy(implemented, {
    get(target, property, receiver) {
      if (property === 'execution') return null;
      return Reflect.get(state as object, property, receiver) as unknown;
    },
  }) as unknown as ThreadState;

  thread = {
    state,
    values,
    files,
    queued,
    tools,
    queuedTools,
    invoked,
    endpointState: () => endpoint,
    siblingCall: async (name: string, args: Record<string, unknown>) => {
      const tool = tools.get(name);
      if (!tool) throw new Error(`memoryThread: no tool '${name}'`);
      return tool.execute(state, args);
    },
    newExecution: () => {
      flow += 1;
      step = 1;
      executing = true;
    },
    nextStep: () => {
      step += 1;
    },
    atRest: () => {
      executing = false;
    },
  };
  return thread;
}

export function user(id: string, roles: string[] = []): ThreadUser {
  return { id, username: id, role: 'user', roles };
}
