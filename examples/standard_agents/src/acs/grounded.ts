/**
 * `groundedTool`: a Standard Agents function tool classified by an Agent
 * Capability Standard capability, with that capability's safety rules
 * enforced inside the tool.
 *
 * The Standard Agent Specification (0.2.0) has no hook that can refuse a
 * tool call before it runs, and tool `annotations` "MUST NOT change argument
 * validation, execution, the tool's results, or what is sent to the model".
 * The one place every conforming runtime runs our code before the side
 * effect is the tool's own `execute`. So the wrapper checks there, and
 * returns an ordinary error result when a rule is not met. The annotation
 * only describes the tool; the wrapper is what enforces.
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
  policyProblems,
  requestApproval,
  type ApprovalPolicy,
} from './approval.js';
import { digest as digestOf, type Json } from './canonical.js';
import {
  CAPABILITIES,
  ONTOLOGY_VERSION,
  STANDARD_VERSION,
  effectiveFlags,
  prerequisites,
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
  type CheckpointRecord,
  type Diagnostic,
  type ApprovalRecord,
  type RefusalCode,
  type TraceEntry,
} from './records.js';
import { serially } from './serial.js';

/** The key this binding owns in a tool's `annotations`. */
export const ANNOTATION_KEY = 'acs';

/**
 * What `annotations.acs` holds: the tool's classification and its effective
 * safety flags. `schemas/interop/standard_agents_annotation.schema.json` is
 * the schema.
 */
export interface AcsAnnotation extends SafetyFlags {
  standard: string;
  ontology: string;
  capability: CapabilityId;
  layer: Layer;
  domain?: string;
}

/** What the wrapper tells the tool about this call. */
export interface GroundedCall {
  /** The trace sequence number this call will be recorded under. */
  seq: number;
  /** The checkpoint this call used, when the capability requires one. */
  checkpoint_id?: string;
  /** The approvers who approved this call, when the capability requires approval. */
  approvers?: string[];
}

export interface GroundedToolOptions<C extends CapabilityId, Args extends ToolArgs> {
  /**
   * The tool's name, as the runtime knows it (its file name). A tool cannot
   * see its own name at run time, and the name is part of what an approver
   * approves, so it is stated here.
   */
  name: string;
  /** The ontology capability this tool performs. */
  capability: C;
  /** The capability's domain parameter, e.g. `config` or `email`. */
  domain?: string;
  /** Flags stricter than the capability's; a weaker one is ignored (W602). */
  flags?: DeclaredFlags;
  /** Who may approve and for how long, when the tool needs approval. */
  approval?: ApprovalPolicy;
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
   * Do the work and return the capability's output: every field the
   * ontology requires, including `evidence_anchors`. Throw to fail.
   */
  execute: (state: ThreadState, args: z.infer<Args>, call: GroundedCall) => Promise<CapabilityOutput<C>>;
}

/** How long a checkpoint can authorise a call, unless the tool says otherwise: ten minutes. */
export const CHECKPOINT_MAX_AGE_MS = 10 * 60 * 1000;

function refusal(
  code: RefusalCode,
  tool: string,
  capability: CapabilityId,
  message: string,
  suggestion: string,
  extra: Record<string, Json> = {},
): ToolResult {
  const diagnostic: Diagnostic = {
    code,
    name: CODE_NAMES[code],
    severity: 'error',
    message,
    location: { tool, capability },
    suggestion,
  };
  return {
    status: 'error',
    error: `${code} ${CODE_NAMES[code]}: ${message} ${suggestion}`,
    error_code: code,
    error_data: { ...diagnostic, ...extra },
  };
}

/**
 * How `output` breaks the capability's output contract: a required field
 * that is missing, or `evidence_anchors` or a required `confidence` of the
 * wrong type. The ontology types those two fields the same way wherever it
 * declares them: an array, and a number from 0 to 1.
 */
