import { validateAgentDefinition, type HookToolCall, type PackedExports, type ToolResult } from '@standardagents/spec';
import { Ajv2020 } from 'ajv/dist/2020.js';
import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import approvalsGet from '../agents/api/acs/approvals.get.js';
import approvalsPost from '../agents/api/acs/approvals.post.js';
import configSteward from '../agents/agents/config_steward.js';
import auditHook from '../agents/hooks/acs_audit_tool_calls.js';
import prompt from '../agents/prompts/config_steward.js';
import checkpointConfig from '../agents/tools/checkpoint_config.js';
import readConfig from '../agents/tools/read_config.js';
import rollbackConfig from '../agents/tools/rollback_config.js';
import verifyConfig from '../agents/tools/verify_config.js';
import writeConfig from '../agents/tools/write_config.js';
import { approvalState, decideApproval, readApproval, type ApprovalPolicy } from '../src/acs/approval.js';
import { digest } from '../src/acs/canonical.js';
import { ANNOTATION_KEY, CHECKPOINT_MAX_AGE_MS, acsAnnotation, groundedTool } from '../src/acs/grounded.js';
import { lintAgentBindings, lintPromptTools } from '../src/acs/lint.js';
import { CAPABILITIES, ONTOLOGY_VERSION, STANDARD_VERSION, effectiveFlags } from '../src/acs/ontology.js';
import { readCheckpoints, readTrace } from '../src/acs/records.js';
import { SETTINGS_PATH } from '../src/example/settings.js';
import annotationSchema from '../../../schemas/interop/standard_agents_annotation.schema.json' with { type: 'json' };
import manifest from '../package.json' with { type: 'json' };
import { memoryThread, user, type MemoryThread } from './memory_thread.js';

const CHANGE = { key: 'retries', value: '5' };

function thread(): MemoryThread {
  const t = memoryThread();
  t.files.set(SETTINGS_PATH, '{"retries":"3"}');
  return t;
}

function data(result: ToolResult): Record<string, unknown> {
  expect(result.status, result.error).toBe('success');
  return JSON.parse(result.result ?? 'null') as Record<string, unknown>;
}

/** The digest an approver decides on, as the refused call reported it. */
function digestOf(result: ToolResult): string {
  expect(result.error_code).toBe('F502');
  return result.error_data?.['digest'] as string;
}

/** Wait until a call that will never return has written its `started` entry. */
async function started(t: MemoryThread): Promise<void> {
  await vi.waitFor(async () => expect((await readTrace(t.state)).at(-1)?.status).toBe('started'));
}

