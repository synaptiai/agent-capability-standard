/**
 * `groundedTool`: a Standard Agents function tool classified by an Agent
 * Capability Standard capability, with that capability's safety rules
 * enforced inside the tool. `controlTool`: a tool that only signals the
 * host, never refused and always recorded.
 *
 * The binding is a safety layer on a tool-calling host (STANDARD 1.2.0
 * §5.18, class SL in §10.4; its conformance statement is
 * `tests/conformance/calls/statements/standard_agents_binding.json`).
 *
 * The Standard Agent Specification (0.2.0) has no hook that can refuse a
 * tool call before it runs, and tool `annotations` "MUST NOT change argument
 * validation, execution, the tool's results, or what is sent to the model".
 * The one place every conforming runtime runs our code before the side
 * effect is the tool's own `execute`. So the wrapper checks there, and
 * returns an ordinary error result, a §9.8 refusal, when a rule is not met.
 * The annotation only describes the tool (it is a carrier of the tool
 * binding record, §5.18.1); the wrapper is what enforces.
 *
 * Approval is checked before the checkpoint, as in the reference executor
 * (`core/src/exec/machine.rs`), and neither is used up until every check has
 * passed: a call refused for lack of approval leaves the checkpoint valid,
 * and one refused for lack of a checkpoint leaves the approval unused.
 *
 * A checkpoint authorises a call only in the execution it was taken in, and
 * only for a few minutes, so the restore point is taken after the approval
 * arrives, just before the change. The time limit is the rule the binding
 * guarantees: the specification calls `flowId` the "Unique execution ID" and
 * does not say when it changes (see `flowOf` in records.ts). A call made
 * outside an execution, from an endpoint or an effect, has no `flowId`, and
 * neither a checkpoint nor an approval authorises it: the runtime runs one
 * execution of a thread at a time, and nothing else (see serial.ts).
 *
 * A composite (a tool that calls other tools with `state.invokeTool`) lists
 * the tools it may call in `invokes` (§5.18.4). Each invocation issues a
 * one-shot nesting token; the invoked grounded tool is covered by the
 * composite's approval and checkpoint only if it takes a token that matches
 * its execution, its name and its arguments. Same thread or execution is not
 * evidence that the composite's own code made the call.
 */
import {
  defineTool,
  type ThreadState,
  type ToolArgs,
  type ToolDefinition,
  type ToolResult,
  type UsesAwareExecute,
  type VariableDefinition,
} from '@standardagents/spec';
import type { z } from 'zod';
import {
  approvalRound,
  approvalState,
  consumeApproval,
  countedDecisions,
  policyProblems,
  principalOf,
  requestApproval,
  type ApprovalPolicy,
} from './approval.js';
import {
  allowed,
  annotationRecord,
  CapabilityOutputError,
  checkBindings,
  checkGrounding,
  digest as digestOf,
  encodeCapabilityOutput,
  groundingPolicies,
  holdsCredential,
  iJsonProblem,
  joinFlags,
  type GroundingPolicy,
  type Json,
} from '@synaptiai/acs-core';
import { notifyEvidence } from './evidence.js';
import { destinationPolicies } from './layer.js';
import { confidenceFailure, type BindingProfiles } from './profiles.js';
import {
  CAPABILITIES,
  ONTOLOGY_VERSION,
  STANDARD_VERSION,
  effectiveFlagsOf,
  prerequisitesOf,
  type CapabilityId,
  type CapabilityOutput,
  type DeclaredFlags,
  type Layer,
  type SafetyFlags,
} from './ontology.js';
import {
  CODE_NAMES,
  KEYS,
  appendTrace,
  completeTrace,
  flowOf,
  readCheckpoints,
  readExecuted,
  stepOf,
  type AgentIdentity,
  type CheckpointRecord,
  type Diagnostic,
  type ApprovalRecord,
  type RecordedBy,
  type RefusalCode,
  type TraceEntry,
} from './records.js';
import { serially } from './serial.js';

/** The key this binding owns in a tool's `annotations`. */
export const ANNOTATION_KEY = 'acs';

/** The binding's name, as every record it writes names the layer (§5.18.8). */
export const LAYER_NAME = '@acs/standard-agents-binding';

/**
 * What `annotations.acs` holds: the tool binding record of the tool
 * (`tool`, `ontology`, `capability`, and the declared members), the
 * Standard it cites, and informative copies of its layer and effective
 * flags. `schemas/interop/standard_agents_annotation.schema.json` is the
 * schema; a layer reads the record and ignores the copies (§5.18.1).
 */
export interface AcsAnnotation extends SafetyFlags {
  standard: string;
  ontology: string;
  /** The name the tool states for itself: what an approver is shown. */
  tool?: string;
  capability: CapabilityId;
  layer: Layer;
  domain?: string;
  /** The flags the tool declared (§5.2.1). */
  flags?: DeclaredFlags;
  additional_capabilities?: CapabilityId[];
  invokes?: string[];
  approval?: { min_approvers?: number; role?: string; expires?: string };
}

/** What `annotations.acs` holds for a control-only tool (§5.18.3). */
export interface AcsControlAnnotation {
  standard: string;
  ontology: string;
  tool: string;
  control: true;
}

/** What the wrapper tells the tool about this call. */
export interface GroundedCall {
  /** The trace sequence number this call will be recorded under. */
  seq: number;
  /** The checkpoint this call used, when the capability requires one. */
  checkpoint_id?: string;
  /**
   * The approvers who approved this call, as principals (`sa-user:<id>`),
   * when the capability requires approval.
   */
  approvers?: string[];
  /** The composite call that covered this one, when it is a nested call (§5.18.4). */
  covered_by?: number;
}

