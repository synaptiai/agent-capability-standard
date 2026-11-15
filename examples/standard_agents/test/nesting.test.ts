/**
 * Nested calls are attributed by one-shot nesting tokens (STANDARD 1.2.0
 * §5.18.4): a call is covered by a composite's approval and checkpoint only
 * when it takes the token of a pending invocation the composite's own code
 * made, in the same execution, of the same tool, with the same arguments.
 * Same thread or execution is not evidence.
 */
import type { ToolResult } from '@standardagents/spec';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { decideApproval, requestApproval } from '../src/acs/approval.js';
import { groundedTool } from '../src/acs/grounded.js';
import { readTrace } from '../src/acs/records.js';
import { memoryThread, user, type MemoryThread } from './memory_thread.js';

const A = { path: 'a' };
const B = { path: 'b' };

function deferred(): { promise: Promise<void>; release: () => void } {
  let release!: () => void;
  const promise = new Promise<void>((resolve) => (release = resolve));
  return { promise, release };
}

function setup() {
  const t = memoryThread();
  const args = z.object({}).passthrough();
  const save = groundedTool({
    name: 'save',
    capability: 'checkpoint',
    description: 'save',
    args,
    execute: async (_s, _a, call) => ({ checkpoint_id: `cp-${call.seq}`, evidence_anchors: [] }),
  });
  const write = groundedTool({
    name: 'write',
    capability: 'mutate',
    description: 'write',
    args,
    execute: async () => ({ success: true, evidence_anchors: [] }),
  });
  const undo = groundedTool({
    name: 'undo',
    capability: 'rollback',
    description: 'undo',
    args,
    execute: async () => ({ restored: true, evidence_anchors: [] }),
  });
  const nestedResults: ToolResult[] = [];
  const composite = (name: string, invoked: string, nestedArgs: Record<string, unknown>, invokes: Record<string, never>) =>
    groundedTool({
      name,
      capability: 'invoke',
      invokes,
      description: name,
      args,
      execute: async (state) => {
        nestedResults.push(await state.invokeTool(invoked, nestedArgs));
        return { result: true, evidence_anchors: [] };
      },
    });
  const batch = composite('batch', 'write', A, { write } as never);
  const batchB = composite('batch_b', 'write', B, { write } as never);
  const fix = composite('fix', 'undo', {}, { undo } as never);
  const solo = composite('solo', 'write', A, {});
  for (const [name, tool] of Object.entries({ save, write, undo, batch, batch_b: batchB, fix, solo })) t.tools.set(name, tool);
  return { t, nestedResults };
}

async function approve(t: MemoryThread, action: string, capability: string, args: Record<string, unknown>): Promise<void> {
  const request = await requestApproval(t.state, [{ action, capability, args: args as never }], {}, Date.now());
  await decideApproval(t.state, user('alice'), request.digest, 'approved', Date.now());
}

const run = (t: MemoryThread, name: string, args: Record<string, unknown> = {}) => t.tools.get(name)!.execute(t.state, args);

describe('nesting tokens', () => {
  it('covers the composite own invocation, and records which call covered it', async () => {
    const { t, nestedResults } = setup();
    await run(t, 'save');
    await approve(t, 'batch', 'invoke', A);
    expect((await run(t, 'batch', A)).status).toBe('success');
    expect(nestedResults[0]?.status).toBe('success');
    const trace = await readTrace(t.state);
    const batchEntry = trace.find((e) => e.action === 'batch')!;
    expect(trace.find((e) => e.action === 'write')).toMatchObject({ status: 'executed', covered_by: batchEntry.seq });
  });

  it('(a) does not cover a call an endpoint makes while the composite runs', async () => {
    const { t, nestedResults } = setup();
    const gate = deferred();
    t.beforeInvoke = () => gate.promise;
    await run(t, 'save');
    await approve(t, 'batch', 'invoke', A);
    const pending = run(t, 'batch', A);
    await expect.poll(() => t.invoked.length).toBe(1);
    const fromEndpoint = await t.tools.get('write')!.execute(t.endpointState(), A);
    expect(fromEndpoint.error_code).toBe('F502');
    gate.release();
    expect((await pending).status).toBe('success');
    expect(nestedResults[0]?.status).toBe('success');
  });

  it('(b) does not cover a parallel sibling call with other arguments', async () => {
    const { t } = setup();
    const gate = deferred();
    t.beforeInvoke = () => gate.promise;
    await run(t, 'save');
    await approve(t, 'batch', 'invoke', A);
    await approve(t, 'write', 'mutate', B);
    const pending = run(t, 'batch', A);
    await expect.poll(() => t.invoked.length).toBe(1);
    // The only checkpoint went to batch: the sibling is checked on its own.
    expect((await t.siblingCall('write', B)).error_code).toBe('F501');
    gate.release();
    await pending;
  });

  it('(c) lets a sibling with exactly the pending arguments take the one covered call', async () => {
    const { t, nestedResults } = setup();
    const gate = deferred();
    t.beforeInvoke = () => gate.promise;
    await run(t, 'save');
    await approve(t, 'batch', 'invoke', A);
    await approve(t, 'write', 'mutate', A);
    const pending = run(t, 'batch', A);
    await expect.poll(() => t.invoked.length).toBe(1);
    expect((await t.siblingCall('write', A)).status).toBe('success');
    gate.release();
    await pending;
    // batch's own invocation found its token taken: checked on its own.
    expect(nestedResults[0]?.error_code).toBe('F501');
  });

  it('(d) keeps a nested call prerequisites: a covered rollback with no checkpoint ever taken is F503', async () => {
    const { t, nestedResults } = setup();
    expect((await run(t, 'fix')).status).toBe('success');
    expect(nestedResults[0]?.error_code).toBe('F503');
  });

  it('(e) refuses an invocation of a tool the composite does not list, without calling the runtime', async () => {
    const { t, nestedResults } = setup();
    expect((await run(t, 'solo', A)).status).toBe('success');
    expect(nestedResults[0]?.error_code).toBe('F504');
    expect(t.invoked).toEqual([]);
    const refused = (await readTrace(t.state)).find((e) => e.code === 'F504');
    expect(refused).toMatchObject({ action: 'write', status: 'refused' });
  });

  it('(f) leaves no token once the composite returns', async () => {
    const { t } = setup();
    await run(t, 'save');
    await approve(t, 'batch', 'invoke', A);
    await run(t, 'batch', A);
    // A later write with the same arguments is checked on its own.
    expect((await run(t, 'write', A)).error_code).toBe('F502');
  });

  it('(g) two composites on one thread remove only their own tokens', async () => {
    const { t, nestedResults } = setup();
    const gates = new Map([
      ['a', deferred()],
      ['b', deferred()],
    ]);
    t.beforeInvoke = (_name, args) => gates.get(String(args['path']))!.promise;
    await run(t, 'save');
    await run(t, 'save');
    await approve(t, 'batch', 'invoke', A);
    await approve(t, 'batch_b', 'invoke', B);
    const first = run(t, 'batch', A);
    const second = t.siblingCall('batch_b', B);
    await expect.poll(() => t.invoked.length).toBe(2);
    gates.get('a')!.release();
    await first;
    gates.get('b')!.release();
    await second;
    expect(nestedResults.map((r) => r.status)).toEqual(['success', 'success']);
  });

  it('declares uses only for a tool with invokes', () => {
    const { t } = setup();
    expect((t.tools.get('batch') as { uses?: readonly string[] }).uses).toEqual(['write']);
    expect((t.tools.get('write') as { uses?: readonly string[] }).uses).toBeUndefined();
  });
});