async function post(t: MemoryThread, caller: ReturnType<typeof user> | null, body: unknown): Promise<Response> {
  const request = new Request('https://runtime.example/threads/thread-1/acs/approvals', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  return approvalsPost(request, t.state, {}, { caller, threadAccess: caller !== null });
}

describe('classification', () => {
  it('annotates each tool with its capability and effective flags', () => {
    expect(acsAnnotation(writeConfig)).toEqual({
      standard: STANDARD_VERSION,
      ontology: ONTOLOGY_VERSION,
      capability: 'mutate',
      layer: 'EXECUTE',
      domain: 'config',
      risk: 'high',
      mutation: true,
      requires_checkpoint: true,
      requires_approval: true,
    });
    expect(acsAnnotation(readConfig)).toMatchObject({ capability: 'retrieve', risk: 'low', mutation: false });
  });

  it("keeps other owners' annotation keys", () => {
    const tool = groundedTool({
      name: 'noop',
      capability: 'observe',
      description: 'Observe nothing.',
      args: z.object({}),
      annotations: { agentbuilder: { codemode: { language: 'typescript' } } },
      execute: async () => ({ observation: null, evidence_anchors: [], confidence: 1 }),
    });
    expect(Object.keys(tool.annotations ?? {})).toEqual(['agentbuilder', ANNOTATION_KEY]);
  });

  it('takes flags from the ontology, and lets a tool only raise them', () => {
    expect(effectiveFlags('mutate').flags).toMatchObject({ requires_checkpoint: true, requires_approval: true });
    expect(effectiveFlags('observe', { requires_approval: true }).flags.requires_approval).toBe(true);
    expect(effectiveFlags('mutate', { risk: 'low' })).toMatchObject({ flags: { risk: 'high' } });
    expect(effectiveFlags('mutate', { risk: 'low' }).warnings[0]).toMatch(/^W602/);
    expect(effectiveFlags('audit', { mutation: false }).flags.mutation).toBe(false);
    expect(effectiveFlags('persist', { mutation: false }).flags.mutation).toBe(true);
  });

  it('refuses to define a tool that declares weaker flags', () => {
    expect(() =>
      groundedTool({
        name: 'quiet_write',
        capability: 'mutate',
        flags: { risk: 'low' },
        description: 'x',
        args: z.object({}),
        execute: async () => ({ success: true, evidence_anchors: [] }),
      }),
    ).toThrow(/W602/);
  });
});

/** Ask for the change, and have `who` approve it. Returns the digest. */
async function approve(t: MemoryThread, args = CHANGE, who = 'alice'): Promise<string> {
  const d = digestOf(await writeConfig.execute(t.state, args));
  await decideApproval(t.state, user(who), d, 'approved', Date.now());
  return d;
}

describe('checkpoint before mutation', () => {
  it('refuses an approved mutation when no checkpoint has run, and keeps the approval', async () => {
    const t = thread();
    const d = await approve(t);

    const result = await writeConfig.execute(t.state, CHANGE);
    expect(result).toMatchObject({ status: 'error', error_code: 'F501' });
    expect(result.error_data).toMatchObject({
      code: 'F501',
      name: 'CHECKPOINT_REQUIRED',
      severity: 'error',
      location: { tool: 'write_config', capability: 'mutate' },
    });
    expect(t.files.get(SETTINGS_PATH)).toBe('{"retries":"3"}');
    expect((await readApproval(t.state, d))?.used_at).toBeUndefined();

    // The restore point is taken after the approval, just before the change.
    await checkpointConfig.execute(t.state, { label: 'before change' });
    data(await writeConfig.execute(t.state, CHANGE));
    expect(JSON.parse(t.files.get(SETTINGS_PATH) ?? '')).toEqual({ retries: '5' });
  });

  it('does not accept a checkpoint taken before the thread last went idle', async () => {
    const t = thread();
    await checkpointConfig.execute(t.state, { label: 'taken too early' });
    await approve(t);

    // The thread waited for the person; the approved call runs in a new execution.
    t.newExecution();
    const result = await writeConfig.execute(t.state, CHANGE);
    expect(result).toMatchObject({ status: 'error', error_code: 'F501' });
    expect(result.error).toMatch(/before this thread last went idle/);
    expect(t.files.get(SETTINGS_PATH)).toBe('{"retries":"3"}');

    await checkpointConfig.execute(t.state, { label: 'just before the change' });
    data(await writeConfig.execute(t.state, CHANGE));
    expect((await readTrace(t.state)).at(-1)).toMatchObject({ flow_id: 'flow-2', checkpoint_id: 'cp-4' });
  });

  it('does not accept a checkpoint that is too old, or any outside an execution', async () => {
    let clock = 0;
    const now = () => clock;
    const anchors = { evidence_anchors: [] };
    const save = groundedTool({
      name: 'save',
      capability: 'checkpoint',
      description: 'x',
      args: z.object({}),
      now,
      execute: async (_state, _args, call) => ({ checkpoint_id: `cp-${call.seq}`, ...anchors }),
    });
    const store = groundedTool({
      name: 'store',
      capability: 'persist',
      flags: { requires_checkpoint: true },
      description: 'x',
      args: z.object({}),
      now,
      execute: async () => ({ stored: true, ...anchors }),
    });
    const t = thread();

    // In one execution: valid at ten minutes, refused a millisecond later.
    await save.execute(t.state, {});
    clock = CHECKPOINT_MAX_AGE_MS + 1;
    expect((await store.execute(t.state, {})).error).toMatch(/too long ago/);
    await save.execute(t.state, {});
    clock += CHECKPOINT_MAX_AGE_MS;
    data(await store.execute(t.state, {}));

    // Outside an execution there is no flow to tie a checkpoint to.
    t.atRest();
    await save.execute(t.state, {});
    const result = await store.execute(t.state, {});
    expect(result).toMatchObject({ status: 'error', error_code: 'F501' });
    expect(result.error).toMatch(/not part of an execution/);
  });

  it('lets a tool shorten the time a checkpoint counts, never lengthen it', async () => {
    const define = (checkpoint_max_age_ms: number) =>
      groundedTool({
        name: 'store',
        capability: 'persist',
        flags: { requires_checkpoint: true },
        description: 'x',
        args: z.object({}),
        checkpoint_max_age_ms,
        execute: async () => ({ stored: true, evidence_anchors: [] }),
      });
    for (const age of [CHECKPOINT_MAX_AGE_MS + 1, Number.POSITIVE_INFINITY, 0, -1, Number.NaN]) {
      expect(() => define(age), String(age)).toThrow(/checkpoint_max_age_ms/);
    }
    expect(() => define(CHECKPOINT_MAX_AGE_MS)).not.toThrow();

    let clock = 0;
    const save = groundedTool({
      name: 'save',
      capability: 'checkpoint',
      description: 'x',
      args: z.object({}),
      now: () => clock,
      execute: async (_state, _args, call) => ({ checkpoint_id: `cp-${call.seq}`, evidence_anchors: [] }),
    });
    const quick = groundedTool({
      name: 'store',
      capability: 'persist',
      flags: { requires_checkpoint: true },
      description: 'x',
      args: z.object({}),
      checkpoint_max_age_ms: 60_000,
      now: () => clock,
      execute: async () => ({ stored: true, evidence_anchors: [] }),
    });
    const t = thread();
    await save.execute(t.state, {});
    clock = 60_001;
    expect((await quick.execute(t.state, {})).error).toMatch(/too long ago/);
  });

  it('refuses a rollback when no checkpoint has run', async () => {
    const t = thread();
    const result = await rollbackConfig.execute(t.state, { checkpoint_id: 'cp-1' });
    expect(result).toMatchObject({ status: 'error', error_code: 'F503' });
  });

  it('uses up one checkpoint per mutation', async () => {
    const t = thread();
    await checkpointConfig.execute(t.state, { label: 'first change' });
    await approve(t);
    data(await writeConfig.execute(t.state, CHANGE));
    expect((await readCheckpoints(t.state)).map((c) => c.valid)).toEqual([false]);

    // A second change, approved, still needs a checkpoint of its own.
    const second = { key: 'retries', value: '9' };
    await approve(t, second);
    const result = await writeConfig.execute(t.state, second);
    expect(result).toMatchObject({ status: 'error', error_code: 'F501' });
    expect(JSON.parse(t.files.get(SETTINGS_PATH) ?? '')).toEqual({ retries: '5' });
  });
});

describe('approval bound to what was shown', () => {
  it('refuses until a person approves, and leaves the checkpoint valid', async () => {
    const t = thread();
    await checkpointConfig.execute(t.state, { label: 'before change' });
    const result = await writeConfig.execute(t.state, CHANGE);

    expect(result).toMatchObject({ status: 'error', error_code: 'F502' });
    const shown = [{ action: 'write_config', capability: 'mutate', args: CHANGE }];
    expect(result.error_data).toMatchObject({ shown, state: 'pending', digest: await digest(shown) });
    expect((await readCheckpoints(t.state)).map((c) => c.valid)).toEqual([true]);
    expect(t.files.get(SETTINGS_PATH)).toBe('{"retries":"3"}');
  });

  it('runs once approved, and an approval is single-use', async () => {
    const t = thread();
    await checkpointConfig.execute(t.state, { label: 'one' });
    const refused = await writeConfig.execute(t.state, CHANGE);
    await decideApproval(t.state, user('alice'), digestOf(refused), 'approved', Date.now());

    const output = data(await writeConfig.execute(t.state, CHANGE));
    expect(output).toMatchObject({ success: true, previous_state: { retries: '3' }, new_state: { retries: '5' } });
    expect((await readApproval(t.state, digestOf(refused)))?.used_at).toBeTypeOf('number');

    // The same change again starts a new request: the old approval is spent.
    await checkpointConfig.execute(t.state, { label: 'two' });
    expect(await writeConfig.execute(t.state, CHANGE)).toMatchObject({ error_code: 'F502' });
  });

  it('does not let an approval for one change authorise another', async () => {
    const t = thread();
    await checkpointConfig.execute(t.state, { label: 'one' });
    const refused = await writeConfig.execute(t.state, CHANGE);
    await decideApproval(t.state, user('alice'), digestOf(refused), 'approved', Date.now());

    const other = await writeConfig.execute(t.state, { key: 'retries', value: '500' });
    expect(other).toMatchObject({ status: 'error', error_code: 'F502' });
    expect(digestOf(other)).not.toBe(digestOf(refused));
    expect(t.files.get(SETTINGS_PATH)).toBe('{"retries":"3"}');
  });

  it('stays refused after a rejection', async () => {
    const t = thread();
    await checkpointConfig.execute(t.state, { label: 'one' });
    const refused = await writeConfig.execute(t.state, CHANGE);
    await decideApproval(t.state, user('alice'), digestOf(refused), 'rejected', Date.now());
    // A rejected request is closed; asking again opens a fresh round and
    // keeps the rejection on record.
    expect(await writeConfig.execute(t.state, CHANGE)).toMatchObject({
      error_code: 'F502',
      error_data: { state: 'pending' },
    });
    const record = await readApproval(t.state, digestOf(refused));
    expect(record?.decisions).toEqual([]);
    expect(record?.history).toEqual([
      expect.objectContaining({ decisions: [expect.objectContaining({ approver: 'alice', decision: 'rejected' })] }),
    ]);
  });

  it('counts distinct approvers, checks the role, and lets approvals expire', async () => {
    let clock = 1_000;
    const tool = groundedTool({
      name: 'release',
      capability: 'execute',
      description: 'Run the release.',
      approval: { min_approvers: 2, role: 'release-manager', expires_ms: 60_000 },
      args: z.object({ version: z.string() }),
      now: () => clock,
      execute: async () => ({ result: 'released', success: true, evidence_anchors: [] }),
    });
    const t = thread();
    const d = digestOf(await tool.execute(t.state, { version: '1.2.0' }));

    await expect(decideApproval(t.state, user('mallory'), d, 'approved', clock)).rejects.toThrow(/release-manager/);
    await decideApproval(t.state, user('alice', ['release-manager']), d, 'approved', clock);
    await expect(decideApproval(t.state, user('alice', ['release-manager']), d, 'approved', clock)).rejects.toThrow(
      /already decided/,
    );
    expect(await tool.execute(t.state, { version: '1.2.0' })).toMatchObject({ error_data: { state: 'pending' } });

    await decideApproval(t.state, user('bob', ['release-manager']), d, 'approved', clock);
    clock += 60_001;
    expect(await tool.execute(t.state, { version: '1.2.0' })).toMatchObject({ error_code: 'F502' });
  });

  it('refuses, when the tool is defined, an approval policy §5.14 does not allow', () => {
    const define = (approval: ApprovalPolicy) => () =>
      groundedTool({
        name: 'release',
        capability: 'execute',
        description: 'Run the release.',
        approval,
        args: z.object({}),
        execute: async () => ({ result: 'released', evidence_anchors: [] }),
      });
    // An unset environment variable read with Number() is NaN, and 0 or less
    // would let the call run on no decision at all.
    for (const min_approvers of [0, -1, 1.5, Number.NaN]) {
      expect(define({ min_approvers }), String(min_approvers)).toThrow(/min_approvers/);
    }
    for (const expires_ms of [0, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(define({ expires_ms }), String(expires_ms)).toThrow(/expires_ms/);
    }
    expect(define({ min_approvers: 2, expires_ms: 1 })).not.toThrow();

    // A stored request with no usable approver count is never approved.
    const record = { digest: 'd', shown: [], min_approvers: 0, requested_at: 0, decisions: [] };
    for (const min_approvers of [0, -1, null as unknown as number]) {
      expect(approvalState({ ...record, min_approvers }, 1), String(min_approvers)).toBe('pending');
    }
  });

  it('accepts no decision after the request has expired, as the reference executor does', async () => {
    let clock = 0;
    const release = (min_approvers: number) =>
      groundedTool({
        name: 'release',
        capability: 'execute',
        description: 'Run the release.',
        approval: { min_approvers, expires_ms: 60_000 },
        args: z.object({ version: z.string() }),
        now: () => clock,
        execute: async () => ({ result: 'released', evidence_anchors: [] }),
      });
    const t = thread();

    // Two approvers: the second decides thirty days after the first.
    const two = release(2);
    const d = digestOf(await two.execute(t.state, { version: '1' }));
    await decideApproval(t.state, user('alice'), d, 'approved', clock);
    clock = 30 * 24 * 60 * 60 * 1000;
    await expect(decideApproval(t.state, user('bob'), d, 'approved', clock)).rejects.toThrow(/expired/);
    expect(await two.execute(t.state, { version: '1' })).toMatchObject({ error_code: 'F502' });

    // One approver, deciding a year after the request was made.
    const one = release(1);
    const stale = digestOf(await one.execute(t.state, { version: '2' }));
    clock += 365 * 24 * 60 * 60 * 1000;
    await expect(decideApproval(t.state, user('alice'), stale, 'approved', clock)).rejects.toThrow(/expired/);
    expect(await one.execute(t.state, { version: '2' })).toMatchObject({ error_code: 'F502' });
  });

  it('keeps an approval given in time valid for the expiry after it was given', async () => {
    let clock = 0;
    const tool = groundedTool({
      name: 'release',
      capability: 'execute',
      description: 'Run the release.',
      approval: { expires_ms: 60_000 },
      args: z.object({ version: z.string() }),
      now: () => clock,
      execute: async () => ({ result: 'released', evidence_anchors: [] }),
    });
    const t = thread();
    const d = digestOf(await tool.execute(t.state, { version: '1' }));
    clock = 59_000;
    await decideApproval(t.state, user('alice'), d, 'approved', clock);
    clock = 119_000;
    data(await tool.execute(t.state, { version: '1' }));

    const late = digestOf(await tool.execute(t.state, { version: '2' }));
    clock += 59_000;
    await decideApproval(t.state, user('alice'), late, 'approved', clock);
    clock += 60_001;
    expect(await tool.execute(t.state, { version: '2' })).toMatchObject({ error_code: 'F502' });
  });

  it('takes no approval after the deadline, so later approvers cannot extend the window', async () => {
    let clock = 0;
    const tool = groundedTool({
      name: 'release',
      capability: 'execute',
      description: 'Run the release.',
      approval: { expires_ms: 1000 },
      args: z.object({ version: z.string() }),
      now: () => clock,
      execute: async () => ({ result: 'released', evidence_anchors: [] }),
    });
    const t = thread();
    const d = digestOf(await tool.execute(t.state, { version: '1' }));
    clock = 999;
    await decideApproval(t.state, user('alice'), d, 'approved', clock);
    // Alice's approval still counts at 1500, but the request takes no new approval.
    clock = 1500;
    await expect(decideApproval(t.state, user('bob'), d, 'approved', clock)).rejects.toThrow(/no approval/);
    clock = 2000;
    expect(await tool.execute(t.state, { version: '1' })).toMatchObject({ error_code: 'F502' });

    // An approval stored after the deadline (by a writer that skipped the
    // check) counts for nothing.
    const record = { digest: 'd', shown: [], min_approvers: 1, requested_at: 0, expires_ms: 1000 };
    const carol = { decision_id: 'x', decision: 'approved' as const, approver: 'carol', at: 1500 };
    expect(approvalState({ ...record, decisions: [carol] }, 1600)).toBe('expired');

    // A rejection is still taken after the deadline while an approval counts.
    const d2 = digestOf(await tool.execute(t.state, { version: '2' }));
    clock += 999;
    await decideApproval(t.state, user('alice'), d2, 'approved', clock);
    clock += 500;
    await decideApproval(t.state, user('bob'), d2, 'rejected', clock);
    expect(await tool.execute(t.state, { version: '2' })).toMatchObject({ error_code: 'F502' });
  });
});

describe('decisions made at the same moment', () => {
  // Endpoint requests are not serialised with one another, and the store has
  // no conditional write, so two decisions can be in flight together.
  const both = async (first: 'approved' | 'rejected', second: 'approved' | 'rejected') => {
    const t = thread();
    const d = digestOf(await writeConfig.execute(t.state, CHANGE));
    await Promise.all([
      decideApproval(t.state, user('alice'), d, first, 1),
      decideApproval(t.state, user('bob'), d, second, 1),
    ]);
    return { t, d };
  };

  it('never loses a rejection to an approval', async () => {
    for (const order of [
      ['approved', 'rejected'],
      ['rejected', 'approved'],
    ] as const) {
      const { t, d } = await both(order[0], order[1]);
      const record = await readApproval(t.state, d);
      expect(record && approvalState(record, 2), order.join(' then ')).toBe('rejected');
      await checkpointConfig.execute(t.state, { label: 'one' });
      expect(await writeConfig.execute(t.state, CHANGE)).toMatchObject({ error_code: 'F502' });
    }
  });

  it('can lose an approval, which the approver gives again', async () => {
    const tool = groundedTool({
      name: 'release',
      capability: 'execute',
      description: 'Run the release.',
      approval: { min_approvers: 2 },
      args: z.object({ version: z.string() }),
      execute: async () => ({ result: 'released', success: true, evidence_anchors: [] }),
    });
    const t = thread();
    const d = digestOf(await tool.execute(t.state, { version: '1.2.0' }));
    await Promise.all([
      decideApproval(t.state, user('alice'), d, 'approved', 1),
      decideApproval(t.state, user('bob'), d, 'approved', 1),
    ]);
    // Whichever approval the shared list lost is simply given again.
    for (const name of ['alice', 'bob']) {
      await decideApproval(t.state, user(name), d, 'approved', 2).catch((error: unknown) => {
        expect(String(error)).toMatch(/already decided/);
      });
    }
    const record = await readApproval(t.state, d);
    expect(record?.decisions.map((x) => x.approver).sort()).toEqual(['alice', 'bob']);
    expect(await tool.execute(t.state, { version: '1.2.0' })).toMatchObject({ status: 'success' });
  });
});

describe('the approval endpoint', () => {
  it('lists what is pending and records the authenticated caller', async () => {
    const t = thread();
    await checkpointConfig.execute(t.state, { label: 'one' });
    const d = digestOf(await writeConfig.execute(t.state, CHANGE));

    const listed = (await (
      await approvalsGet(new Request('https://runtime.example/x'), t.state, {}, { caller: user('alice'), threadAccess: true })
    ).json()) as { approvals: { digest: string; round: number; shown: unknown }[] };
    expect(listed.approvals).toEqual([
      expect.objectContaining({ digest: d, round: 1, shown: [{ action: 'write_config', capability: 'mutate', args: CHANGE }] }),
    ]);

    const response = await post(t, user('alice'), { digest: d, round: listed.approvals[0]?.round, decision: 'approved' });
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ digest: d, state: 'approved' });
    expect(t.queued).toEqual([expect.objectContaining({ role: 'user', silent: true })]);

    data(await writeConfig.execute(t.state, CHANGE));
    const entry = (await readTrace(t.state)).at(-1);
    expect(entry?.approval).toMatchObject({ digest: d, approvers: ['alice'] });
  });

  it('refuses an anonymous caller, a malformed body and an unknown request', async () => {
    const t = thread();
    expect((await post(t, null, { digest: 'a'.repeat(64), round: 1, decision: 'approved' })).status).toBe(401);
    expect((await post(t, user('alice'), { decision: 'approved' })).status).toBe(400);
    // The round the approver was shown is part of the decision.
    expect((await post(t, user('alice'), { digest: 'a'.repeat(64), decision: 'approved' })).status).toBe(400);
    expect((await post(t, user('alice'), { digest: 'a'.repeat(64), round: 0, decision: 'approved' })).status).toBe(400);
    expect((await post(t, user('alice'), { digest: 'a'.repeat(64), round: 1, decision: 'approved' })).status).toBe(404);
  });

  it('applies a decision only to the round the approver was shown', async () => {
    const t = thread();
    const first = await writeConfig.execute(t.state, CHANGE);
    const d = digestOf(first);
    expect(first.error_data).toMatchObject({ round: 1 });

    // Alice and Bob both have round 1 open. Bob rejects it, and the model,
    // woken, asks again: that opens round 2.
    expect((await post(t, user('bob'), { digest: d, round: 1, decision: 'rejected' })).status).toBe(200);
    expect(await writeConfig.execute(t.state, CHANGE)).toMatchObject({ error_data: { state: 'pending', round: 2 } });

    // Alice's approval, given on the list she loaded before Bob rejected.
    const late = await post(t, user('alice'), { digest: d, round: 1, decision: 'approved' });
    expect(late.status).toBe(409);
    await checkpointConfig.execute(t.state, { label: 'one' });
    expect(await writeConfig.execute(t.state, CHANGE)).toMatchObject({ error_code: 'F502' });
    expect(t.files.get(SETTINGS_PATH)).toBe('{"retries":"3"}');
  });

  it('does not let a repeated approval authorise the next round', async () => {
    const t = thread();
    const d = digestOf(await writeConfig.execute(t.state, CHANGE));
    const approval = { digest: d, round: 1, decision: 'approved' };
    expect((await post(t, user('alice'), approval)).status).toBe(200);
    await checkpointConfig.execute(t.state, { label: 'one' });
    data(await writeConfig.execute(t.state, CHANGE));

    // The setting is changed back, and the model makes the same change again.
    t.files.set(SETTINGS_PATH, '{"retries":"3"}');
    expect(await writeConfig.execute(t.state, CHANGE)).toMatchObject({ error_data: { state: 'pending', round: 2 } });
    // A client's retry of Alice's first request (a second tab, a double submit).
    expect((await post(t, user('alice'), approval)).status).toBe(409);
    await checkpointConfig.execute(t.state, { label: 'two' });
    expect(await writeConfig.execute(t.state, CHANGE)).toMatchObject({ error_code: 'F502' });
    expect(t.files.get(SETTINGS_PATH)).toBe('{"retries":"3"}');
  });

  it('answers a decision it stored when the thread cannot be woken, and accepts the same decision again', async () => {
    const t = thread();
    const d = digestOf(await writeConfig.execute(t.state, CHANGE));
    const failing = new Proxy(t.state, {
      get(target, property, receiver) {
        if (property === 'queueMessage') return async () => Promise.reject(new Error('queue unavailable'));
        return Reflect.get(target, property, receiver) as unknown;
      },
    });
    const request = (body: unknown) =>
      new Request('https://runtime.example/threads/thread-1/acs/approvals', { method: 'POST', body: JSON.stringify(body) });
    const approval = { digest: d, round: 1, decision: 'approved' };

    const response = await approvalsPost(request(approval), failing, {}, { caller: user('alice'), threadAccess: true });
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ digest: d, state: 'approved', woken: false });

    // The client sends the same decision again: it is answered, and the thread woken.
    const retry = await post(t, user('alice'), approval);
    expect(retry.status).toBe(200);
    expect(await retry.json()).toEqual({ digest: d, state: 'approved' });
    expect(t.queued).toHaveLength(1);
    // A different decision by the same approver is still refused.
    expect((await post(t, user('alice'), { ...approval, decision: 'rejected' })).status).toBe(409);
  });

  it('answers a rejection sent again as the first, and no other decision on the closed round', async () => {
    const t = thread();
    const d = digestOf(await writeConfig.execute(t.state, CHANGE));
    const rejection = { digest: d, round: 1, decision: 'rejected' };
    expect((await post(t, user('bob'), rejection)).status).toBe(200);

    // Bob's client did not get the answer and sends the rejection again.
    const retry = await post(t, user('bob'), rejection);
    expect(retry.status).toBe(200);
    expect(await retry.json()).toEqual({ digest: d, state: 'rejected' });
    expect(t.queued).toHaveLength(2);

    // Anyone else's decision, or Bob's approval, on the rejected round is refused.
    expect((await post(t, user('carol'), rejection)).status).toBe(409);
    expect((await post(t, user('alice'), { ...rejection, decision: 'approved' })).status).toBe(409);
    expect((await post(t, user('bob'), { ...rejection, decision: 'approved' })).status).toBe(409);

    // Once the same values are asked for again, the rejection is of a closed round.
    expect(await writeConfig.execute(t.state, CHANGE)).toMatchObject({ error_data: { state: 'pending', round: 2 } });
    expect((await post(t, user('bob'), rejection)).status).toBe(409);
    expect(t.queued).toHaveLength(2);
  });
});