export interface GroundedToolOptions<C extends CapabilityId, Args extends ToolArgs> {
  /**
   * The tool's name, as the runtime knows it (its file name). A tool cannot
   * see its own name at run time, and the name is part of what an approver
   * approves, so it is stated here.
   */
  name: string;
  /** The ontology capability this tool performs: its primary one. */
  capability: C;
  /**
   * Other capabilities the same call performs (§5.18.3): the call takes the
   * strictest flags and every prerequisite of all of them.
   */
  additional_capabilities?: CapabilityId[];
  /** The capability's domain parameter, e.g. `config` or `email`. */
  domain?: string;
  /**
   * Flags stricter than the capability's. A weaker one is W602, which fails
   * the definition here, as warnings do in strict validation.
   */
  flags?: DeclaredFlags;
  /** Who may approve and for how long, when the tool needs approval. */
  approval?: ApprovalPolicy;
  /**
   * The tools this tool may call with `state.invokeTool` while it runs, by
   * the name the runtime knows them under (§5.18.4). The tool takes their
   * flags, transitively; a call it makes to a tool not listed is refused
   * with F504, and a tool with no `invokes` may invoke none.
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  invokes?: Record<string, ToolDefinition<ThreadState, any>>;
  description: string;
  args: Args;
  variables?: VariableDefinition[];
  progressArgument?: string;
  /** Other owners' annotation keys. The `acs` key is set by the wrapper. */
  annotations?: Record<string, unknown>;
  /**
   * How long a checkpoint can authorise this tool's call, in milliseconds:
   * more than zero and at most `CHECKPOINT_MAX_AGE_MS`, the default. Only
   * for a tool that requires one.
   */
  checkpoint_max_age_ms?: number;
  /** Milliseconds since the Unix epoch; defaults to `Date.now`. */
  now?: () => number;
  /**
   * Grounding policies (STANDARD 1.2.0 §5.20) this layer applies to the
   * tool's outputs: when a policy requires the tool's capability, an output
   * that is neither grounded nor marked inferred is refused with F505 (the
   * call has run; its trace entry is `failed`). Checked when the tool is
   * defined: a capability the ontology does not define throws (V101).
   * Without this option the output check is 1.1's: the contract's required
   * fields, `evidence_anchors` an array, and a required `confidence` from 0
   * to 1.
   */
  grounding?: GroundingPolicy | readonly GroundingPolicy[];
  /**
   * Domain profiles (STANDARD 1.2.0 §5.21) this layer applies to the tool's
   * calls, as the core computed them (`bindingProfiles`): they raise the
   * flags of each of the tool's capabilities at the call's effective risk
   * (with `invokes`), and of each capability the tools it invokes perform,
   * transitively, at theirs (its approval covers their nested calls); a
   * call they require a person for counts only
   * approvals the deployment attests as a person's
   * (`approver_identity.kind: human`), and its trace entries carry
   * `person_required`. A composite that invokes such a tool needs a
   * person's approval too, as its approval covers the nested call; a nested
   * call needing a person that a composite without one makes is checked as
   * a call of its own. Their grounding policies join `grounding`; and an
   * output below their minimum confidence, or whose `confidence` is not a
   * number from 0 to 1, fails with F504 (the call has run). Their
   * `allowed_destinations` join the layer's destination policies for this
   * tool's `send` calls (§4.4.2; see `configureLayer`) and, for a
   * composite, for the sends its code invokes at any depth: each nested
   * call the binding attributes to it (§5.18.4).
   */
  profiles?: BindingProfiles;
  /**
   * For a tool whose capabilities include `send`: where a call's
   * destination is, `args => args.to` (default: `args.destination`). It
   * only says where to look: the destination policies in force are the
   * layer's (`configureLayer`) and the profiles', and a `send` tool
   * defined without this option obeys them too (STANDARD 1.2.0 §4.4.2).
   * A tool that does not perform `send` throws when defined with it.
   */
  destination?: (args: Record<string, unknown>) => unknown;
  /**
   * What the call's producer had (`evidence_seen`, §5.20): only what this
   * call received (`refsIn(args)`) and what the tool's own code read during
   * `execute` (the file it read and cites). Never a stored trace or history:
   * a ref there was seen by an earlier request, not by this one. Without it,
   * the layer attests nothing.
   */
  seen?: (call: { state: ThreadState; args: z.infer<Args>; output: CapabilityOutput<C> }) =>
    | readonly string[]
    | Promise<readonly string[]>;
  /**
   * The host's own secrets (§6.7), registered with the redactor that every
   * trace entry this tool writes passes through. The default patterns
   * apply whether or not this is given.
   */
  secrets?: readonly string[] | ((state: ThreadState) => Promise<readonly string[]>);
  /**
   * Do the work and return the capability's output: every field the
   * ontology requires, including `evidence_anchors`. Throw to fail.
   */
  execute: (state: ThreadState, args: z.infer<Args>, call: GroundedCall) => Promise<CapabilityOutput<C>>;
}

/** How long a checkpoint can authorise a call, unless the tool says otherwise: ten minutes. */
export const CHECKPOINT_MAX_AGE_MS = 10 * 60 * 1000;

/** The flags of an unbound tool (§5.18.2): the strictest case. */
const STRICTEST: SafetyFlags = { risk: 'high', mutation: true, requires_checkpoint: true, requires_approval: true };

function refusal(
  code: RefusalCode,
  tool: string,
  capability: CapabilityId | null,
  message: string,
  suggestion: string,
  extra: Record<string, Json> = {},
): ToolResult {
  const diagnostic: Diagnostic = {
    code,
    name: CODE_NAMES[code],
    severity: 'error',
    message,
    location: { tool, ...(capability !== null ? { capability } : {}) },
    suggestion,
  };
  return {
    status: 'error',
    error: `${code} ${CODE_NAMES[code]}: ${message} ${suggestion}`,
    error_code: code,
    error_data: { ...diagnostic, ...extra },
  };
}

/** The name each tool defined here states for itself; see `statedName`. */
const STATED_NAMES = new WeakMap<object, string>();

/** The effective flags each tool defined here computed for itself. */
const EFFECTIVE = new WeakMap<object, SafetyFlags>();

/**
 * The tools defined here whose calls an applied domain profile requires a
 * person for (§5.21.3), directly or through a tool they invoke: a
 * composite's approval covers its nested calls (§5.18.4), so it must be a
 * person's whenever one of them needs a person's.
 */
const PERSON = new WeakSet<object>();

