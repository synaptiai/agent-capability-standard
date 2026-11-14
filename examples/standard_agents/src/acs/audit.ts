/**
 * The audit side of the binding: one trace entry for every tool call in a
 * thread, whether or not the tool is grounded.
 *
 * A function tool cannot see its own call id, and a hook cannot see what the
 * tool recorded, so the two halves are joined here. The `tool_call_done`
 * hook gives each entry a grounded tool wrote the id of the call that
 * produced it, and writes an entry of its own for a call no grounded tool
 * recorded. Matching is by tool name, oldest first, which is right because a
 * runtime executes tool calls "sequentially in the order they were returned"
 * (Tools, Conformance Notes).
 *
 * An entry still `started` belongs to a call that was cut off while its tool
 * ran. A finished entry of the same tool is matched before it, and it then
 * stops waiting, so a cut-off call never takes the id of a later one.
 */
import type { HookToolCall, HookToolResult } from '@standardagents/spec';
import { KEYS, appendTrace, type Store, type TraceEntry, type Unlinked } from './records.js';

/** Record that a tool call finished. Call it from a `tool_call_done` hook. */
export async function recordToolCall(
  store: Store,
  toolCall: HookToolCall,
  toolResult: Pick<HookToolResult, 'status' | 'error'>,
  now: number,
): Promise<TraceEntry> {
  const name = toolCall.function.name;
  const unlinked = (await store.getValue<Unlinked[]>(KEYS.unlinked)) ?? [];
  const cutOff: Unlinked[] = [];
  let match: { waiting: Unlinked; entry: TraceEntry } | undefined;
  for (const waiting of unlinked.filter((u) => u.action === name)) {
    const entry = await store.getValue<TraceEntry>(KEYS.trace(waiting.seq));
    if (entry && entry.status !== 'started') {
      match = { waiting, entry };
      break;
    }
    cutOff.push(waiting);
  }
  // With no finished entry, the call that is done is itself a cut-off one.
  const oldest = cutOff[0];
  if (!match && oldest) {
    const entry = await store.getValue<TraceEntry>(KEYS.trace(oldest.seq));
    if (entry) match = { waiting: oldest, entry };
  }
  if (match) {
    const settled = new Set<Unlinked>([match.waiting, ...cutOff.filter((u) => u.seq < match.waiting.seq)]);
    await store.setValue(
      KEYS.unlinked,
      unlinked.filter((u) => !settled.has(u)),
    );
    const linked: TraceEntry = { ...match.entry, tool_call_id: toolCall.id };
    await store.setValue(KEYS.trace(linked.seq), linked);
    return linked;
  }
  return appendTrace(store, {
    at: now,
    action: name,
    capability: null,
    status: toolResult.status === 'success' ? 'executed' : 'failed',
    tool_call_id: toolCall.id,
    ...(toolResult.error !== undefined ? { error: toolResult.error } : {}),
  });
}
