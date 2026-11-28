/**
 * The audit side of the binding: one trace entry for every tool call in a
 * thread, whether or not the tool is grounded.
 *
 * A function tool cannot see its own call id, and a hook cannot see what the
 * tool recorded, so the two halves are joined here. The `tool_call_done`
 * hook gives each entry a grounded tool wrote the id of the call that
 * produced it, and writes an entry of its own for a call no grounded tool
 * recorded.
 *
 * Matching is by tool name among the entries of the hook's own execution and
 * model step (`flowId` and `stepCount`), oldest first. A runtime executes
 * tool calls "sequentially in the order they were returned" (Tools,
 * Conformance Notes), and no model step starts between a call and its hook,
 * so within a step the calls finish in the order their entries were written.
 * An entry of an earlier step or execution belongs to a call whose hook did
 * not run (a hook failure is non-fatal, and a runtime may time hooks out):
 * it keeps no call id rather than taking the id of a later call. Within one
 * step such an entry cannot be told apart: the next call of the same tool in
 * that step gives its id to it, and that call's own entry keeps none. A call
 * made outside an execution, as from a thread endpoint, drops no entry that
 * is waiting.
 *
 * An entry still `started` belongs to a call that was cut off while its tool
 * ran. Within the step, a finished entry of the same tool is matched before
 * it, and the cut-off entry then stops waiting; when there is none, the call
 * reported done is the cut-off one itself. A hook delivered twice for one
 * call adds nothing.
 *
 * An entry a composite's state wrote (a nested call, or a call made while
 * the composite's invocation of the tool was pending) is linked only while
 * the composite's own entry waits: a runtime that fires the hook for an
 * invocation fires it while the composite runs, and once the composite's
 * hook has come, a later call of the same tool the model made in that step
 * takes its own entry, not the nested call's, which keeps no call id.
 * This relies on the order the rest of the matching relies on: the calls
 * of a step run one after another, each hook before the next call. A hook
 * of the model's own call that came while a composite's entry still waits
 * would take a finished nested entry of the same tool, and a model's call
 * that ran while a composite's invocation of the tool was pending would be
 * taken for a nested one.
 *
 * An entry the hook writes is redacted (§6.7) with the default patterns,
 * the secrets registered layer-wide (`configureLayer({ secrets })` and each
 * grounded tool's `secrets`, which join them) and any `secrets` the hook
 * passes: a plain tool's error can carry the credential it was refused
 * with, and the name the model called can be one (a model under a prompt
 * injection can name a tool with a secret to put it in the records). Names
 * are matched redacted: an entry keeps only the redacted name, and so does
 * the list of entries waiting for their call id.
 */
import type { HookToolCall, HookToolResult, ThreadState } from '@standardagents/spec';
import {
  KEYS,
  appendTrace,
  flowOf,
  redactedName,
  samePosition,
  stale,
  stepOf,
  withoutOrphans,
  type Store,
  type TraceEntry,
  type Unlinked,
} from './records.js';
import { serially } from './serial.js';

/** What the hook may add to the layer's configuration. */
export interface RecordToolCallOptions {
  /** The host's own secrets (§6.7), beside those registered layer-wide. */
  secrets?: readonly string[];
}

/** Record that a tool call finished. Call it from a `tool_call_done` hook. */
export async function recordToolCall(
  state: Store & Pick<ThreadState, 'threadId' | 'execution'>,
  toolCall: HookToolCall,
  toolResult: Pick<HookToolResult, 'status' | 'error'>,
  now: number,
  options: RecordToolCallOptions = {},
): Promise<TraceEntry> {
  return serially(state.threadId, async () => {
    const known = await state.getValue<number>(KEYS.call(toolCall.id));
    const linkedBefore = known === null ? null : await state.getValue<TraceEntry>(KEYS.trace(known));
    if (linkedBefore) return linkedBefore;

    const flow = flowOf(state);
    const step = stepOf(state);
    // The name the model called, which may hold a secret (§6.7): entries
    // keep it redacted, so it is compared redacted, with the same secrets
    // on both sides (an entry a grounded tool wrote was redacted with its
    // own, which joined the layer's).
    const secrets = options.secrets ?? [];
    const name = redactedName(toolCall.function.name, secrets);
    const unlinked = (await state.getValue<Unlinked[]>(KEYS.unlinked)) ?? [];
    // A nested call's entry whose composite no longer waits belongs to no
    // hook (`withoutOrphans`): this call is not that one.
    const here = withoutOrphans(unlinked).filter((u) => samePosition(u, flow, step));
    const cutOff: Unlinked[] = [];
    let match: { waiting: Unlinked; entry: TraceEntry } | undefined;
    for (const waiting of here.filter((u) => redactedName(u.action, secrets) === name)) {
      const entry = await state.getValue<TraceEntry>(KEYS.trace(waiting.seq));
      if (entry && entry.status !== 'started') {
        match = { waiting, entry };
        break;
      }
      cutOff.push(waiting);
    }
    // With no finished entry, the call that is done is itself a cut-off one.
    const oldest = cutOff[0];
    if (!match && oldest) {
      const entry = await state.getValue<TraceEntry>(KEYS.trace(oldest.seq));
      if (entry) match = { waiting: oldest, entry };
    }

    // The matched entry and the cut-off ones before it stop waiting. Entries
    // of other steps are dropped too: no later hook can link them.
    const settled = new Set<Unlinked>();
    if (match) {
      settled.add(match.waiting);
      for (const waiting of cutOff) if (waiting.seq < match.waiting.seq) settled.add(waiting);
    }
    // So do the entries of the nested calls of a composite this hook linked.
    const remaining = withoutOrphans(unlinked.filter((u) => !settled.has(u) && !stale(u, flow, step)));
    if (remaining.length !== unlinked.length) await state.setValue(KEYS.unlinked, remaining);

    let linked: TraceEntry;
    if (match) {
      linked = { ...match.entry, tool_call_id: toolCall.id };
      await state.setValue(KEYS.trace(linked.seq), linked);
    } else {
      linked = await appendTrace(
        state,
        {
          at: now,
          ...(flow !== null ? { flow_id: flow } : {}),
          ...(step !== null ? { step } : {}),
          action: name,
          capability: null,
          status: toolResult.status === 'success' ? 'executed' : 'failed',
          tool_call_id: toolCall.id,
          ...(toolResult.error !== undefined ? { error: toolResult.error } : {}),
        },
        secrets,
      );
    }
    await state.setValue(KEYS.call(toolCall.id), linked.seq);
    return linked;
  });
}