/** A capability a call performs, at the call's effective risk R (§5.21.3). */
interface Performed {
  capability: CapabilityId;
  risk: SafetyFlags['risk'];
}

/**
 * What each tool defined here performs: its capabilities at its effective
 * risk, and what the tools it invokes perform, transitively. Profiles given
 * to a composite govern the nested calls its approval covers (§5.21.3,
 * §5.18.4), so they raise its flags for each of these as they would raise
 * the nested call's own.
 */
const PERFORMS = new WeakMap<object, readonly Performed[]>();

/**
 * What each name a tool defined here states for itself is bound to: its
 * capability, or `control`; `null` once two definitions of the name
 * disagree. A refusal that knows a tool only by name (a composite's call to
 * a tool it does not list) names the capability from here (§5.18.8: only an
 * unbound tool's refusal has none).
 */
const BOUND_NAMES = new Map<string, CapabilityId | 'control' | null>();

function noteBound(name: string, as: CapabilityId | 'control'): void {
  const known = BOUND_NAMES.get(name);
  BOUND_NAMES.set(name, known === undefined || known === as ? as : null);
}

/**
 * The name a tool defined with `groundedTool` or `controlTool` states for
 * itself: what an approver is shown and the trace records. A tool cannot
 * see the name it is registered under, so `lintPromptTools` compares the
 * two.
 */
export function statedName(tool: object): string | undefined {
  return STATED_NAMES.get(tool);
}

/**
 * The effective flags of a tool another tool invokes (§5.18.4): those a
 * grounded or control tool computed for itself, else those of its `acs`
 * annotation read as a binding record (copies ignored), else, for a tool
 * with no annotation or one that does not load, the strictest case.
 */
function invokedFlags(name: string, tool: object & { annotations?: Record<string, unknown> }): SafetyFlags {
  const computed = EFFECTIVE.get(tool);
  if (computed) return computed;
  const record = annotationRecord(name, tool.annotations?.[ANNOTATION_KEY]);
  if (!record) return STRICTEST;
  const loaded = checkBindings([record]).effective[name];
  return loaded
    ? {
        risk: loaded.risk,
        mutation: loaded.mutation,
        requires_checkpoint: loaded.requires_checkpoint,
        requires_approval: loaded.requires_approval,
      }
    : STRICTEST;
}

/**
 * What a tool another tool invokes performs (§5.18.4): what a grounded or
 * control tool noted for itself, else the capabilities of its `acs`
 * annotation read as a binding record, at its effective risk, else, for a
 * tool with no annotation or one that does not load, `mutate` at high risk,
 * as which an unbound tool is treated (§5.18.2).
 */
function invokedPerforms(
  name: string,
  tool: object & { annotations?: Record<string, unknown> },
): readonly Performed[] {
  const computed = PERFORMS.get(tool);
  if (computed) return computed;
  const record = annotationRecord(name, tool.annotations?.[ANNOTATION_KEY]);
  const loaded = record ? checkBindings([record]).effective[name] : undefined;
  if (!loaded) return [{ capability: 'mutate', risk: 'high' }];
  return (loaded.capabilities as CapabilityId[]).map((capability) => ({ capability, risk: loaded.risk }));
}

/**
 * One invocation of a listed tool by a running composite: a one-shot token
 * the invoked tool takes to be covered (§5.18.4).
 */
interface NestingToken {
  composite: string;
  seq: number;
  /** The composite's approval counted only a person's decisions (§5.21.3). */
  person: boolean;
  /**
   * The destination policies of the profiles given to the composite and to
   * every composite enclosing it (§4.4.2, §5.21.3): a nested send is checked
   * against them too.
   */
  destinations: readonly (readonly string[])[];
  flow: string;
  tool: string;
  digest: string;
  used: boolean;
}

/** The pending invocations of each thread. */
const TOKENS = new Map<string, NestingToken[]>();

/**
 * The token of a pending invocation that matches this call, if any; taking
 * it (`used`) is the caller's, once the checks that precede coverage passed.
 */
function findToken(thread: string, flow: string | null, tool: string, argsDigest: string): NestingToken | undefined {
  if (flow === null) return undefined;
  return (TOKENS.get(thread) ?? []).find(
    (t) => !t.used && t.flow === flow && t.tool === tool && t.digest === argsDigest,
  );
}

/**
 * The state a composite's own code gets: the runtime's state, with an
 * `invokeTool` that refuses a tool the composite does not list (F504) and
 * issues a nesting token for one it does.
 */
function nestingState(
  state: ThreadState,
  composite: {
    name: string;
    seq: number;
    person: boolean;
    destinations: readonly (readonly string[])[];
    flow: string | null;
    invokes: readonly string[];
    recorded_by: RecordedBy;
    now: () => number;
  },
  record: (entry: Omit<TraceEntry, 'seq'>) => Promise<unknown>,
): ThreadState {
  const invokeTool = async (tool: string, args: Record<string, unknown> = {}): Promise<ToolResult> => {
    if (!composite.invokes.includes(tool)) {
      const bound = BOUND_NAMES.get(tool) ?? null;
      const capability = bound === null || bound === 'control' ? null : bound;
      const message = `${composite.name} does not list ${tool} in invokes.`;
      const result = refusal('F504', tool, capability, message, `Add ${tool} to the invokes of ${composite.name}.`);
      await record({
        at: composite.now(),
        action: tool,
        capability,
        ...(bound === 'control' ? { control: true as const } : {}),
        status: 'refused',
        code: 'F504',
        covered_by: composite.seq,
        recorded_by: composite.recorded_by,
        error: result.error ?? message,
      }).catch(() => undefined);
      return result;
    }
    if (composite.flow === null) return state.invokeTool(tool, args);
    const token: NestingToken = {
      composite: composite.name,
      seq: composite.seq,
      person: composite.person,
      destinations: composite.destinations,
      flow: composite.flow,
      tool,
      digest: await digestOf(args as Json),
      used: false,
    };
    const pending = TOKENS.get(state.threadId) ?? [];
    pending.push(token);
    TOKENS.set(state.threadId, pending);
    try {
      return await state.invokeTool(tool, args);
    } finally {
      const list = TOKENS.get(state.threadId) ?? [];
      const at = list.indexOf(token);
      if (at >= 0) list.splice(at, 1);
      if (list.length === 0) TOKENS.delete(state.threadId);
    }
  };
  return new Proxy(state, {
    get(target, property) {
      if (property === 'invokeTool') return invokeTool;
      const value = Reflect.get(target, property, target) as unknown;
      return typeof value === 'function' ? (value as (...a: unknown[]) => unknown).bind(target) : value;
    },
  });
}

