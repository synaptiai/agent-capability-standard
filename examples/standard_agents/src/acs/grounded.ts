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
 * the tools it may call in `invokes` (§5.18.4). Each invocation of a grounded
 * tool issues a one-shot nesting token; the invoked tool is covered by the
 * composite's approval and checkpoint only if it takes a token that matches
 * its execution, its name and its arguments, and only if the decisions that
 * approved the composite are valid for its own approval. Same thread or
 * execution is not evidence that the composite's own code made the call. An
 * invocation of a listed tool defined with plain `defineTool` and a binding
 * record is checked and recorded by the composite's nesting state itself,
 * what it returns included, and runs only under a name `registerTools`
 * registered as that very tool; one with no binding the layer loads may not
 * be listed (V107). A call queued through the composite's state
 * (`queueTool`) runs after it as a call of its own: it may be one of a
 * listed grounded or control tool, which checks itself, and of no other.
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
  decodeCapabilityOutput,
  digest as digestOf,
  encodeCapabilityOutput,
  groundingPolicies,
  holdsCredential,
  iJsonProblem,
  joinFlags,
  type BindingApproval,
  type BoundTool,
  type GroundingPolicy,
  type Json,
} from '@synaptiai/acs-core';
import { notifyEvidence } from './evidence.js';
import { destinationPolicies, layerProfiles, layerSecrets, registeredTool, registerSecrets } from './layer.js';
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
  /** For a `send` tool: the RFC 6901 pointer to the argument that holds the destination (§5.18.1). */
  destination?: string;
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
   * flags and their approval (the most approvers, the shortest expiry, a
   * role one of them sets), transitively; a call it makes to a tool not
   * listed is refused with F504, and a tool with no `invokes` may invoke
   * none (it declares `uses: []`). A listed tool is one defined with
   * `groundedTool` or `controlTool`, or with plain `defineTool` and an `acs`
   * annotation that loads as a binding record, whose nested calls the
   * composite's nesting state checks as a grounded tool's call (a `persist`
   * or `audit` call's data for secrets, a `send`'s destination against
   * every policy in force, that the composite's decisions are valid for its
   * approval, its prerequisites, and what it returns against its output
   * contract, this tool's grounding policies and its profiles' minimum
   * confidence) and records, under a name `registerTools` registered as
   * that very tool only; a tool with no binding the layer loads throws
   * (V107). A name registered as another tool than the one listed is
   * refused, and, while a destination policy is in force, so is one no tool
   * is registered under. `state.queueTool` queues only a listed grounded or
   * control tool, which checks itself when it runs.
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
   * call has run; its trace entry is `failed`). With its profiles' they
   * apply too to the outputs of the nested calls it makes to plain tools,
   * which have no options of their own, by those tools' capabilities.
   * Checked when the tool is defined: a capability the ontology does not
   * define throws (V101).
   * Without this option the output check is 1.1's: the contract's required
   * fields, `evidence_anchors` an array, and a required `confidence` from 0
   * to 1.
   */
  grounding?: GroundingPolicy | readonly GroundingPolicy[];
  /**
   * Domain profiles (STANDARD 1.2.0 §5.21) this layer applies to the tool's
   * calls, beside the layer's (`configureLayer({ profiles })`, applied to
   * every grounded tool defined after it), as the core computed them
   * (`bindingProfiles`): they raise the
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
   * number from 0 to 1, fails with F504 (the call has run), this tool's and
   * a nested plain call's. Their `allowed_destinations` join the layer's
   * destination policies for this
   * tool's `send` calls (§4.4.2; see `configureLayer`) and, for a
   * composite, for the sends its code invokes at any depth: each nested
   * call the binding attributes to it (§5.18.4).
   */
  profiles?: BindingProfiles;
  /**
   * For a tool whose capabilities include `send`: where a call's
   * destination is, as an RFC 6901 pointer into its arguments (`'/to'`,
   * which the annotation states as the record's `destination`, §5.18.1) or
   * a function of them (`args => args.to`). It only says where to look: the
   * destination policies in force are the layer's (`configureLayer`) and the
   * profiles'. A `send` tool defined without it has a destination the layer
   * cannot tell, so while any policy is in force its calls are refused with
   * F504 (STANDARD 1.2.0 §4.4.2, §5.18.10): the layer does not guess an
   * argument the tool's own code may not send to. A tool that does not
   * perform `send` throws when defined with it, as does a pointer that is
   * not one.
   */
  destination?: string | ((args: Record<string, unknown>) => unknown);
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
   * trace entry this tool writes passes through, and refused in a `persist`
   * or `audit` call's data. They join the layer's (`registerSecrets`): an
   * array when the tool is defined, a function's values at each call, so
   * every entry the binding writes is redacted with them, those of other
   * tools and of the audit hook included. The default patterns and the
   * secrets registered layer-wide (`configureLayer({ secrets })`) apply
   * whether or not this is given.
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
 * The approval each tool defined here asks for a call (§5.18.7): its own,
 * joined for a composite with that of each tool it invokes, transitively
 * (§5.18.4).
 */