describe('evidence and audit trail', () => {
  it('rejects an output that lacks a field the ontology requires', async () => {
    const tool = groundedTool({
      name: 'ungrounded_read',
      capability: 'retrieve',
      description: 'x',
      args: z.object({}),
      // @ts-expect-error the retrieve output requires evidence_anchors and confidence
      execute: async () => ({ data: 1 }),
    });
    const t = thread();
    const result = await tool.execute(t.state, {});
    expect(result).toMatchObject({ status: 'error' });
    expect(result.error).toMatch(/missing evidence_anchors, confidence/);
    expect((await readTrace(t.state)).at(-1)).toMatchObject({ status: 'failed' });
  });

  it('rejects required output fields of the wrong type', async () => {
    const returning = (output: Record<string, unknown>) =>
      groundedTool({
        name: 'ungrounded_read',
        capability: 'retrieve',
        description: 'x',
        args: z.object({}),
        execute: async () => output as { data: number; evidence_anchors: []; confidence: number },
      });
    const t = thread();
    for (const [output, problem] of [
      [{ data: 1, evidence_anchors: null, confidence: 1 }, /evidence_anchors is not an array/],
      [{ data: 1, evidence_anchors: [], confidence: 'very' }, /confidence is not a number from 0 to 1/],
      [{ data: 1, evidence_anchors: [], confidence: 1.5 }, /confidence is not a number from 0 to 1/],
    ] as const) {
      const result = await returning(output).execute(t.state, {});
      expect(result, JSON.stringify(output)).toMatchObject({ status: 'error' });
      expect(result.error).toMatch(problem);
      expect((await readTrace(t.state)).at(-1)).toMatchObject({ status: 'failed' });
    }
    data(await returning({ data: 1, evidence_anchors: [], confidence: 0 }).execute(t.state, {}));
  });

  it('records a call whose arguments have no canonical JSON, and does not run it', async () => {
    let runs = 0;
    const tool = groundedTool({
      name: 'note',
      capability: 'persist',
      description: 'x',
      args: z.object({ text: z.string() }),
      execute: async () => {
        runs += 1;
        return { stored: true, evidence_anchors: [] };
      },
    });
    const t = thread();
    // Half of a surrogate pair: JSON.parse and z.string() accept it; RFC 8785 does not.
    const result = await tool.execute(t.state, { text: 'ok \ud83d' });
    expect(result).toMatchObject({ status: 'error' });
    expect(result.error).toMatch(/unpaired surrogate/);
    expect(runs).toBe(0);
    expect((await readTrace(t.state)).at(-1)).toMatchObject({ action: 'note', status: 'failed' });
  });

  it('records every call, including refusals, with its evidence', async () => {
    const t = thread();
    await readConfig.execute(t.state, {});
    await approve(t);
    await writeConfig.execute(t.state, CHANGE);
    const cp = data(await checkpointConfig.execute(t.state, { label: 'one' }));
    await writeConfig.execute(t.state, CHANGE);
    data(await verifyConfig.execute(t.state, { key: 'retries', expected: '5' }));

    const trace = await readTrace(t.state);
    expect(trace.map((e) => [e.seq, e.action, e.capability, e.status, e.code ?? null])).toEqual([
      [1, 'read_config', 'retrieve', 'executed', null],
      [2, 'write_config', 'mutate', 'refused', 'F502'],
      [3, 'write_config', 'mutate', 'refused', 'F501'],
      [4, 'checkpoint_config', 'checkpoint', 'executed', null],
      [5, 'write_config', 'mutate', 'executed', null],
      [6, 'verify_config', 'verify', 'executed', null],
    ]);
    expect(trace[4]).toMatchObject({ checkpoint_id: cp['checkpoint_id'], approval: { approvers: ['alice'] } });
    expect(trace[4]?.evidence_anchors).toHaveLength(2);
    expect(trace[0]?.args_digest).toBe(await digest({}));
  });

  it('leaves a started entry for a call that is cut off while it runs', async () => {
    // A tool whose own code never returns stands for an execution that is
    // aborted, or a process that is lost, after the tool may have acted.
    const hangs = groundedTool({
      name: 'send_report',
      capability: 'send',
      description: 'x',
      args: z.object({ to: z.string() }),
      execute: () => new Promise<never>(() => {}),
    });
    const t = thread();
    const call = (id: string): HookToolCall => ({ id, type: 'function', function: { name: 'send_report', arguments: '{}' } });
    const context = { source: { kind: 'prompt', promptName: 'config_steward' } } as const;

    const refused = await hangs.execute(t.state, { to: 'ops' });
    await auditHook.execute(t.state, call('call_1'), { status: 'error' }, context);
    await decideApproval(t.state, user('alice'), digestOf(refused), 'approved', Date.now());
    const cp = data(await checkpointConfig.execute(t.state, { label: 'before send' }));
    void hangs.execute(t.state, { to: 'ops' });
    await started(t);

    expect((await readTrace(t.state)).at(-1)).toMatchObject({
      seq: 3,
      action: 'send_report',
      status: 'started',
      checkpoint_id: cp['checkpoint_id'],
      approval: { approvers: ['alice'] },
    });

    // A later call to the same tool finishes (refused: the approval is used).
    // Its call id goes to its own entry, not to the one that was cut off.
    await hangs.execute(t.state, { to: 'ops' });
    await auditHook.execute(t.state, call('call_3'), { status: 'error' }, context);
    const trace = await readTrace(t.state);
    expect(trace.map((e) => [e.seq, e.status, e.tool_call_id ?? null])).toEqual([
      [1, 'refused', 'call_1'],
      [2, 'executed', null],
      [3, 'started', null],
      [4, 'refused', 'call_3'],
    ]);
  });

  it('gives a cut-off call its id when the runtime reports it done', async () => {
    const hangs = groundedTool({
      name: 'observe_forever',
      capability: 'observe',
      description: 'x',
      args: z.object({}),
      execute: () => new Promise<never>(() => {}),
    });
    const t = thread();
    void hangs.execute(t.state, {});
    await started(t);
    await auditHook.execute(
      t.state,
      { id: 'call_1', type: 'function', function: { name: 'observe_forever', arguments: '{}' } },
      { status: 'error', error: 'aborted' },
      { source: { kind: 'prompt', promptName: 'config_steward' } },
    );
    expect(await readTrace(t.state)).toEqual([expect.objectContaining({ seq: 1, status: 'started', tool_call_id: 'call_1' })]);
  });

  it('restores the checkpointed document on rollback', async () => {
    const t = thread();
    const cp = data(await checkpointConfig.execute(t.state, { label: 'one' }));
    const refused = await writeConfig.execute(t.state, CHANGE);
    await decideApproval(t.state, user('alice'), digestOf(refused), 'approved', Date.now());
    await writeConfig.execute(t.state, CHANGE);

    const output = data(await rollbackConfig.execute(t.state, { checkpoint_id: cp['checkpoint_id'] as string }));
    expect(output).toMatchObject({ restored: true, restored_state: { retries: '3' } });
    expect(t.files.get(SETTINGS_PATH)).toBe('{"retries":"3"}');
  });

  it('restores over damaged settings, and only from a restore point taken in this thread', async () => {
    const t = thread();
    const cp = data(await checkpointConfig.execute(t.state, { label: 'one' }));

    // The settings are damaged: the case a restore point exists for.
    t.files.set(SETTINGS_PATH, '{"retries": "5",');
    const output = data(await rollbackConfig.execute(t.state, { checkpoint_id: cp['checkpoint_id'] as string }));
    expect(output).toMatchObject({ restored: true, previous_state: '{"retries": "5",', restored_state: { retries: '3' } });
    expect(t.files.get(SETTINGS_PATH)).toBe('{"retries":"3"}');

    // A path made from the model's string, and an id no checkpoint call returned.
    t.files.set('/acs/checkpoints/../../attachments/settings.json', '{"admin":"true"}');
    t.files.set('/acs/checkpoints/cp-99/settings.json', '{"admin":"true"}');
    for (const checkpoint_id of ['../../attachments', 'cp-99']) {
      const result = await rollbackConfig.execute(t.state, { checkpoint_id });
      expect(result, checkpoint_id).toMatchObject({ status: 'error' });
      expect(result.error).toMatch(/not a restore point/);
    }
    expect(t.files.get(SETTINGS_PATH)).toBe('{"retries":"3"}');
    expect(rollbackConfig.args.safeParse({ checkpoint_id: '../../attachments' }).success).toBe(false);
  });

  it('joins tool call ids to grounded entries and records ungrounded calls', async () => {
    const t = thread();
    const call = (id: string, name: string): HookToolCall => ({ id, type: 'function', function: { name, arguments: '{}' } });
    const context = { source: { kind: 'prompt', promptName: 'config_steward' } } as const;

    await readConfig.execute(t.state, {});
    await auditHook.execute(t.state, call('call_1', 'read_config'), { status: 'success' }, context);
    await auditHook.execute(t.state, call('call_2', 'web_search'), { status: 'error', error: 'offline' }, context);

    expect(await readTrace(t.state)).toEqual([
      expect.objectContaining({ seq: 1, action: 'read_config', capability: 'retrieve', tool_call_id: 'call_1' }),
      expect.objectContaining({ seq: 2, action: 'web_search', capability: null, status: 'failed', tool_call_id: 'call_2' }),
    ]);
  });

  it('keeps an entry waiting for its hook when a call is made outside the execution meanwhile', async () => {
    const t = thread();
    const call = (id: string, name: string): HookToolCall => ({ id, type: 'function', function: { name, arguments: '{}' } });
    const context = { source: { kind: 'prompt', promptName: 'config_steward' } } as const;
    // A thread endpoint, with no execution, reads the settings while the
    // model's own call to the same tool waits for its hook.
    const endpoint = new Proxy(t.state, {
      get: (target, property, receiver) => (property === 'execution' ? null : (Reflect.get(target, property, receiver) as unknown)),
    });
    await readConfig.execute(t.state, {});
    await readConfig.execute(endpoint, {});
    await auditHook.execute(t.state, call('call_1', 'read_config'), { status: 'success' }, context);

    expect((await readTrace(t.state)).map((e) => [e.seq, e.flow_id ?? null, e.capability, e.tool_call_id ?? null])).toEqual([
      [1, 'flow-1', 'retrieve', 'call_1'],
      [2, null, 'retrieve', null],
    ]);
  });

  it('never gives a call id to an entry of an earlier step or execution', async () => {
    const t = thread();
    const call = (id: string, name: string): HookToolCall => ({ id, type: 'function', function: { name, arguments: '{}' } });
    const context = { source: { kind: 'prompt', promptName: 'config_steward' } } as const;

    // Step 1: the write is refused, and its hook does not run (it failed or
    // timed out, which the specification allows).
    await approve(t);
    // Step 2: the restore point and the write that changes the setting.
    t.nextStep();
    await checkpointConfig.execute(t.state, { label: 'one' });
    await auditHook.execute(t.state, call('call_2', 'checkpoint_config'), { status: 'success' }, context);
    data(await writeConfig.execute(t.state, CHANGE));
    await auditHook.execute(t.state, call('call_3', 'write_config'), { status: 'success' }, context);
    // A hook delivered twice for one call adds nothing.
    await auditHook.execute(t.state, call('call_3', 'write_config'), { status: 'success' }, context);

    expect((await readTrace(t.state)).map((e) => [e.seq, e.action, e.status, e.tool_call_id ?? null])).toEqual([
      [1, 'write_config', 'refused', null],
      [2, 'checkpoint_config', 'executed', 'call_2'],
      [3, 'write_config', 'executed', 'call_3'],
    ]);
  });

  it('does not give a cut-off call the id of a call in a later execution', async () => {
    const hangs = groundedTool({
      name: 'observe_forever',
      capability: 'observe',
      description: 'x',
      args: z.object({}),
      execute: () => new Promise<never>(() => {}),
    });
    const t = thread();
    void hangs.execute(t.state, {});
    await started(t);

    // The execution is lost. In the next one a call to the same tool never
    // reaches it (the runtime rejects its arguments), and its hook runs.
    t.newExecution();
    await auditHook.execute(
      t.state,
      { id: 'call_9', type: 'function', function: { name: 'observe_forever', arguments: '{"x":' } },
      { status: 'error', error: 'invalid arguments' },
      { source: { kind: 'prompt', promptName: 'config_steward' } },
    );
    expect((await readTrace(t.state)).map((e) => [e.seq, e.capability, e.status, e.tool_call_id ?? null])).toEqual([
      [1, 'observe', 'started', null],
      [2, null, 'failed', 'call_9'],
    ]);
  });
});