/** What the checks before a call decided. */
type Claim =
  | { outcome: ToolResult }
  | {
      outcome?: undefined;
      started: TraceEntry;
      call: GroundedCall;
      flow: string | null;
      recorded_by: RecordedBy;
      /** The destination policies enclosing composites' profiles put in force for this call. */
      enclosing: readonly (readonly string[])[];
    };

/** The duration text (§5.10.1) of a policy's expiry, in its largest exact unit, for the annotation. */
function durationText(ms: number): string {
  const whole = Math.ceil(ms);
  for (const [unit, size] of [
    ['d', 86_400_000],
    ['h', 3_600_000],
    ['m', 60_000],
    ['s', 1_000],
  ] as const) {
    if (whole % size === 0) return `${whole / size}${unit}`;
  }
  return `${whole}ms`;
}

/**
 * Define a function tool that performs one ontology capability (and any
 * additional ones) and enforces their effective safety flags and `requires`
 * edges before it runs.
 */
export function groundedTool<C extends CapabilityId, Args extends ToolArgs>(
  options: GroundedToolOptions<C, Args>,
): ToolDefinition<ThreadState, Args> {
  const { name, capability, domain } = options;
  const additional = options.additional_capabilities ?? [];
  const capabilities: CapabilityId[] = [capability, ...additional];
  const own = effectiveFlagsOf(capabilities, options.flags);
  if (own.warnings.length > 0) {
    throw new Error(`groundedTool '${name}': ${own.warnings.join('; ')}; a tool definition may not declare weaker flags`);
  }
  const invokes = options.invokes ?? {};
  const invokeNames = Object.keys(invokes);
  let flags = own.flags;
  // Whether an applied profile requires a person for the call (§5.21.3).
  // A composite needs one when a tool it invokes does: its approval covers
  // that tool's nested calls (§5.18.4).
  let person = false;
  // What the nested calls the composite's approval covers perform.
  const nested: Performed[] = [];
  for (const [invoked, tool] of Object.entries(invokes)) {
    flags = joinFlags(flags, invokedFlags(invoked, tool));
    person ||= PERSON.has(tool);
    nested.push(...invokedPerforms(invoked, tool));
  }
  const risk = flags.risk;
  // Domain profiles (§5.21.3): the flags they raise for each capability at
  // the call's effective risk R before profiles, which includes its other
  // capabilities and the tools it invokes (§5.18.3, §5.18.4); and, since a
  // composite's effective flags include those of each tool it lists, those
  // they raise for what its nested calls perform, at their own R (so
  // `block_autonomous` given to a composite alone reaches them).
  const profiles = options.profiles;
  if (profiles !== undefined) {
    const raise = (c: CapabilityId, declared: DeclaredFlags): void => {
      const raised = profiles.flags(c, declared);
      flags = joinFlags(flags, {
        risk: raised.risk,
        mutation: raised.mutation,
        requires_checkpoint: raised.requires_checkpoint,
        requires_approval: raised.requires_approval,
      });
      person ||= raised.person;
    };
    for (const c of capabilities) raise(c, { ...options.flags, risk });
    for (const performed of nested) raise(performed.capability, { risk: performed.risk });
  }
  const minimumConfidence = profiles?.policy.minimum_confidence ?? null;
  const policy = options.approval ?? {};
  const problems = policyProblems(policy);
  if (problems.length > 0) {
    throw new Error(`groundedTool '${name}': ${problems.join('; ')} (STANDARD 1.2.0 §5.14)`);
  }
  const maxAge = options.checkpoint_max_age_ms ?? CHECKPOINT_MAX_AGE_MS;
  if (!(maxAge > 0 && maxAge <= CHECKPOINT_MAX_AGE_MS)) {
    throw new Error(
      `groundedTool '${name}': checkpoint_max_age_ms must be more than zero and at most ${CHECKPOINT_MAX_AGE_MS}, not ${maxAge}`,
    );
  }
  const now = options.now ?? (() => Date.now());
  const prerequisites = prerequisitesOf(capabilities);
  // Grounding policies, checked once (§5.20): an unknown id throws here.
  // The applied profiles' grounding policies join the tool's own (§5.21.3).
  const fromProfiles: GroundingPolicy[] = (profiles?.policy.grounding ?? []).map((g) => ({
    require: g.require as CapabilityId[],
    ...(g.kinds !== null ? { kinds: g.kinds } : {}),
  }));
  const policies = [
    ...(options.grounding === undefined ? [] : groundingPolicies(options.grounding)),
    ...(fromProfiles.length > 0 ? groundingPolicies(fromProfiles) : []),
  ].filter((p) => p.require.includes(capability));
  const secretsOf = async (state: ThreadState): Promise<readonly string[]> => {
    const given = options.secrets;
    return typeof given === 'function' ? await given(state) : (given ?? []);
  };
  // persist data and audit records holding a secret are refused (§5.18.10).
  const holdsRecords = capabilities.includes('persist') || capabilities.includes('audit');
  // A send call's destination is checked against the policies in force
  // (§4.4.2, §5.18.10): the layer's and the applied profiles'.
  const sends = capabilities.includes('send');
  if (options.destination !== undefined && !sends) {
    throw new Error(
      `groundedTool '${name}': the destination option is for a tool that performs send, and ${capabilities.join(', ')} is not (STANDARD 1.2.0 §4.4.2)`,
    );
  }
  const destinationOf = options.destination ?? ((args: Record<string, unknown>) => args['destination']);
  const profileDestinations = profiles?.policy.destinations ?? [];

  const annotation: AcsAnnotation = {
    standard: STANDARD_VERSION,
    ontology: ONTOLOGY_VERSION,
    tool: name,
    capability,
    layer: CAPABILITIES[capability].layer,
    ...(domain !== undefined ? { domain } : {}),
    ...(options.flags !== undefined && Object.keys(options.flags).length > 0 ? { flags: options.flags } : {}),
    ...(additional.length > 0 ? { additional_capabilities: additional } : {}),
    ...(invokeNames.length > 0 ? { invokes: invokeNames } : {}),
    ...(options.approval !== undefined && Object.keys(options.approval).length > 0
      ? {
          approval: {
            ...(policy.min_approvers !== undefined ? { min_approvers: policy.min_approvers } : {}),
            ...(policy.role !== undefined ? { role: policy.role } : {}),
            ...(policy.expires_ms !== undefined ? { expires: durationText(policy.expires_ms) } : {}),
          },
        }
      : {}),
    ...flags,
  };

  // What decides this tool's calls (§5.18.8): its binding record and the
  // checkpoint maximum age, which the annotation does not state.
  const configuration = {
    annotation,
    settings: {
      checkpoint_max_age_ms: maxAge,
      ...(profiles !== undefined ? { profiles: profiles.documents } : {}),
    },
  };
  let layer: Promise<RecordedBy> | undefined;
  const recordedBy = (): Promise<RecordedBy> =>
    (layer ??= digestOf(configuration as unknown as Json).then((config_sha256) => ({
      name: LAYER_NAME,
      version: STANDARD_VERSION,
      config_sha256,
    })));

  /**
   * Everything before the tool's own code runs: the checks, then using up
   * what the call needs, then the `started` entry. It runs under `serially`,
   * so two calls in this realm cannot both pass on one approval or one
   * checkpoint, and taking a nesting token is atomic with the other checks.
   */
  const check = async (state: ThreadState, argsJson: Json, secrets: readonly string[]): Promise<Claim> => {
    const flow = flowOf(state);
    const step = stepOf(state);
    const position = { ...(flow !== null ? { flow_id: flow } : {}), ...(step !== null ? { step } : {}) };
    const identity = {
      action: name,
      capability,
      ...(domain !== undefined ? { domain } : {}),
      ...position,
      // An applied profile requires a person for the call (§5.21.3).
      ...(person ? { person_required: true as const } : {}),
    };
    // What is known of the call so far, for the record if a write fails.
    const used: Pick<TraceEntry, 'args_digest' | 'approval' | 'checkpoint_id' | 'covered_by'> = {};
    let layerRecord: RecordedBy | undefined;
    try {
      const recorded_by = await recordedBy();
      layerRecord = recorded_by;
      // §5.18.7: no decision can bind to arguments that are not I-JSON
      // (§5.14), so a call that needs approval with such arguments is
      // refused with F502, not left to fail as the layer's own error.
      const argsProblem = flags.requires_approval ? iJsonProblem(argsJson) : null;
      try {
        used.args_digest = await digestOf(argsJson);
      } catch (cause) {
        if (argsProblem === null) throw cause;
      }
      const base = {
        ...identity,
        ...(used.args_digest !== undefined ? { args_digest: used.args_digest } : {}),
        recorded_by,
      };
      const refuse = async (result: ToolResult, code: RefusalCode): Promise<Claim> => {
        await appendTrace(
          state,
          {
            ...base,
            ...(used.covered_by !== undefined ? { covered_by: used.covered_by } : {}),
            at: now(),
            status: 'refused',
            code,
            error: result.error ?? code,
          },
          secrets,
        );
        return { outcome: result };
      };

      // Data a persist call would store, or a record an audit call would
      // append, that holds a secret is refused, not redacted: memory is read
      // back as fact (§5.18.10, §6.7).
      if (holdsRecords && holdsCredential(argsJson, secrets)) {
        return await refuse(
          refusal(
            'F504',
            name,
            capability,
            `The ${capabilities.includes('persist') ? 'data this call would store' : 'record this call would append'} holds what looks like a credential (STANDARD 1.2.0 §6.7).`,
            'Store where the secret is kept, or cite it by reference or digest, not the secret itself.',
          ),
          'F504',
        );
      }

      // The pending invocation of a running composite this call is, if any
      // (§5.18.4): the destination policies of the profiles given to it and
      // to the composites enclosing it reach this call (§5.21.3).
      const token = used.args_digest === undefined ? undefined : findToken(state.threadId, flow, name, used.args_digest);
      const enclosing = token?.destinations ?? [];

      // A send whose destination a policy in force does not allow, or
      // whose destination is not a string, is refused before approval and
      // the checkpoint (§4.4.2, §5.18.10): the layer's, the tool's profiles'
      // and those of the profiles of every composite enclosing the call.
      // The destination is not repeated: it is in the call's arguments
      // (§6.7).
      if (sends) {
        const policies = [...destinationPolicies(), ...profileDestinations, ...enclosing];
        if (policies.length > 0) {
          const args = typeof argsJson === 'object' && argsJson !== null && !Array.isArray(argsJson) ? argsJson : {};
          const destination = destinationOf(args as Record<string, unknown>);
          if (typeof destination !== 'string' || !allowed(policies, destination)) {
            return await refuse(
              refusal(
                'F504',
                name,
                capability,
                typeof destination === 'string'
                  ? "This call's destination is not one the destination policies in force allow."
                  : "This call's destination is not a string, so no destination policy in force can allow it.",
                'Send only to an allowed destination (STANDARD 1.2.0 §4.4.2).',
              ),
              'F504',
            );
          }
        }
      }

      // A nested call the running composite's own code made, with these
      // exact arguments in this execution, is covered by the composite's
      // approval and checkpoint (§5.18.4): only those two checks are skipped.
      // A call a profile requires a person for is covered only by a
      // composite whose approval a person gave (§5.21.3); otherwise it is
      // checked as a call of its own. Each invocation covers at most one
      // call: the token is taken here, synchronously after it was found.
      if (token !== undefined) token.used = true;
      const covered = token !== undefined && (token.person || !person);
      if (covered) used.covered_by = token.seq;

      // 1. Approval, bound to the digest of exactly what is about to run.
      let request: ApprovalRecord | undefined;
      // When the request was found approved: the approvals that counted then
      // are the ones the call's record lists.
      let approvedAt = 0;
      if (flags.requires_approval && !covered) {
        if (argsProblem !== null) {
          return await refuse(
            refusal(
              'F502',
              name,
              capability,
              `The arguments of ${name} are not I-JSON (STANDARD 1.2.0 §5.14), so no decision can bind to them: the value ${argsProblem}.`,
              'Call the tool again with arguments that are I-JSON: integers within ±2^53, strings with no lone surrogate.',
            ),
            'F502',
          );
        }
        if (flow === null) {
          return await refuse(
            refusal(
              'F502',
              name,
              capability,
              'This call is not part of an execution, and an approval authorises only a call made in one, where the runtime runs one call at a time.',
              `Call ${name} from a tool call in an execution.`,
            ),
            'F502',
          );
        }
        const shown: Json[] = [{ action: name, capability, args: argsJson }];
        approvedAt = now();
        request = await requestApproval(state, shown, policy, approvedAt);
        let standing = approvalState(request, approvedAt);
        // A person must decide (§5.21.3): only approvals the deployment
        // attests as a person's count.
        if (standing === 'approved' && person) {
          const people = countedDecisions(request, approvedAt).filter((d) => d.approver_identity?.kind === 'human');
          if (new Set(people.map((d) => d.approver)).size < request.min_approvers) standing = 'pending';
        }
        if (standing !== 'approved') {
          return await refuse(
            refusal(
              'F502',
              name,
              capability,
              person
                ? `This call needs a person's approval (an applied domain profile requires one, STANDARD 1.2.0 §5.21.3: only approvals the deployment attests as a person's count), and the request is ${standing}.`
                : `This call needs approval and the request is ${standing}.`,
              'Tell the person what you intend to do and wait for them to decide; then call the tool again with the same arguments.',
              { digest: request.digest, round: approvalRound(request), shown, state: standing },
            ),
            'F502',
          );
        }
      }

      // 2. `requires` edges: each prerequisite capability must have run.
      // A missing checkpoint is F501 (F503 for a rollback); any other
      // prerequisite V102 (§5.18.5).
      const executed = await readExecuted(state);
      for (const needed of prerequisites) {
        if (!executed[needed]) {
          const code: RefusalCode =
            needed !== 'checkpoint' ? 'V102' : capabilities.includes('rollback') ? 'F503' : 'F501';
          return await refuse(
            refusal(
              code,
              name,
              capability,
              `'${capability}' requires '${needed}' to have run first in this thread.`,
              `Call a '${needed}' tool, then call ${name} again.`,
            ),
            code,
          );
        }
      }

      // 3. A valid checkpoint for this call alone, taken in this execution and
      // not long ago.
      const needsCheckpoint = flags.requires_checkpoint && !covered;
      const checkpoints = needsCheckpoint ? await readCheckpoints(state) : [];
      const unused = [...checkpoints].reverse().filter((c) => c.valid);
      const at = now();
      const checkpoint =
        flow === null ? undefined : unused.find((c) => c.flow_id === flow && at - c.at <= maxAge);
      if (needsCheckpoint && !checkpoint) {
        const message =
          flow === null
            ? 'This call is not part of an execution, and a checkpoint authorises a call only in the execution it was taken in.'
            : unused.some((c) => c.flow_id === flow)
              ? 'The last checkpoint was taken too long ago, and what it saved may have changed since.'
              : unused.length > 0
                ? 'The last checkpoint was taken before this thread last went idle, and what it saved may have changed since.'
                : 'Every earlier checkpoint has been used; each call that requires a checkpoint needs its own.';
        return await refuse(
          refusal(
            'F501',
            name,
            capability,
            message,
            flow === null
              ? `Call ${name} from a tool call, after a 'checkpoint' tool in the same execution.`
              : `Call a 'checkpoint' tool, then call ${name} again.`,
          ),
          'F501',
        );
      }

      // Every check has passed. Only now are the approval and the checkpoint
      // used up, so a call refused above leaves both as they were.
      let approvers: string[] | undefined;
      if (request) {
        // The approvers that counted (§5.17): those whose approvals made
        // the request approved, as principals, with their identities when
        // every one of those decisions recorded one. One decision per
        // approver, so identities never disagree for one principal.
        // Under a person requirement, a person's approvals only (§5.21.3).
        const counted = countedDecisions(request, approvedAt).filter(
          (d) => !person || d.approver_identity?.kind === 'human',
        );
        approvers = [...new Set(counted.map((d) => principalOf(d.approver)))];
        const identities = new Map<string, AgentIdentity>();
        for (const d of counted) {
          if (d.approver_identity) identities.set(d.approver_identity.principal, d.approver_identity);
        }
        const attested = counted.every((d) => d.approver_identity !== undefined);
        used.approval = {
          digest: request.digest,
          approvers,
          ...(attested ? { approver_identities: [...identities.values()] } : {}),
          decision_ids: counted.map((d) => d.decision_id),
        };
        // A rejection recorded since the request was read stops the call;
        // the checkpoint is not touched.
        if (await consumeApproval(state, request, now())) {
          delete used.approval;
          return await refuse(
            refusal(
              'F502',
              name,
              capability,
              'The request was rejected while this call was starting.',
              'Tell the person what you intend to do and wait for them to decide; then call the tool again with the same arguments.',
              { digest: request.digest, round: approvalRound(request), state: 'rejected' },
            ),
            'F502',
          );
        }
      }
      if (checkpoint) {
        used.checkpoint_id = checkpoint.id;
        await state.setValue(
          KEYS.checkpoints,
          checkpoints.map((c): CheckpointRecord => (c.id === checkpoint.id ? { ...c, valid: false } : c)),
        );
      }

      // 4. Record that the call is starting. The entry is written before the
      // tool's own code runs, so that a call cut off while it runs still
      // leaves a record of what it used.
      const started = await appendTrace(state, { ...base, ...used, at: now(), status: 'started' }, secrets);
      return {
        started,
        flow,
        recorded_by,
        enclosing,
        call: {
          seq: started.seq,
          ...(used.checkpoint_id !== undefined ? { checkpoint_id: used.checkpoint_id } : {}),
          ...(approvers !== undefined ? { approvers } : {}),
          ...(used.covered_by !== undefined ? { covered_by: used.covered_by } : {}),
        },
      };
    } catch (cause) {
      // A write failed, or the arguments of a call that needs no approval
      // have no canonical JSON: the layer could not complete its checks, so
      // the call is refused (R407, §5.18.8). Record what the call used, so
      // no approval or checkpoint is spent without a trace entry; if the
      // store refuses that too, there is nothing more to do.
      const message = cause instanceof Error ? cause.message : String(cause);
      await appendTrace(
        state,
        {
          ...identity,
          ...used,
          ...(layerRecord !== undefined ? { recorded_by: layerRecord } : {}),
          at: now(),
          status: 'failed',
          code: 'R407',
          error: message,
        },
        secrets,
      ).catch(() => undefined);
      return {
        outcome: refusal(
          'R407',
          name,
          capability,
          `The safety checks of this call could not be completed: ${message}.`,
          'The call did not run.',
        ),
      };
    }
  };

  const execute = async (state: ThreadState, args: z.infer<Args>): Promise<ToolResult> => {
    let secrets: readonly string[];
    try {
      secrets = await secretsOf(state);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      return refusal('R407', name, capability, `The host's secrets could not be read: ${message}.`, 'The call did not run.');
    }
    const claim = await serially(state.threadId, () => check(state, args as Json, secrets));
    if (claim.outcome) return claim.outcome;
    const { started, call, flow, recorded_by, enclosing } = claim;

    // Run with the nesting state, check the output contract (§5.18.9),
    // record the outcome.
    let text: string;
    let output: CapabilityOutput<C>;
    try {
      const composite = nestingState(
        state,
        {
          name,
          seq: call.seq,
          person,
          // The composite's nested sends are checked against its profiles'
          // destination policies and those enclosing it (§4.4.2, §5.21.3).
          destinations: [...enclosing, ...profileDestinations],
          flow,
          invokes: invokeNames,
          recorded_by,
          now,
        },
        (entry) => serially(state.threadId, () => appendTrace(state, entry, secrets)),
      );
      output = await options.execute(composite, args, call);
      text = encodeCapabilityOutput(capability, output);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      const contract = cause instanceof CapabilityOutputError;
      try {
        await serially(state.threadId, () =>
          completeTrace(
            state,
            started,
            {
              at: now(),
              status: 'failed',
              error: message,
              ...(contract ? { code: 'R402' as const } : {}),
            },
            secrets,
          ),
        );
      } catch (recordFailure) {
        const why = recordFailure instanceof Error ? recordFailure.message : String(recordFailure);
        return refusal('R407', name, capability, `The call's outcome could not be recorded: ${why}.`, 'It ran and failed.');
      }
      if (contract) {
        return {
          status: 'error',
          error: message,
          error_code: 'R402',
          error_data: { ...cause.diagnostic, location: { tool: name, capability } },
        };
      }
      return { status: 'error', error: message };
    }

    // Grounding (§5.20), after the contract check: each policy that
    // requires the tool's capability applies on its own. The call's argument
    // names are what an `acs:` anchor may cite.
    if (policies.length > 0) {
      let problem: string | null = null;
      try {
        const bound = Object.keys(args as object).filter((k) => /^[A-Za-z_][A-Za-z0-9_-]*$/.test(k));
        const seen = options.seen ? await options.seen({ state, args, output }) : null;
        for (const policy of policies) {
          const result = checkGrounding(output, policy, { bound, seen });
          if (result.code !== null) {
            problem = result.message;
            break;
          }
        }
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : String(cause);
        await serially(state.threadId, () =>
          completeTrace(state, started, { at: now(), status: 'failed', code: 'R407', error: message }, secrets),
        ).catch(() => undefined);
        return refusal('R407', name, capability, `The grounding check could not be completed: ${message}.`, 'It ran.');
      }
      if (problem !== null) {
        const result = refusal(
          'F505',
          name,
          capability,
          `The output of ${name} is not grounded: ${problem}.`,
          'Return evidence anchors to what the call read, or mark the output inferred with an inference_method and a confidence.',
        );
        try {
          await serially(state.threadId, () =>
            completeTrace(state, started, { at: now(), status: 'failed', code: 'F505', error: result.error ?? 'F505' }, secrets),
          );
        } catch (recordFailure) {
          const why = recordFailure instanceof Error ? recordFailure.message : String(recordFailure);
          return refusal('R407', name, capability, `The call's outcome could not be recorded: ${why}.`, 'It ran.');
        }
        return result;
      }
    }

    // The applied profiles' minimum confidence (§5.21.3), after grounding.
    const low = minimumConfidence === null ? null : confidenceFailure(output, minimumConfidence);
    if (low !== null) {
      const result = refusal(
        'F504',
        name,
        capability,
        `The output of ${name} fails a domain profile: ${low.message}.`,
        'Return an output whose confidence, a number from 0 to 1, meets the minimum of the applied profiles.',
      );
      try {
        await serially(state.threadId, () =>
          completeTrace(
            state,
            started,
            { at: now(), status: 'failed', code: 'F504', reason_code: low.reason, error: result.error ?? 'F504' },
            secrets,
          ),
        );
      } catch (recordFailure) {
        const why = recordFailure instanceof Error ? recordFailure.message : String(recordFailure);
        return refusal('R407', name, capability, `The call's outcome could not be recorded: ${why}.`, 'It ran.');
      }
      return result;
    }

    const anchors = output['evidence_anchors'];
    let completed: TraceEntry | undefined;
    try {
      await serially(state.threadId, async () => {
        const entry = await completeTrace(
          state,
          started,
          {
            at: now(),
            status: 'executed',
            ...(Array.isArray(anchors) ? { evidence_anchors: anchors } : {}),
          },
          secrets,
        );
        completed = entry;
        if (capabilities.includes('checkpoint')) {
          const id = typeof output['checkpoint_id'] === 'string' ? output['checkpoint_id'] : `checkpoint-${entry.seq}`;
          const checkpoints = await readCheckpoints(state);
          await state.setValue(KEYS.checkpoints, [
            ...checkpoints,
            { id, valid: true, seq: entry.seq, at: entry.at, flow_id: flow },
          ]);
        }
      });
    } catch (recordFailure) {
      // The tool ran; its record could not be completed. The layer reports
      // its own failure (R407) rather than a result it could not record.
      const why = recordFailure instanceof Error ? recordFailure.message : String(recordFailure);
      return refusal(
        'R407',
        name,
        capability,
        `The call ran, but its record could not be completed: ${why}.`,
        'Check the thread store.',
      );
    }

    // A notification of the evidence recorded (§6.6), at most once.
    if (completed !== undefined) notifyEvidence(state, completed);
    return { status: 'success', result: text };
  };

  const definition = defineTool<ThreadState, Args>({
    description: options.description,
    args: options.args,
    annotations: { ...options.annotations, [ANNOTATION_KEY]: annotation },
    ...(options.variables !== undefined ? { variables: options.variables } : {}),
    ...(options.progressArgument !== undefined ? { progressArgument: options.progressArgument } : {}),
    // With `invokes`, the runtime enforces the list too.
    ...(invokeNames.length > 0 ? { uses: invokeNames } : {}),
    // `UsesAwareExecute` is a conditional type on `Args`, which TypeScript
    // cannot resolve while `Args` is still generic; for any concrete `Args`
    // it is exactly the signature of `execute` above.
    execute: execute as UsesAwareExecute<ThreadState, Args, readonly string[]>,
  });
  STATED_NAMES.set(definition, name);
  EFFECTIVE.set(definition, flags);
  PERFORMS.set(definition, [...capabilities.map((capability) => ({ capability, risk })), ...nested]);
  if (person) PERSON.add(definition);
  noteBound(name, capability);
  return definition;
}