function outputProblems(capability: CapabilityId, output: unknown): string[] {
  if (typeof output !== 'object' || output === null || Array.isArray(output)) {
    return [`the '${capability}' output is not a JSON object`];
  }
  const record = output as Record<string, unknown>;
  const required: readonly string[] = CAPABILITIES[capability].output_required;
  const problems: string[] = [];
  const missing = required.filter((field) => !(field in record));
  if (missing.length > 0) problems.push(`the '${capability}' output is missing ${missing.join(', ')}`);
  if ('evidence_anchors' in record && !Array.isArray(record['evidence_anchors'])) {
    problems.push(`the '${capability}' output's evidence_anchors is not an array`);
  }
  if (required.includes('confidence') && 'confidence' in record) {
    const confidence = record['confidence'];
    if (typeof confidence !== 'number' || !(confidence >= 0 && confidence <= 1)) {
      problems.push(`the '${capability}' output's confidence is not a number from 0 to 1`);
    }
  }
  return problems;
}

/** The name each tool defined here states for itself; see `statedName`. */
const STATED_NAMES = new WeakMap<object, string>();

/**
 * The name a tool defined with `groundedTool` states for itself: what an
 * approver is shown and the trace records. A tool cannot see the name it is
 * registered under, so `lintPromptTools` compares the two.
 */
export function statedName(tool: object): string | undefined {
  return STATED_NAMES.get(tool);
}

/** What the checks before a call decided. */
type Claim =
  | { outcome: ToolResult }
  | { outcome?: undefined; started: TraceEntry; call: GroundedCall; flow: string | null };

/**
 * Define a function tool that performs one ontology capability and enforces
 * that capability's effective safety flags and `requires` edges before it
 * runs.
 */