describe('the agent definition', () => {
  it('is a valid Standard Agent', () => {
    expect(validateAgentDefinition(configSteward)).toEqual([]);
  });

  it('offers a tool for everything its tools require', () => {
    const tools = {
      read_config: readConfig,
      checkpoint_config: checkpointConfig,
      write_config: writeConfig,
      verify_config: verifyConfig,
      rollback_config: rollbackConfig,
    };
    expect(lintPromptTools('config_steward', tools)).toEqual([]);

    // Without the checkpoint tool the write and the rollback could never run.
    const { checkpoint_config: _removed, ...withoutCheckpoint } = tools;
    expect(lintPromptTools('config_steward', withoutCheckpoint).map((d) => [d.code, d.location.tool])).toEqual([
      ['V102', 'write_config'],
      ['V102', 'rollback_config'],
    ]);

    // A tool defined with plain defineTool is reported as unclassified.
    const plain = { ...tools, web_search: { annotations: { agentbuilder: {} } } };
    expect(lintPromptTools('config_steward', plain)).toEqual([
      expect.objectContaining({ code: 'unclassified', severity: 'warning', location: { prompt: 'config_steward', tool: 'web_search' } }),
    ]);
  });

  it('reports a tool whose stated name is not the name it is offered under', () => {
    // Copied from another tool, with `name` left unchanged: an approver
    // would be shown `archive_record` for a call that purges.
    const purge = groundedTool({
      name: 'archive_record',
      capability: 'execute',
      description: 'Purge a record.',
      args: z.object({ key: z.string() }),
      execute: async () => ({ result: 'purged', evidence_anchors: [] }),
    });
    expect(lintPromptTools('records', { purge_record: purge }).map((d) => [d.code, d.severity, d.location, d.message])).toEqual([
      [
        'misnamed_tool',
        'error',
        { prompt: 'records', tool: 'purge_record', capability: 'execute' },
        "tool 'purge_record' states the name 'archive_record', which is what an approver is shown and the trace records",
      ],
    ]);
  });

  it('binds no stop or session action to a tool that can be refused', () => {
    const tools = { read_config: readConfig, checkpoint_config: checkpointConfig, write_config: writeConfig, rollback_config: rollbackConfig };
    expect(lintAgentBindings(configSteward, tools)).toEqual([]);

    // The specification acts on the call, not on its result: a refused write
    // would still end the session and report the model's text to a parent.
    const ending = {
      name: 'ends_on_write',
      sideA: {
        prompt: 'config_steward',
        stopTool: 'rollback_config',
        sessionStop: { name: 'write_config', messageProperty: 'value' },
        sessionStatus: { name: 'read_config' },
      },
      sideB: { human: true },
    } as const;
    expect(lintAgentBindings(ending, tools).map((d) => [d.code, d.severity, d.location])).toEqual([
      ['bound_gated_tool', 'error', { agent: 'ends_on_write', side: 'sideA', binding: 'stopTool', tool: 'rollback_config', capability: 'rollback' }],
      ['bound_gated_tool', 'error', { agent: 'ends_on_write', side: 'sideA', binding: 'sessionStop', tool: 'write_config', capability: 'mutate' }],
    ]);
    expect(lintAgentBindings(ending, tools).map((d) => d.message)).toEqual([
      "agent 'ends_on_write' binds stopTool to 'rollback_config' (rollback), which is refused without a 'checkpoint' call; the binding acts on the call, not on its result",
      "agent 'ends_on_write' binds sessionStop to 'write_config' (mutate), which is refused without approval and a 'checkpoint' call; the binding acts on the call, not on its result",
    ]);
  });

  it('offers only grounded tools, each with an annotation the schema accepts', () => {
    const tools = {
      read_config: readConfig,
      checkpoint_config: checkpointConfig,
      write_config: writeConfig,
      verify_config: verifyConfig,
      rollback_config: rollbackConfig,
    };
    expect(prompt.tools).toEqual(Object.keys(tools));
    const validate = new Ajv2020().compile(annotationSchema);
    for (const [name, tool] of Object.entries(tools)) {
      const annotation = acsAnnotation(tool);
      expect(validate(annotation), `${name}: ${JSON.stringify(validate.errors)}`).toBe(true);
      expect(Object.hasOwn(CAPABILITIES, annotation?.capability ?? '')).toBe(true);
    }
    expect(validate({ ...acsAnnotation(writeConfig), capability: 'detect-anomaly' })).toBe(false);
  });
});