export interface ControlToolOptions<Args extends ToolArgs> {
  /** The tool's name, as the runtime knows it. */
  name: string;
  description: string;
  args: Args;
  /** What the tool returns; a plain success when omitted. */
  execute?: (state: ThreadState, args: z.infer<Args>) => Promise<ToolResult>;
  /**
   * Called when the call's trace entry cannot be written: the call still
   * succeeds (§5.18.3). Defaults to `console.error`.
   */
  onRecordFailure?: (error: unknown) => void;
  /** Other owners' annotation keys. */
  annotations?: Record<string, unknown>;
  /** Milliseconds since the Unix epoch; defaults to `Date.now`. */
  now?: () => number;
}

/**
 * Define a control-only tool (§5.18.3): it only signals the host (ends a
 * turn or a session, reports a status), performs no capability, and is
 * never refused. Each call is recorded (`control: true`); a record that
 * cannot be written is reported to `onRecordFailure` and the call still
 * succeeds. Bind a stop or session action to a tool like this one (F506).
 */
export function controlTool<Args extends ToolArgs>(options: ControlToolOptions<Args>): ToolDefinition<ThreadState, Args> {
  const { name } = options;
  const now = options.now ?? (() => Date.now());
  const onRecordFailure =
    options.onRecordFailure ?? ((error: unknown) => console.error(`controlTool '${name}': its call was not recorded`, error));
  const annotation: AcsControlAnnotation = { standard: STANDARD_VERSION, ontology: ONTOLOGY_VERSION, tool: name, control: true };
  let layer: Promise<RecordedBy> | undefined;

  const execute = async (state: ThreadState, args: z.infer<Args>): Promise<ToolResult> => {
    try {
      layer ??= digestOf(annotation as unknown as Json).then((config_sha256) => ({
        name: LAYER_NAME,
        version: STANDARD_VERSION,
        config_sha256,
      }));
      const recorded_by = await layer;
      const flow = flowOf(state);
      const step = stepOf(state);
      await serially(state.threadId, () =>
        appendTrace(state, {
          at: now(),
          action: name,
          capability: null,
          control: true,
          ...(flow !== null ? { flow_id: flow } : {}),
          ...(step !== null ? { step } : {}),
          status: 'executed',
          recorded_by,
        }),
      );
    } catch (error) {
      onRecordFailure(error);
    }
    if (options.execute) return options.execute(state, args);
    return { status: 'success', result: 'ok' };
  };

  const definition = defineTool<ThreadState, Args>({
    description: options.description,
    args: options.args,
    annotations: { ...options.annotations, [ANNOTATION_KEY]: annotation },
    execute: execute as UsesAwareExecute<ThreadState, Args, readonly string[]>,
  });
  STATED_NAMES.set(definition, name);
  EFFECTIVE.set(definition, { risk: 'low', mutation: false, requires_checkpoint: false, requires_approval: false });
  PERFORMS.set(definition, []);
  noteBound(name, 'control');
  return definition;
}

/** The `acs` annotation of a tool definition, if it has a well-formed one. */
export function acsAnnotation(tool: { annotations?: Record<string, unknown> }): AcsAnnotation | null {
  const value = tool.annotations?.[ANNOTATION_KEY];
  if (typeof value !== 'object' || value === null) return null;
  const candidate = value as Partial<AcsAnnotation>;
  return typeof candidate.capability === 'string' && Object.hasOwn(CAPABILITIES, candidate.capability)
    ? (candidate as AcsAnnotation)
    : null;
}

/** The `acs` annotation of a control-only tool, if the tool has one. */
export function acsControlAnnotation(tool: { annotations?: Record<string, unknown> }): AcsControlAnnotation | null {
  const value = tool.annotations?.[ANNOTATION_KEY];
  if (typeof value !== 'object' || value === null) return null;
  return (value as Partial<AcsControlAnnotation>).control === true ? (value as AcsControlAnnotation) : null;
}
