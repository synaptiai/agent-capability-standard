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
  const match = unlinked.find((u) => u.action === name);
  if (match) {
    const entry = await store.getValue<TraceEntry>(KEYS.trace(match.seq));
    await store.setValue(
      KEYS.unlinked,
      unlinked.filter((u) => u !== match),
    );
    if (entry) {
      const linked: TraceEntry = { ...entry, tool_call_id: toolCall.id };
      await store.setValue(KEYS.trace(match.seq), linked);
      return linked;
    }
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
