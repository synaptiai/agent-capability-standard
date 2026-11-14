/**
 * An in-memory stand-in for a runtime's `ThreadState`, for the tests.
 *
 * It implements the members this example uses with the behaviour the
 * Standard Agent Specification requires of them, and nothing else: the
 * durable key-value store (values round-trip as JSON; `null` deletes), the
 * thread file system, and the message queue. It is not a runtime: no model
 * runs, and hooks and endpoints are called by the tests directly.
 */
import type { QueueMessageInput, ThreadState, ThreadUser } from '@standardagents/spec';

export interface MemoryThread {
  state: ThreadState;
  values: Map<string, string>;
  files: Map<string, string>;
  queued: QueueMessageInput[];
  /** Start a new execution, as when an idle thread runs again. */
  newExecution(): void;
}

export function memoryThread(): MemoryThread {
  const values = new Map<string, string>();
  const files = new Map<string, string>();
  const queued: QueueMessageInput[] = [];

  let flow = 1;
  const implemented = {
    threadId: 'thread-1',
    agentId: 'config_steward',
    userId: 'owner',
    // Only the execution's identity is modelled.
    get execution() {
      return { flowId: `flow-${flow}` };
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

  return {
    state,
    values,
    files,
    queued,
    newExecution: () => {
      flow += 1;
    },
  };
}

export function user(id: string, roles: string[] = []): ThreadUser {
  return { id, username: id, role: 'user', roles };
}