export function groundedTool<C extends CapabilityId, Args extends ToolArgs>(
  options: GroundedToolOptions<C, Args>,
): ToolDefinition<ThreadState, Args> {
  const { name, capability, domain } = options;
  const { flags, warnings } = effectiveFlags(capability, options.flags);
  if (warnings.length > 0) {
    throw new Error(`groundedTool '${name}': ${warnings.join('; ')}`);
  }
  const policy = options.approval ?? {};
  const problems = policyProblems(policy);
  if (problems.length > 0) {
    throw new Error(`groundedTool '${name}': ${problems.join('; ')} (STANDARD v1.1.0 §5.14)`);
  }
  const maxAge = options.checkpoint_max_age_ms ?? CHECKPOINT_MAX_AGE_MS;
  if (!(maxAge > 0 && maxAge <= CHECKPOINT_MAX_AGE_MS)) {
    throw new Error(
      `groundedTool '${name}': checkpoint_max_age_ms must be more than zero and at most ${CHECKPOINT_MAX_AGE_MS}, not ${maxAge}`,
    );
  }
  const now = options.now ?? (() => Date.now());

  const annotation: AcsAnnotation = {
    standard: STANDARD_VERSION,
    ontology: ONTOLOGY_VERSION,
    capability,
    layer: CAPABILITIES[capability].layer,
    ...(domain !== undefined ? { domain } : {}),
    ...flags,
  };

  /**
   * Everything before the tool's own code runs: the checks, then using up
   * what the call needs, then the `started` entry. It runs under `serially`,
   * so two calls in this realm cannot both pass on one approval or one
   * checkpoint.
   */
  const check = async (state: ThreadState, argsJson: Json): Promise<Claim> => {
    const flow = flowOf(state);
    const step = stepOf(state);
    const position = { ...(flow !== null ? { flow_id: flow } : {}), ...(step !== null ? { step } : {}) };
    const identity = { action: name, capability, ...(domain !== undefined ? { domain } : {}), ...position };
    // What is known of the call so far, for the record if a write fails.
    const used: Pick<TraceEntry, 'args_digest' | 'approval' | 'checkpoint_id'> = {};
    try {
      used.args_digest = await digestOf(argsJson);
      const base = { ...identity, args_digest: used.args_digest };
      const refuse = async (result: ToolResult, code: RefusalCode): Promise<Claim> => {
        await appendTrace(state, { ...base, at: now(), status: 'refused', code, error: result.error ?? code });
        return { outcome: result };
      };

      // 1. Approval, bound to the digest of exactly what is about to run.
      let request: ApprovalRecord | undefined;
      if (flags.requires_approval) {
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
        request = await requestApproval(state, shown, policy, now());
        const standing = approvalState(request, now());
        if (standing !== 'approved') {
          return await refuse(
            refusal(
              'F502',
              name,
              capability,
              `This call needs approval and the request is ${standing}.`,
              'Tell the person what you intend to do and wait for them to decide; then call the tool again with the same arguments.',
              { digest: request.digest, round: approvalRound(request), shown, state: standing },
            ),
            'F502',
          );
        }
      }

      // 2. `requires` edges: each prerequisite capability must have run.
      const executed = await readExecuted(state);
      for (const needed of prerequisites(capability)) {
        if (!executed[needed]) {
          const code: RefusalCode = capability === 'rollback' ? 'F503' : 'F501';
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
      const checkpoints = flags.requires_checkpoint ? await readCheckpoints(state) : [];
      const unused = [...checkpoints].reverse().filter((c) => c.valid);
      const at = now();
      const checkpoint =
        flow === null ? undefined : unused.find((c) => c.flow_id === flow && at - c.at <= maxAge);
      if (flags.requires_checkpoint && !checkpoint) {
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
        approvers = [...new Set(request.decisions.map((d) => d.approver))];
        used.approval = {
          digest: request.digest,
          approvers,
          decision_ids: request.decisions.map((d) => d.decision_id),
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
      const started = await appendTrace(state, { ...base, ...used, at: now(), status: 'started' });
      return {
        started,
        flow,
        call: {
          seq: started.seq,
          ...(used.checkpoint_id !== undefined ? { checkpoint_id: used.checkpoint_id } : {}),
          ...(approvers !== undefined ? { approvers } : {}),
        },
      };
    } catch (cause) {
      // A write failed, or the arguments have no canonical JSON. Record what
      // the call used, so no approval or checkpoint is spent without a trace
      // entry; if the store refuses that too, there is nothing more to do.
      const message = cause instanceof Error ? cause.message : String(cause);
      await appendTrace(state, { ...identity, ...used, at: now(), status: 'failed', error: message }).catch(() => undefined);
      return { outcome: { status: 'error', error: message } };
    }
  };

  const execute = async (state: ThreadState, args: z.infer<Args>): Promise<ToolResult> => {
    const claim = await serially(state.threadId, () => check(state, args as Json));
    if (claim.outcome) return claim.outcome;
    const { started, call, flow } = claim;

    // Run, check the output contract, record the outcome.
    let output: CapabilityOutput<C>;
    try {
      output = await options.execute(state, args, call);
      const problems = outputProblems(capability, output);
      if (problems.length > 0) throw new Error(problems.join('; '));
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      await serially(state.threadId, () => completeTrace(state, started, { at: now(), status: 'failed', error: message }));
      return { status: 'error', error: message };
    }

    const anchors = output['evidence_anchors'];
    await serially(state.threadId, async () => {
      const entry = await completeTrace(state, started, {
        at: now(),
        status: 'executed',
        ...(Array.isArray(anchors) ? { evidence_anchors: anchors } : {}),
      });
      if (capability === 'checkpoint') {
        const id = typeof output['checkpoint_id'] === 'string' ? output['checkpoint_id'] : `checkpoint-${entry.seq}`;
        const checkpoints = await readCheckpoints(state);
        await state.setValue(KEYS.checkpoints, [
          ...checkpoints,
          { id, valid: true, seq: entry.seq, at: entry.at, flow_id: flow },
        ]);
      }
    });

    return { status: 'success', result: JSON.stringify(output) };
  };

  const definition = defineTool<ThreadState, Args>({
    description: options.description,
    args: options.args,
    annotations: { ...options.annotations, [ANNOTATION_KEY]: annotation },
    ...(options.variables !== undefined ? { variables: options.variables } : {}),
    ...(options.progressArgument !== undefined ? { progressArgument: options.progressArgument } : {}),
    // `UsesAwareExecute` is a conditional type on `Args`, which TypeScript
    // cannot resolve while `Args` is still generic; for any concrete `Args`
    // it is exactly the signature of `execute` above.
    execute: execute as UsesAwareExecute<ThreadState, Args, readonly string[]>,
  });
  STATED_NAMES.set(definition, name);
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