const POLICY = new WeakMap<object, ApprovalPolicy>();

/**
 * The binding a tool another tool invokes has when it was not defined here
 * (§5.18.4): its `acs` annotation read as a binding record (copies
 * ignored), when that loads on its own; undefined for a tool with no
 * annotation, or one that does not load (unbound, §5.18.2: V107 in
 * `invokes`).
 */
function invokedBinding(name: string, tool: object & { annotations?: Record<string, unknown> }): BoundTool | undefined {
  const record = annotationRecord(name, tool.annotations?.[ANNOTATION_KEY]);
  return record ? checkBindings([record]).effective[name] : undefined;
}

/** A binding's `approval` as a policy. */
function policyOf(approval: BindingApproval | undefined): ApprovalPolicy {
  if (approval === undefined) return {};
  return {
    min_approvers: approval.min_approvers,
    ...(approval.role !== undefined ? { role: approval.role } : {}),
    ...(approval.expires_ms !== undefined ? { expires_ms: approval.expires_ms } : {}),
  };
}

/**
 * The approval a composite's call needs (§5.18.4): its approval covers its
 * nested calls, so it is the strictest of its own and each invoked tool's:
 * the most approvers, the shortest expiry, and a role one of them sets (its
 * own first). A nested call whose own role differs is not covered by it
 * (`decisionsCover`).
 */
function joinPolicy(a: ApprovalPolicy, b: ApprovalPolicy | undefined): ApprovalPolicy {
  if (b === undefined) return a;
  const role = a.role ?? b.role;
  const expires =
    a.expires_ms === undefined ? b.expires_ms : b.expires_ms === undefined ? a.expires_ms : Math.min(a.expires_ms, b.expires_ms);
  return {
    ...(a.min_approvers !== undefined || b.min_approvers !== undefined
      ? { min_approvers: Math.max(a.min_approvers ?? 1, b.min_approvers ?? 1) }
      : {}),
    ...(role !== undefined ? { role } : {}),
    ...(expires !== undefined ? { expires_ms: expires } : {}),
  };
}

/**
 * Whether the decisions that approved a composite's call (`authority`, the
 * request it counted) are valid for a nested call's own approval as well
 * (§5.18.4, §5.18.7): the role it sets, at least its approvers, each still
 * within its expiry at `now`. Only then does the composite's approval cover
 * the nested call.
 */
function decisionsCover(authority: ApprovalRecord, policy: ApprovalPolicy, now: number): boolean {
  if (policy.role !== undefined && authority.role !== policy.role) return false;
  const expires =
    authority.expires_ms === undefined
      ? policy.expires_ms
      : policy.expires_ms === undefined
        ? authority.expires_ms
        : Math.min(authority.expires_ms, policy.expires_ms);
  const view: ApprovalRecord = { ...authority, ...(expires !== undefined ? { expires_ms: expires } : {}) };
  const approvers = new Set(countedDecisions(view, now).map((d) => d.approver));
  return approvers.size >= Math.max(authority.min_approvers, policy.min_approvers ?? 1);
}

/** The value an RFC 6901 pointer locates in a call's arguments, or undefined. */
function atPointer(args: unknown, pointer: string): unknown {
  if (pointer === '') return args;
  if (!pointer.startsWith('/')) return undefined;
  let value: unknown = args;
  for (const token of pointer.split('/').slice(1)) {
    const key = token.replaceAll('~1', '/').replaceAll('~0', '~');
    if (Array.isArray(value)) {
      if (!/^(0|[1-9][0-9]*)$/.test(key)) return undefined;
      value = value[Number(key)];
    } else if (typeof value === 'object' && value !== null && Object.hasOwn(value, key)) {
      value = (value as Record<string, unknown>)[key];
    } else {
      return undefined;
    }
  }
  return value;
}

/**
 * Whether a composite's call is still running: its code's invocations are
 * nested calls only while it runs (§5.18.4). `execute` clears it once the
 * composite's own code has settled.
 */
interface CompositeScope {
  open: boolean;
}

/**
 * One invocation of a listed tool by a running composite: a one-shot token
 * the invoked tool takes to be covered (§5.18.4). It carries what the
 * composite's call held, since the runtime runs whatever tool it knows under
 * the name, which need not be the one the composite listed: a nested call is
 * covered only by an approval and a checkpoint the composite's call had.
 */
interface NestingToken {
  composite: string;
  seq: number;
  /** The composite's approval counted only a person's decisions (§5.21.3). */
  person: boolean;
  /**
   * The composite's call used a checkpoint (its own, or the one of the call
   * that covered it): only then does it cover a nested call that needs one.
   */
  checkpoint: boolean;
  /** The composite's call is still running: a token is honoured only while it is. */
  scope: CompositeScope;
  /**
   * The destination policies of the profiles given to the composite and to
   * every composite enclosing it (§4.4.2, §5.21.3): a nested send is checked
   * against them too.
   */
  destinations: readonly (readonly string[])[];
  /**
   * The approval request whose decisions approved the composite's call (its
   * own, or the one that covered it): a nested call is covered only when
   * they are valid for its own approval too (§5.18.4).
   */
  authority: ApprovalRecord | null;
  flow: string;
  tool: string;
  digest: string;
  used: boolean;
}

