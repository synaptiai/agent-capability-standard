/**
 * Nested calls are attributed by one-shot nesting tokens (STANDARD 1.2.0
 * §5.18.4): a call is covered by a composite's approval and checkpoint only
 * when it takes the token of a pending invocation the composite's own code
 * made, in the same execution, of the same tool, with the same arguments.
 * Same thread or execution is not evidence.
 */
import { defineTool, type ThreadUser, type ToolResult } from '@standardagents/spec';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { decideApproval, requestApproval, type ApprovalPolicy } from '../src/acs/approval.js';
import { groundedTool } from '../src/acs/grounded.js';
import { configureLayer, resetLayer } from '../src/acs/layer.js';
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
    // A bound tool: the refusal and its record name its capability, and the
    // record names the layer that decided it (§5.18.8).
    expect(refused).toMatchObject({ action: 'write', capability: 'mutate', status: 'refused' });
    expect(refused?.recorded_by).toMatchObject({ name: '@acs/standard-agents-binding', version: '1.2.0' });
    expect(refused?.recorded_by?.config_sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(nestedResults[0]?.error_data).toMatchObject({ location: { tool: 'write', capability: 'mutate' } });
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

// A composite may list a tool defined with plain defineTool that carries a
// binding record (an `acs` annotation): the layer sees the invocation, so it
// checks and records the nested call itself (STANDARD 1.2.0 §5.18.4,
// §4.4.2, §5.18.8). One with no binding the layer loads is V107.
describe('nested calls of a tool the binding did not define (security round 1, batch 5)', () => {
  const args = z.object({}).passthrough();
  const recordOf = (record: Record<string, unknown>) => ({ acs: { standard: '1.2.0', ontology: '2.2.0', ...record } });

  function relaySetup(notifyRecord: Record<string, unknown> | null) {
    const t = memoryThread();
    const sent: string[] = [];
    const save = groundedTool({
      name: 'save',
      capability: 'checkpoint',
      description: 'save',
      args,
      execute: async (_s, _a, call) => ({ checkpoint_id: `cp-${call.seq}`, evidence_anchors: [] }),
    });
    const notify = defineTool({
      description: 'notify',
      args,
      ...(notifyRecord !== null ? { annotations: recordOf(notifyRecord) } : {}),
      execute: async (_s: unknown, a: Record<string, unknown>) => {
        sent.push(String(a['to']));
        return { status: 'success' as const, result: 'ok' };
      },
    });
    const relay = () =>
      groundedTool({
        name: 'relay',
        capability: 'invoke',
        invokes: { notify } as never,
        description: 'relay',
        args,
        execute: async (state, a) => {
          const result = await state.invokeTool('notify', { to: (a as { to: string }).to });
          return { result: result.error_code ?? result.status, evidence_anchors: [] };
        },
      });
    return { t, sent, save, notify, relay };
  }

  it('checks a nested send of a binding record against the destination policies in force, and records it', async () => {
    configureLayer({ destinations: [['https://hooks.example.com/*']] });
    try {
      const { t, sent, save, notify, relay } = relaySetup({ tool: 'notify', capability: 'send', destination: '/to' });
      const composite = relay();
      for (const [name, tool] of Object.entries({ save, notify, relay: composite })) t.tools.set(name, tool as never);
      for (const [to, outcome] of [
        ['https://attacker.example.net/exfil?d=secret', 'F504'],
        ['https://hooks.example.com/a', 'success'],
      ] as const) {
        await run(t, 'save');
        await approve(t, 'relay', 'invoke', { to });
        const result = await run(t, 'relay', { to });
        expect(result.status).toBe('success');
        expect(String(result.result)).toContain(outcome);
      }
      // Only the allowed destination was sent to.
      expect(sent).toEqual(['https://hooks.example.com/a']);
      const trace = await readTrace(t.state);
      const relays = trace.filter((e) => e.action === 'relay').map((e) => e.seq);
      expect(trace.filter((e) => e.action === 'notify').map((e) => [e.status, e.code ?? null, e.covered_by, e.capability])).toEqual([
        ['refused', 'F504', relays[0], 'send'],
        ['executed', null, relays[1], 'send'],
      ]);
    } finally {
      resetLayer();
    }
  });

  it('refuses a nested send whose binding names no destination argument under a policy', async () => {
    configureLayer({ destinations: [['https://hooks.example.com/*']] });
    try {
      const { t, sent, save, notify, relay } = relaySetup({ tool: 'notify', capability: 'send' });
      for (const [name, tool] of Object.entries({ save, notify, relay: relay() })) t.tools.set(name, tool as never);
      await run(t, 'save');
      const to = 'https://hooks.example.com/a';
      await approve(t, 'relay', 'invoke', { to });
      expect(String((await run(t, 'relay', { to })).result)).toContain('F504');
      expect(sent).toEqual([]);
    } finally {
      resetLayer();
    }
  });

  it('records a nested call of a binding record with no policy in force', async () => {
    const { t, sent, save, notify, relay } = relaySetup({ tool: 'notify', capability: 'send', destination: '/to' });
    for (const [name, tool] of Object.entries({ save, notify, relay: relay() })) t.tools.set(name, tool as never);
    await run(t, 'save');
    const to = 'https://anywhere.example/x';
    await approve(t, 'relay', 'invoke', { to });
    expect((await run(t, 'relay', { to })).status).toBe('success');
    expect(sent).toEqual([to]);
    const trace = await readTrace(t.state);
    const covering = trace.find((e) => e.action === 'relay')!.seq;
    expect(trace.find((e) => e.action === 'notify')).toMatchObject({ status: 'executed', covered_by: covering, capability: 'send' });
  });

  it('does not define a composite that lists a tool with no binding the layer loads (V107)', () => {
    for (const record of [null, { capability: 'teleport' }, { tool: 'notify', capability: 'invoke', invokes: ['other'] }]) {
      const { relay } = relaySetup(record);
      expect(relay).toThrow(/V107 UNRESOLVED_TARGET: it invokes 'notify'/);
    }
  });
});

// A composite's approval covers its nested calls only where it is a decision
// valid for each of them (STANDARD 1.2.0 §5.18.4, §5.18.7): the composite
// asks for the strictest approval of the tools it invokes, and a nested call
// whose own approval its decisions do not meet is checked on its own.
describe("a composite takes the approval of the tools it invokes (security round 1, batch 5)", () => {
  const args = z.object({}).passthrough();
  const KEY = { key: 'prod/db' };

  function prodSetup(batchApproval: ApprovalPolicy = {}) {
    let clock = Date.UTC(2026, 10, 17);
    const t = memoryThread();
    const writes: unknown[] = [];
    const now = () => clock;
    const save = groundedTool({
      name: 'save',
      capability: 'checkpoint',
      description: 'save',
      args,
      now,
      execute: async (_s, _a, call) => ({ checkpoint_id: `cp-${call.seq}`, evidence_anchors: [] }),
    });
    const writeProd = groundedTool({
      name: 'write_prod',
      capability: 'mutate',
      description: 'write_prod',
      args,
      now,
      approval: { role: 'admin', min_approvers: 2, expires_ms: 60_000 },
      execute: async (_s, a) => {
        writes.push(a);
        return { success: true, evidence_anchors: [] };
      },
    });
    const nested: ToolResult[] = [];
    const composite = (name: string, invoked: string, tool: unknown, approval: ApprovalPolicy = {}) =>
      groundedTool({
        name,
        capability: 'invoke',
        invokes: { [invoked]: tool } as never,
        description: name,
        args,
        now,
        approval,
        execute: async (state, a) => {
          nested.push(await state.invokeTool(invoked, a as Record<string, unknown>));
          return { result: true, evidence_anchors: [] };
        },
      });
    const batch = composite('batch', 'write_prod', writeProd, batchApproval);
    const outer = composite('outer', 'batch', batch);
    for (const [name, tool] of Object.entries({ save, write_prod: writeProd, batch, outer })) t.tools.set(name, tool);
    const decide = async (action: string, who: ThreadUser[], policy: ApprovalPolicy) => {
      const request = await requestApproval(t.state, [{ action, capability: 'invoke', args: KEY }], policy, clock);
      for (const u of who) await decideApproval(t.state, u, request.digest, 'approved', clock);
    };
    return { t, writes, nested, decide, tick: (ms: number) => (clock += ms) };
  }

  const ADMIN = { role: 'admin', min_approvers: 2, expires_ms: 60_000 };

  it('asks a composite for the role, approvers and expiry of a tool it invokes, transitively', async () => {
    const { t, writes, decide } = prodSetup();
    await run(t, 'save');
    // bob, who holds no role, approves batch as if it needed no more.
    await decide('batch', [user('bob')], {});
    expect((await run(t, 'batch', KEY)).error_code).toBe('F502');
    // Decided under the joined policy, bob is not allowed to decide at all.
    await expect(decide('batch', [user('bob')], ADMIN)).rejects.toThrow(/role 'admin'/);
    // The composite enclosing it asks the same.
    await decide('outer', [user('bob')], {});
    expect((await run(t, 'outer', KEY)).error_code).toBe('F502');
    expect(writes).toEqual([]);
    // Two admins approve batch: it runs, and covers the nested write.
    await decide('batch', [user('ann', ['admin']), user('al', ['admin'])], ADMIN);
    expect((await run(t, 'batch', KEY)).status).toBe('success');
    expect(writes).toEqual([KEY]);
    const trace = await readTrace(t.state);
    const covering = trace.filter((e) => e.action === 'batch').at(-1)!.seq;
    expect(trace.filter((e) => e.action === 'write_prod').at(-1)).toMatchObject({ status: 'executed', covered_by: covering });
  });

  it('checks a nested call on its own when the decisions that approved the composite are not valid for it', async () => {
    // batch sets a role of its own, so it asks ops, not admin: its approval
    // does not cover write_prod, which is checked on its own.
    const { t, writes, nested, decide } = prodSetup({ role: 'ops' });
    await run(t, 'save');
    const policy = { role: 'ops', min_approvers: 2, expires_ms: 60_000 };
    await decide('batch', [user('carol', ['ops']), user('cy', ['ops'])], policy);
    expect((await run(t, 'batch', KEY)).status).toBe('success');
    expect(nested.at(-1)?.error_code).toBe('F502');
    expect(writes).toEqual([]);
    // Valid for write_prod at the composite's start, lapsed by the nested call.
    const both = prodSetup();
    await both.t.tools.get('save')!.execute(both.t.state, {});
    await both.decide('batch', [user('ann', ['admin']), user('al', ['admin'])], ADMIN);
    both.tick(61_000);
    expect((await both.t.tools.get('batch')!.execute(both.t.state, KEY)).error_code).toBe('F502');
  });
});