describe('the package', () => {
  it('exports what Packaging describes, with every tool still classified', async () => {
    const pkg: PackedExports = await import('../src/package.js');

    expect(pkg.__meta.packageId).toBe(manifest.name);
    expect(pkg.__meta.entryAgents).toEqual(manifest.standardagent.entryAgents);
    expect(Object.keys(pkg.threadEndpoints ?? {})).toEqual(manifest.standardagent.threadEndpoints);
    expect(manifest.keywords).toContain('standardagent');

    for (const agentName of pkg.__meta.entryAgents) {
      const agent = await pkg.agents[agentName]?.();
      expect(validateAgentDefinition(agent)).toEqual([]);
    }

    // Everything a prompt names is in the package, and each tool is classified.
    for (const loadPrompt of Object.values(pkg.prompts)) {
      const packed = await loadPrompt();
      expect(Object.keys(pkg.models)).toContain(packed.model);
      for (const hook of packed.hooks ?? []) expect(Object.keys(pkg.hooks)).toContain(hook);
      const offered: Record<string, { annotations?: Record<string, unknown> }> = {};
      for (const tool of packed.tools ?? []) {
        const name = typeof tool === 'string' ? tool : tool.name;
        const definition = await pkg.tools[name]?.();
        expect(definition, name).toBeDefined();
        expect(acsAnnotation(definition ?? {}), name).not.toBeNull();
        offered[name] = definition ?? {};
      }
      // Each tool states the name it is packed under, and nothing is unmet.
      expect(lintPromptTools(packed.name, offered)).toEqual([]);
    }
  });
});