/** The pending invocations of each thread. */
const TOKENS = new Map<string, NestingToken[]>();

/**
 * The token of a pending invocation that matches this call, if any, while
 * the composite that made it still runs; taking it (`used`) is the
 * caller's, once the checks that precede coverage passed.
 */
function findToken(thread: string, flow: string | null, tool: string, argsDigest: string): NestingToken | undefined {
  if (flow === null) return undefined;
  return (TOKENS.get(thread) ?? []).find(
    (t) => !t.used && t.scope.open && t.flow === flow && t.tool === tool && t.digest === argsDigest,
  );
}

/**
 * The state a composite's own code gets: the runtime's state, with an
 * `invokeTool` that refuses a tool the composite does not list (F504),
 * issues a nesting token for a grounded or control tool it lists, and checks
 * and records itself a call of a listed tool defined with plain
 * `defineTool` and a binding record (`invokePlain`); and a `queueTool` that
 * queues only a listed grounded or control tool. Once the composite's call
 * has ended, an invocation through it is not a nested call (§5.18.4): its
 * code kept the state and invoked later, or did not wait for the
 * invocation. It is refused with F504, not run uncovered: a plain tool it
 * reaches has no wrapper to check it as a call of its own.
 *
 * The runtime runs whatever tool it registers under an invoked name, which
 * need not be the one listed (§5.18.4), and the layer cannot read its
 * registry: `registerTools` is the deployment's statement of it. An
 * invocation of a name registered as another tool than the one listed, or
 * as two, is refused (F504); a listed plain tool, whose code runs without
 * the wrapper, is run only under a name registered as that very tool, since
 * its checks are those of the binding listed; and while a destination
 * policy is in force, so is any listed tool, since a tool the runtime runs
 * under an unregistered name may send anywhere (§4.4.2, §5.18.10).
 */
function nestingState(
  state: ThreadState,
  composite: {
    name: string;
    seq: number;
    person: boolean;
    /** The composite's call used a checkpoint, its own or its covering call's. */
    checkpoint: boolean;
    scope: CompositeScope;
    destinations: readonly (readonly string[])[];
    authority: ApprovalRecord | null;
    flow: string | null;
    /** The tools the composite lists, by the name it invokes each under. */
    invokes: Readonly<Record<string, object>>;
    /** The listed tools not defined here, with the binding each loads as. */
    plain: ReadonlyMap<string, BoundTool>;
    /**
     * The composite's grounding policies, its own and its applied profiles'
     * (§5.20, §5.21.3): those requiring a nested plain call's capability
     * apply to its output, as a plain tool has no options of its own.
     */
    grounding: readonly GroundingPolicy[];
    /** The highest minimum confidence of the composite's applied profiles (§5.21.3), or null. */
    minimumConfidence: number | null;
    recorded_by: RecordedBy;
    secrets: readonly string[];
    now: () => number;
  },
): ThreadState {
  const write = <T>(body: () => Promise<T>): Promise<T> => serially(state.threadId, body);
  const step = stepOf(state);
  const position = {
    ...(composite.flow !== null ? { flow_id: composite.flow } : {}),
    ...(step !== null ? { step } : {}),
  };
  const listed = (tool: string): boolean => Object.hasOwn(composite.invokes, tool);

  const boundCapability = (tool: string): CapabilityId | null => {
    const bound = composite.plain.get(tool)?.capabilities[0] ?? BOUND_NAMES.get(tool) ?? null;
    return bound === null || bound === 'control' ? null : bound;
  };

  /**
   * Record a refusal of an invocation through the composite's state: one
   * attributed to the composite's running call carries its `covered_by`;
   * one made after its call ended is no nested call, so it carries none
   * (§5.18.4). Recording it never fails the refusal.
   */
  const recordRefusal = (tool: string, result: ToolResult, attributed: boolean): Promise<unknown> => {
    const plain = composite.plain.get(tool);
    const control = plain?.control === true || (plain === undefined && BOUND_NAMES.get(tool) === 'control');
    return write(() =>
      appendTrace(
        state,
        {
          at: composite.now(),
          action: tool,
          capability: boundCapability(tool),
          ...(control ? { control: true as const } : {}),
          ...position,
          status: 'refused',
          code: 'F504',
          ...(attributed ? { covered_by: composite.seq } : {}),
          recorded_by: composite.recorded_by,
          error: result.error ?? 'F504',
        },
        composite.secrets,
      ),
    ).catch(() => undefined);
  };

  /**
   * Why an invocation of `tool` through the composite's state is refused
   * before anything runs (F504), or null: the composite's call has ended
   * (§5.18.4: no nested call), it does not list the tool, or the layer
   * cannot tell that the tool the runtime runs under the name is the one
   * listed. A plain listed tool is checked by its listed binding, so it runs
   * only under a name registered as that very tool (`registerTools`).
   */
  const refusalOf = (tool: string): { result: ToolResult; attributed: boolean } | null => {
    const capability = boundCapability(tool);
    if (!composite.scope.open) {
      return {
        attributed: false,
        result: refusal(
          'F504',
          tool,
          capability,
          `${composite.name}'s call has ended, so this invocation through its state is not a nested call its approval and checkpoint cover (STANDARD 1.2.0 §5.18.4).`,
          `Invoke ${tool} while ${composite.name} runs, and wait for it; or call ${tool} as a call of its own.`,
        ),
      };
    }
    if (!listed(tool)) {
      return {
        attributed: true,
        result: refusal('F504', tool, capability, `${composite.name} does not list ${tool} in invokes.`, `Add ${tool} to the invokes of ${composite.name}.`),
      };
    }
    const registered = registeredTool(tool);
    const why =
      registered === null
        ? `two different tools are registered under the name ${tool} (registerTools), so the layer cannot tell which one the runtime runs`
        : registered !== undefined && registered !== composite.invokes[tool]
          ? `the tool registered under the name ${tool} (registerTools) is not the one ${composite.name} lists, so the checks the listed binding gives do not apply to the tool the runtime runs`
          : registered === undefined && composite.plain.has(tool)
            ? `${tool} is defined with plain defineTool, whose code runs without the wrapper, and no tool is registered under its name (registerTools), so the layer cannot tell that the tool the runtime runs under it is the one ${composite.name} lists, whose binding it would check`
            : registered === undefined && (destinationPolicies().length > 0 || composite.destinations.length > 0)
              ? `a destination policy is in force and no tool is registered under the name ${tool} (registerTools), so the layer cannot tell that the tool the runtime runs under it is the one ${composite.name} lists, which checks where it sends, and not one that may send anywhere (STANDARD 1.2.0 §4.4.2, §5.18.10)`
              : null;
    if (why === null) return null;
    return {
      attributed: true,
      result: refusal(
        'F504',
        tool,
        capability,
        `The layer cannot check this nested call: ${why} (STANDARD 1.2.0 §5.18.4).`,
        `Register the agent's tools, by the names the runtime runs them under, with registerTools, and list in invokes of ${composite.name} the tool registered under ${tool}.`,
      ),
    };
  };

  /**
   * The checks of a nested plain call's output (§5.18.10, §5.20, §5.21.3),
   * as `execute` makes them on a grounded tool's: the output contract
   * (R402), then the composite's grounding policies that require the
   * capability (F505), then its profiles' minimum confidence (F504). Null
   * when the output passes, with the output.
   */
  const checkOutput = (
    tool: string,
    capability: CapabilityId,
    args: Record<string, unknown>,
    result: ToolResult,
  ):
    | { output: Record<string, Json>; failure?: undefined }
    | { failure: ToolResult; code: RefusalCode; reason_code?: 'below_minimum_confidence' | 'invalid_confidence' } => {
    let output: Record<string, Json>;
    try {
      output = decodeCapabilityOutput(capability, result.result as string);
    } catch (cause) {
      if (!(cause instanceof CapabilityOutputError)) throw cause;
      return {
        code: 'R402',
        failure: {
          status: 'error',
          error: cause.message,
          error_code: 'R402',
          error_data: { ...cause.diagnostic, location: { tool, capability } },
        },
      };
    }
    const policies = composite.grounding.filter((p) => p.require.includes(capability));
    if (policies.length > 0) {
      const bound = Object.keys(args).filter((k) => /^[A-Za-z_][A-Za-z0-9_-]*$/.test(k));
      for (const policy of policies) {
        const grounding = checkGrounding(output, policy, { bound, seen: null });
        if (grounding.code !== null) {
          return {
            code: 'F505',
            failure: refusal(
              'F505',
              tool,
              capability,
              `The output of ${tool} is not grounded: ${grounding.message}.`,
              'Return evidence anchors to what the call read, or mark the output inferred with an inference_method and a confidence.',
            ),
          };
        }
      }
    }
    const low = composite.minimumConfidence === null ? null : confidenceFailure(output, composite.minimumConfidence);
    if (low !== null) {
      return {
        code: 'F504',
        reason_code: low.reason,
        failure: refusal(
          'F504',
          tool,
          capability,
          `The output of ${tool} fails a domain profile: ${low.message}.`,
          'Return an output whose confidence, a number from 0 to 1, meets the minimum of the applied profiles.',
        ),
      };
    }
    return { output };
  };

  /**
   * A nested call of a listed tool the binding did not define (§5.18.4):
   * its code runs without the wrapper, so the layer, which sees the
   * invocation, makes here every check the composite's approval and
   * checkpoint do not cover ("Every other check still applies"): that its
   * `persist` data or `audit` record holds no secret (§5.18.10, §6.7), a
   * `send`'s destination against every policy in force (§4.4.2), that the
   * composite's decisions are valid for the binding's own approval (no other
   * approval can be asked of it), its prerequisites (§5.18.5), and, once it
   * has run, its output (§5.18.10, §5.20, §5.21.3): a call whose output is
   * refused has run and failed, and is no prerequisite that ran. It records
   * the call with the call that covered it, before it runs and again with
   * its outcome (§5.18.8).
   */
  const invokePlain = async (tool: string, bound: BoundTool, args: Record<string, unknown>): Promise<ToolResult> => {
    const capability = bound.control ? null : (bound.capabilities[0] ?? null);
    let args_digest: string | undefined;
    try {
      args_digest = await digestOf(args as Json);
    } catch {
      args_digest = undefined;
    }
    const base = {
      action: tool,
      capability,
      ...(bound.control ? { control: true as const } : {}),
      ...(bound.domain !== undefined ? { domain: bound.domain } : {}),
      ...position,
      ...(args_digest !== undefined ? { args_digest } : {}),
      covered_by: composite.seq,
      recorded_by: composite.recorded_by,
    };
    const refuseNested = async (code: RefusalCode, message: string, suggestion: string): Promise<ToolResult> => {
      const result = refusal(code, tool, capability, message, suggestion);
      await write(() =>
        appendTrace(state, { ...base, at: composite.now(), status: 'refused', code, error: result.error ?? code }, composite.secrets),
      ).catch(() => undefined);
      return result;
    };
    // Data a persist call would store, or a record an audit call would
    // append, that holds a secret is refused, not redacted (§5.18.10, §6.7).
    const records = bound.capabilities.includes('persist') || bound.capabilities.includes('audit');
    if (records && holdsCredential(args as Json, composite.secrets)) {
      return refuseNested(
        'F504',
        `The ${bound.capabilities.includes('persist') ? 'data this nested call would store' : 'record this nested call would append'} holds what looks like a credential (STANDARD 1.2.0 §6.7).`,
        'Store where the secret is kept, or cite it by reference or digest, not the secret itself.',
      );
    }
    if (bound.capabilities.includes('send')) {
      const policies = [...destinationPolicies(), ...composite.destinations];
      if (policies.length > 0) {
        const destination = bound.destination === undefined ? undefined : atPointer(args, bound.destination);
        if (typeof destination !== 'string' || !allowed(policies, destination)) {
          return refuseNested(
            'F504',
            typeof destination === 'string'
              ? "This nested call's destination is not one the destination policies in force allow."
              : `This nested call sends, and the layer cannot tell where: ${
                  bound.destination === undefined
                    ? 'its binding names no destination argument'
                    : `its argument at ${bound.destination} is not a string`
                }, so no destination policy in force can allow it.`,
            'Send only to an allowed destination (STANDARD 1.2.0 §4.4.2).',
          );
        }
      }
    }
    if (bound.requires_approval) {
      const policy = policyOf(bound.approval);
      if (composite.authority === null || !decisionsCover(composite.authority, policy, composite.now())) {
        return refuseNested(
          'F502',
          `The decisions that approved ${composite.name} are not valid for the approval ${tool} needs (its role, approvers or expiry), and ${tool} is not defined with groundedTool, so no decision of its own can be asked.`,
          `Give ${composite.name} the approval ${tool} needs, or define ${tool} with groundedTool.`,
        );
      }
    }
    const executed = await readExecuted(state);
    for (const needed of bound.prerequisites) {
      if (!executed[needed]) {
        const code: RefusalCode =
          needed !== 'checkpoint' ? 'V102' : bound.capabilities.includes('rollback') ? 'F503' : 'F501';
        return refuseNested(
          code,
          `'${capability}' requires '${needed}' to have run first in this thread.`,
          `Call a '${needed}' tool, then call ${composite.name} again.`,
        );
      }
    }
    const late = refusalOf(tool);
    if (late !== null) {
      await recordRefusal(tool, late.result, late.attributed);
      return late.result;
    }
    let started: TraceEntry;
    try {
      started = await write(() => appendTrace(state, { ...base, at: composite.now(), status: 'started' }, composite.secrets));
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      return refusal('R407', tool, capability, `The nested call could not be recorded: ${message}.`, 'The call did not run.');
    }
    // The composite may have ended while the record was written: the call
    // starts below, synchronously after this check, or not at all.
    if (!composite.scope.open) {
      const result = refusal(
        'F504',
        tool,
        capability,
        `${composite.name}'s call ended before this nested call could start (STANDARD 1.2.0 §5.18.4).`,
        `Wait for ${tool} before ${composite.name} returns.`,
      );
      await write(() =>
        completeTrace(state, started, { at: composite.now(), status: 'refused', code: 'F504', error: result.error ?? 'F504' }, composite.secrets),
      ).catch(() => undefined);
      return result;
    }
    let result: ToolResult;
    try {
      result = await state.invokeTool(tool, args);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      await write(() =>
        completeTrace(state, started, { at: composite.now(), status: 'failed', error: message }, composite.secrets),
      ).catch(() => undefined);
      throw cause;
    }
    // Check what it returned as a grounded tool's output is checked; a
    // control tool's call returns none (§5.18.3).
    let checked: ReturnType<typeof checkOutput> | undefined;
    if (result.status !== 'error' && capability !== null) {
      try {
        checked = checkOutput(tool, capability, args, result);
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : String(cause);
        await write(() =>
          completeTrace(state, started, { at: composite.now(), status: 'failed', code: 'R407', error: message }, composite.secrets),
        ).catch(() => undefined);
        return refusal('R407', tool, capability, `The output check of the nested call could not be completed: ${message}.`, 'It ran.');
      }
    }
    const anchors = checked?.failure === undefined ? checked?.output['evidence_anchors'] : undefined;
    const outcome: Parameters<typeof completeTrace>[2] =
      checked?.failure !== undefined
        ? {
            at: composite.now(),
            status: 'failed',
            code: checked.code,
            ...(checked.reason_code !== undefined ? { reason_code: checked.reason_code } : {}),
            error: checked.failure.error ?? checked.code,
          }
        : {
            at: composite.now(),
            status: result.status === 'error' ? 'failed' : 'executed',
            ...(result.status === 'error' && result.error !== undefined ? { error: result.error } : {}),
            ...(Array.isArray(anchors) ? { evidence_anchors: anchors } : {}),
          };
    let completed: TraceEntry;
    try {
      completed = await write(() => completeTrace(state, started, outcome, composite.secrets));
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      return refusal('R407', tool, capability, `The nested call ran, but its record could not be completed: ${message}.`, 'Check the thread store.');
    }
    if (checked?.failure !== undefined) return checked.failure;
    // A notification of the evidence recorded (§6.6), at most once.
    if (checked !== undefined) notifyEvidence(state, completed);
    return result;
  };

  const invokeTool = async (tool: string, args: Record<string, unknown> = {}): Promise<ToolResult> => {
    const refused = refusalOf(tool);
    if (refused !== null) {
      await recordRefusal(tool, refused.result, refused.attributed);
      return refused.result;
    }
    const plain = composite.plain.get(tool);
    if (plain !== undefined) return invokePlain(tool, plain, args);
    if (composite.flow === null) return state.invokeTool(tool, args);
    const digest = await digestOf(args as Json);
    // The composite may have ended while the digest was computed (an
    // invocation it did not wait for): no token is issued after it has.
    const late = refusalOf(tool);
    if (late !== null) {
      await recordRefusal(tool, late.result, late.attributed);
      return late.result;
    }
    const token: NestingToken = {
      composite: composite.name,
      seq: composite.seq,
      person: composite.person,
      checkpoint: composite.checkpoint,
      scope: composite.scope,
      destinations: composite.destinations,
      authority: composite.authority,
      flow: composite.flow,
      tool,
      digest,
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

  /**
   * A call queued through the composite's state runs after the composite's
   * call has ended, so it is no nested call (§5.18.4): it is checked as a
   * call of its own, or refused (F504). A listed grounded or control tool
   * checks itself when the runtime runs it; a listed plain tool has no
   * wrapper to check it then, so queueing one is refused, as is queueing a
   * tool the composite does not list, one the layer cannot tell the runtime
   * runs under the name, or any once the composite's call has ended. The
   * refusal is thrown (`queueTool` returns nothing) and recorded.
   */
  const queueTool = (tool: string, args: Record<string, unknown> = {}): void => {
    const refused =
      refusalOf(tool) ??
      (composite.plain.has(tool)
        ? {
            attributed: true,
            result: refusal(
              'F504',
              tool,
              boundCapability(tool),
              `A call queued through ${composite.name}'s state runs after its call has ended, as a call of its own, and ${tool} is defined with plain defineTool, so nothing would check it then (STANDARD 1.2.0 §5.18.4).`,
              `Invoke ${tool} with state.invokeTool while ${composite.name} runs, or define ${tool} with groundedTool.`,
            ),
          }
        : null);
    if (refused !== null) {
      void recordRefusal(tool, refused.result, refused.attributed);
      throw new Error(refused.result.error ?? 'F504');
    }
    state.queueTool(tool, args);
  };

  return new Proxy(state, {
    get(target, property) {
      if (property === 'invokeTool') return invokeTool;
      if (property === 'queueTool') return queueTool;
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
      /** The approval request whose decisions approved the call: its own, or its composite's. */
      authority: ApprovalRecord | null;
      /** The call used a checkpoint: its own, or the one of the composite that covered it. */
      checkpointed: boolean;
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
  // The approval a call needs (§5.18.7): the tool's own, joined with that of
  // each tool it invokes, transitively, since its approval covers their
  // nested calls (§5.18.4).
  const declaredPolicy = options.approval ?? {};
  const problems = policyProblems(declaredPolicy);
  if (problems.length > 0) {
    throw new Error(`groundedTool '${name}': ${problems.join('; ')} (STANDARD 1.2.0 §5.14)`);
  }
  let policy: ApprovalPolicy = declaredPolicy;
  // The listed tools not defined with groundedTool or controlTool, by the
  // binding their `acs` annotation loads as: the composite's nesting state
  // checks and records their calls (§5.18.4). One with no binding the layer
  // loads is unbound, and a composite may not list it (V107): the layer
  // could tell neither what it does nor where it sends.
  const plain = new Map<string, BoundTool>();
  for (const [invoked, tool] of Object.entries(invokes)) {
    const computed = EFFECTIVE.get(tool);
    if (computed !== undefined) {
      flags = joinFlags(flags, computed);
      person ||= PERSON.has(tool);
      nested.push(...(PERFORMS.get(tool) ?? []));
      policy = joinPolicy(policy, POLICY.get(tool));
      continue;
    }
    const bound = invokedBinding(invoked, tool);
    if (bound === undefined) {
      throw new Error(
        `groundedTool '${name}': V107 UNRESOLVED_TARGET: it invokes '${invoked}', which has no binding the layer loads (a tool defined with plain defineTool and no acs annotation, or one that does not load on its own), so the layer can tell neither what its calls do nor where they send; define it with groundedTool or controlTool, or give it a binding record (STANDARD 1.2.0 §5.18.2, §5.18.4)`,
      );
    }
    plain.set(invoked, bound);
    flags = joinFlags(flags, {
      risk: bound.risk,
      mutation: bound.mutation,
      requires_checkpoint: bound.requires_checkpoint,
      requires_approval: bound.requires_approval,
    });
    nested.push(...bound.capabilities.map((c) => ({ capability: c, risk: bound.risk })));
    policy = joinPolicy(policy, policyOf(bound.approval));
  }
  const risk = flags.risk;
  // Domain profiles (§5.21.3): the tool's own (`profiles`) and the layer's
  // (`configureLayer({ profiles })`), applied together. They raise the
  // flags for each capability at the call's effective risk R before
  // profiles, which includes its other capabilities and the tools it
  // invokes (§5.18.3, §5.18.4); and, since a composite's effective flags
  // include those of each tool it lists, those for what its nested calls
  // perform, at their own R (so `block_autonomous` given to a composite
  // alone reaches them).
  const fromLayer = layerProfiles();
  const applied: BindingProfiles[] = [
    ...(options.profiles !== undefined ? [options.profiles] : []),
    ...(fromLayer !== null && fromLayer !== options.profiles ? [fromLayer] : []),
  ];
  for (const profiles of applied) {
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
  const minimums = applied.map((p) => p.policy.minimum_confidence).filter((m): m is number => m !== null);
  const minimumConfidence = minimums.length > 0 ? Math.max(...minimums) : null;
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
  const fromProfiles: GroundingPolicy[] = applied.flatMap((p) =>
    p.policy.grounding.map((g) => ({
      require: g.require as CapabilityId[],
      ...(g.kinds !== null ? { kinds: g.kinds } : {}),
    })),
  );
  // A nested call of a plain tool it invokes, which has no options of its
  // own, is checked under all of them (§5.18.4).
  const allPolicies = [
    ...(options.grounding === undefined ? [] : groundingPolicies(options.grounding)),
    ...(fromProfiles.length > 0 ? groundingPolicies(fromProfiles) : []),
  ];
  const policies = allPolicies.filter((p) => p.require.includes(capability));
  // The tool's own secrets and the layer's (§6.7), read at each call. The
  // tool's join the layer's (registerSecrets), so that the entries other
  // tools and the audit hook write are redacted with them too: an array
  // now, a function's values when it gives them.
  if (Array.isArray(options.secrets)) registerSecrets(options.secrets);
  const secretsOf = async (state: ThreadState): Promise<readonly string[]> => {
    const given = options.secrets;
    const own = typeof given === 'function' ? await given(state) : (given ?? []);
    if (typeof given === 'function') registerSecrets(own);
    return [...own, ...layerSecrets()];
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
  // Where a call's destination is: the option's pointer or function. A send
  // tool defined without it has a destination the layer cannot tell, so
  // under a policy its calls are refused (§4.4.2, §5.18.10): an argument the
  // layer guessed (`destination`, say) need not be where the tool's own code
  // sends.
  const pointer = typeof options.destination === 'string' ? options.destination : undefined;
  if (pointer !== undefined && pointer !== '' && !pointer.startsWith('/')) {
    throw new Error(
      `groundedTool '${name}': the destination option ${JSON.stringify(pointer)} is not an RFC 6901 pointer (one that starts with '/') (STANDARD 1.2.0 §5.18.1)`,
    );
  }
  const destinationOf: ((args: Record<string, unknown>) => unknown) | null =
    pointer !== undefined
      ? (args) => atPointer(args, pointer)
      : typeof options.destination === 'function'
        ? options.destination
        : null;
  // The tool's own profiles' destination policies; the layer's profiles'
  // are among the layer's policies (`destinationPolicies`).
  const profileDestinations = options.profiles?.policy.destinations ?? [];

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
    ...(pointer !== undefined ? { destination: pointer } : {}),
    ...(options.approval !== undefined && Object.keys(options.approval).length > 0
      ? {
          approval: {
            ...(declaredPolicy.min_approvers !== undefined ? { min_approvers: declaredPolicy.min_approvers } : {}),
            ...(declaredPolicy.role !== undefined ? { role: declaredPolicy.role } : {}),
            ...(declaredPolicy.expires_ms !== undefined ? { expires: durationText(declaredPolicy.expires_ms) } : {}),
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
      ...(options.profiles !== undefined ? { profiles: options.profiles.documents } : {}),
      ...(fromLayer !== null && fromLayer !== options.profiles ? { layer_profiles: fromLayer.documents } : {}),
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

      // The layer's profiles this tool's flags were computed with must be
      // the ones in force: profiles configured later would not apply to it
      // (§5.21.1), so its call is refused rather than run without them.
      if (layerProfiles() !== fromLayer) {
        return await refuse(
          refusal(
            'R407',
            name,
            capability,
            "The layer's domain profiles changed (configureLayer) after this tool was defined, so its checks would not apply the profiles in force (STANDARD 1.2.0 §5.21.1).",
            "Define the agent's tools after configureLayer.",
          ),
          'R407',
        );
      }

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
          const destination = destinationOf === null ? undefined : destinationOf(args as Record<string, unknown>);
          if (typeof destination !== 'string' || !allowed(policies, destination)) {
            return await refuse(
              refusal(
                'F504',
                name,
                capability,
                destinationOf === null
                  ? `${name} sends, and the layer cannot tell where: it was defined without the destination option, so no destination policy in force can allow its call.`
                  : typeof destination === 'string'
                    ? "This call's destination is not one the destination policies in force allow."
                    : "This call's destination is not a string, so no destination policy in force can allow it.",
                destinationOf === null
                  ? `Define ${name} with the destination option, the argument its code sends to (STANDARD 1.2.0 §4.4.2, §5.18.10).`
                  : 'Send only to an allowed destination (STANDARD 1.2.0 §4.4.2).',
              ),
              'F504',
            );
          }
        }
      }

      // A nested call the running composite's own code made, with these
      // exact arguments in this execution, is covered by the composite's
      // approval and checkpoint (§5.18.4): only those two checks are skipped,
      // and only as far as the composite's call held them. The runtime runs
      // whatever tool it knows under the invoked name, which need not be the
      // one the composite listed (a copy, a wrapper, another definition), so
      // the composite's own flags prove nothing about this call. A call that
      // needs approval is covered only when decisions approved the
      // composite's call and are valid for its own approval too (its role,
      // approvers and expiry, §5.18.7); one that needs a checkpoint only when
      // the composite's call used one; one a profile requires a person for
      // only by a composite whose approval a person gave (§5.21.3).
      // Otherwise it is checked as a call of its own. Each invocation covers
      // at most one call: the token is taken here, synchronously after it was
      // found.
      if (token !== undefined) token.used = true;
      const covered =
        token !== undefined &&
        (token.person || !person) &&
        (!flags.requires_approval || (token.authority !== null && decisionsCover(token.authority, policy, now()))) &&
        (!flags.requires_checkpoint || token.checkpoint);
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
        authority: request ?? (covered && token !== undefined ? token.authority : null),
        checkpointed: used.checkpoint_id !== undefined || (covered && token !== undefined && token.checkpoint),
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
    const { started, call, flow, recorded_by, enclosing, authority, checkpointed } = claim;

    // Run with the nesting state, check the output contract (§5.18.9),
    // record the outcome.
    let text: string;
    let output: CapabilityOutput<C>;
    // Open while the tool's own code runs: its invocations are nested calls
    // only until it settles (§5.18.4).
    const scope: CompositeScope = { open: true };
    try {
      const composite = nestingState(state, {
        name,
        seq: call.seq,
        person,
        checkpoint: checkpointed,
        scope,
        // The composite's nested sends are checked against its profiles'
        // destination policies and those enclosing it (§4.4.2, §5.21.3).
        destinations: [...enclosing, ...profileDestinations],
        authority,
        flow,
        invokes,
        plain,
        grounding: allPolicies,
        minimumConfidence,
        recorded_by,
        secrets,
        now,
      });
      try {
        output = await options.execute(composite, args, call);
      } finally {
        scope.open = false;
      }
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
    // The runtime enforces the list too, on `invokeTool` and `queueTool`: a
    // tool with no `invokes` declares none (§5.18.4).
    uses: invokeNames,
    // `UsesAwareExecute` is a conditional type on `Args`, which TypeScript
    // cannot resolve while `Args` is still generic; for any concrete `Args`
    // it is exactly the signature of `execute` above.
    execute: execute as UsesAwareExecute<ThreadState, Args, readonly string[]>,
  });
  STATED_NAMES.set(definition, name);
  EFFECTIVE.set(definition, flags);
  POLICY.set(definition, policy);
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
