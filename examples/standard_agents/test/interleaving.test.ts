/**
 * Calls and decisions that overlap, and a store that fails part-way.
 *
 * The thread's key-value store has no conditional write, and the Standard
 * Agent Specification serialises executions, not endpoint requests or the
 * calls a tool starts itself. These tests put the binding's reads and writes
 * in the orders such overlaps produce.
 */
import type { ThreadState, ToolResult } from '@standardagents/spec';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import approvalsPost from '../agents/api/acs/approvals.post.js';
import checkpointConfig from '../agents/tools/checkpoint_config.js';
import readConfig from '../agents/tools/read_config.js';
import writeConfig from '../agents/tools/write_config.js';
import { approvalState, decideApproval, readApproval } from '../src/acs/approval.js';
import { groundedTool } from '../src/acs/grounded.js';
import { KEYS, readCheckpoints, readExecuted, readTrace, type ApprovalRecord } from '../src/acs/records.js';
import { SETTINGS_PATH } from '../src/example/settings.js';
import { memoryThread, user, type MemoryThread } from './memory_thread.js';

const CHANGE = { key: 'retries', value: '5' };

function thread(): MemoryThread {
  const t = memoryThread();
  t.files.set(SETTINGS_PATH, '{"retries":"3"}');
  return t;
}

function digestOf(result: ToolResult): string {
  expect(result.error_code).toBe('F502');
  return result.error_data?.['digest'] as string;
}

interface Interceptor {
  beforeGet?(key: string): Promise<void> | void;
  /** Throw to make the write fail. */
  beforeSet?(key: string, value: unknown): Promise<void> | void;
  afterSet?(key: string, value: unknown): Promise<void> | void;
}

/** The thread's state, with `on` run around each key-value read and write. */
function intercept(t: MemoryThread, on: Interceptor): ThreadState {
  return new Proxy(t.state, {
    get(target, property, receiver) {
      if (property === 'getValue') {
        return async (key: string) => {
          await on.beforeGet?.(key);
          return target.getValue(key);
        };
      }
      if (property === 'setValue') {
        return async (key: string, value: unknown) => {
          await on.beforeSet?.(key, value);
          await target.setValue(key, value);
          await on.afterSet?.(key, value);
        };
      }
      return Reflect.get(target, property, receiver) as unknown;
    },
  });
}

/** A store whose every read and write waits for the next timer tick. */
function slow(t: MemoryThread): ThreadState {
  const tick = () => new Promise<void>((resolve) => setTimeout(resolve, 1));
  return intercept(t, { beforeGet: tick, beforeSet: tick });
}

async function post(state: ThreadState, caller: string, body: unknown): Promise<{ status: number; body: unknown }> {
  const request = new Request('https://runtime.example/threads/thread-1/acs/approvals', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  const response = await approvalsPost(request, state, {}, { caller: user(caller), threadAccess: true });
  return { status: response.status, body: await response.json() };
}

describe('a rejection recorded while an approved call is starting', () => {
  // Alice has approved and a restore point is taken; the model calls the
  // write, and Bob rejects at some moment while the write is starting. Bob
  // must never be told "rejected" for a change that then runs.
  async function approved(): Promise<{ t: MemoryThread; d: string; reject: () => Promise<{ status: number; body: unknown }> }> {
    const t = thread();
    const d = digestOf(await writeConfig.execute(t.state, CHANGE));
    await decideApproval(t.state, user('alice'), d, 'approved', Date.now());
    await checkpointConfig.execute(t.state, { label: 'one' });
    return { t, d, reject: () => post(t.state, 'bob', { digest: d, round: 1, decision: 'rejected' }) };
  }

  it('stops the call when recorded after the call read the approval and before it used it', async () => {
    const { t, d, reject } = await approved();
    let answer: unknown;
    let done = false;
    const racing = intercept(t, {
      beforeGet: async (key) => {
        if (!done && key === KEYS.executed) {
          done = true;
          answer = await reject();
        }
      },
    });
    const result = await writeConfig.execute(racing, CHANGE);

    expect(answer).toEqual({ status: 200, body: { digest: d, state: 'rejected' } });
    expect(result).toMatchObject({ status: 'error', error_code: 'F502' });
    expect(result.error).toMatch(/rejected while this call was starting/);
    expect(t.files.get(SETTINGS_PATH)).toBe('{"retries":"3"}');
    expect((await readCheckpoints(t.state)).map((c) => c.valid)).toEqual([true]);
    const record = await readApproval(t.state, d);
    expect(record && approvalState(record, Date.now())).toBe('rejected');
  });

  it('stops the call, and does not answer "rejected", when each side writes before the other reads', async () => {
    const { t, d } = await approved();
    // Bob's request reads the request (approved), then waits just before it
    // writes the rejection. The call marks the approval used; then Bob's
    // request writes and reads again; then the call looks for a rejection.
    let reached!: () => void;
    const atWrite = new Promise<void>((resolve) => (reached = resolve));
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    const endpoint = intercept(t, {
      beforeSet: async (key) => {
        if (key === KEYS.rejected(d, 1)) {
          reached();
          await gate;
        }
      },
    });
    const answer = post(endpoint, 'bob', { digest: d, round: 1, decision: 'rejected' });
    await atWrite;
    const tool = intercept(t, {
      afterSet: async (key, value) => {
        if (key === KEYS.approval(d) && (value as ApprovalRecord).used_at !== undefined) {
          release();
          await answer;
        }
      },
    });
    const result = await writeConfig.execute(tool, CHANGE);

    expect(await answer).toMatchObject({ status: 409 });
    expect(result).toMatchObject({ status: 'error', error_code: 'F502' });
    expect(t.files.get(SETTINGS_PATH)).toBe('{"retries":"3"}');
    expect((await readCheckpoints(t.state)).map((c) => c.valid)).toEqual([true]);
  });

  it('answers 409, not "rejected", when recorded after the call passed its checks', async () => {
    const { t, reject } = await approved();
    let answer: unknown;
    let done = false;
    const racing = intercept(t, {
      beforeSet: async (key) => {
        if (!done && key === KEYS.checkpoints) {
          done = true;
          answer = await reject();
        }
      },
    });
    const result = await writeConfig.execute(racing, CHANGE);

    expect(answer).toMatchObject({ status: 409 });
    expect(result.status).toBe('success');
    expect(JSON.parse(t.files.get(SETTINGS_PATH) ?? '')).toEqual({ retries: '5' });
  });
});

describe('gated calls that overlap', () => {
  const sendTool = (sent: string[]) =>
    groundedTool({
      name: 'send_report',
      capability: 'send',
      description: 'Send the report.',
      args: z.object({ to: z.string() }),
      execute: async (_state, { to }) => {
        sent.push(to);
        return { sent: true, evidence_anchors: [] };
      },
    });

  it('refuses a call that needs approval outside an execution, where calls are not serialised', async () => {
    const runs: string[] = [];
    const release = groundedTool({
      name: 'run_release',
      capability: 'execute',
      description: 'Run the release.',
      args: z.object({ version: z.string() }),
      execute: async (_state, { version }) => {
        runs.push(version);
        return { result: 'released', evidence_anchors: [] };
      },
    });
    const t = thread();
    const d = digestOf(await release.execute(t.state, { version: '1' }));
    await decideApproval(t.state, user('alice'), d, 'approved', Date.now());

    // From a thread endpoint, through state.invokeTool: two requests at once.
    t.atRest();
    const results = await Promise.all([release.execute(slow(t), { version: '1' }), release.execute(slow(t), { version: '1' })]);
    for (const result of results) {
      expect(result).toMatchObject({ status: 'error', error_code: 'F502' });
      expect(result.error).toMatch(/not part of an execution/);
    }
    expect(runs).toEqual([]);

    // In an execution the approval is still there to use, once.
    t.newExecution();
    expect((await release.execute(t.state, { version: '1' })).status).toBe('success');
    expect(runs).toEqual(['1']);
  });

  it('runs one of two calls a tool starts together on one approval and one checkpoint', async () => {
    const sent: string[] = [];
    const send = sendTool(sent);
    const t = thread();
    const d = digestOf(await send.execute(t.state, { to: 'ops' }));
    await decideApproval(t.state, user('alice'), d, 'approved', Date.now());
    await checkpointConfig.execute(t.state, { label: 'one' });

    // A tool's own code calls state.invokeTool twice without waiting.
    const results = await Promise.all([send.execute(slow(t), { to: 'ops' }), send.execute(slow(t), { to: 'ops' })]);
    expect(sent).toEqual(['ops']);
    expect(results.map((r) => r.error_code ?? r.status).sort()).toEqual(['F502', 'success']);
    expect((await readExecuted(t.state)).send).toBe(1);
  });

  it('gives every overlapping call its own trace entry', async () => {
    const t = thread();
    await Promise.all([1, 2, 3].map(() => readConfig.execute(slow(t), {})));
    expect((await readTrace(t.state)).map((e) => [e.seq, e.status])).toEqual([
      [1, 'executed'],
      [2, 'executed'],
      [3, 'executed'],
    ]);
    expect((await readExecuted(t.state)).retrieve).toBe(3);
  });
});

describe('a store that fails part-way', () => {
  /** Make the next write of `key` fail, once. */
  function failNextWrite(t: MemoryThread, key: string): ThreadState {
    let failed = false;
    return intercept(t, {
      beforeSet: (written) => {
        if (!failed && written === key) {
          failed = true;
          throw new Error('storage unavailable');
        }
      },
    });
  }

  it('keeps a rejection when asking again fails to store the new round', async () => {
    const t = thread();
    const d = digestOf(await writeConfig.execute(t.state, CHANGE));
    await decideApproval(t.state, user('bob'), d, 'rejected', Date.now());

    const result = await writeConfig.execute(failNextWrite(t, KEYS.approval(d)), CHANGE);
    expect(result).toMatchObject({ status: 'error' });
    const record = await readApproval(t.state, d);
    expect(record && approvalState(record, Date.now())).toBe('rejected');
    await expect(decideApproval(t.state, user('alice'), d, 'approved', Date.now())).rejects.toThrow(/rejected/);

    // Asked again with a working store, the rejection moves to the history.
    expect(await writeConfig.execute(t.state, CHANGE)).toMatchObject({ error_data: { state: 'pending', round: 2 } });
    expect((await readApproval(t.state, d))?.history).toEqual([
      expect.objectContaining({ decisions: [expect.objectContaining({ approver: 'bob', decision: 'rejected' })] }),
    ]);
  });

  it('records what a call used when a write after the approval fails', async () => {
    const t = thread();
    const d = digestOf(await writeConfig.execute(t.state, CHANGE));
    await decideApproval(t.state, user('alice'), d, 'approved', Date.now());
    const cp = await checkpointConfig.execute(t.state, { label: 'one' });

    const result = await writeConfig.execute(failNextWrite(t, KEYS.checkpoints), CHANGE);
    // The layer could not complete its checks: R407 (STANDARD 1.2.0 §5.18.8).
    expect(result).toMatchObject({ status: 'error', error_code: 'R407' });
    expect(result.error).toMatch(/^R407 SAFETY_CHECK_FAILED: .*storage unavailable/);
    expect(t.files.get(SETTINGS_PATH)).toBe('{"retries":"3"}');
    expect((await readTrace(t.state)).at(-1)).toMatchObject({
      action: 'write_config',
      status: 'failed',
      error: 'storage unavailable',
      approval: { digest: d, approvers: ['alice'] },
      checkpoint_id: JSON.parse(cp.result ?? '{}').checkpoint_id,
    });
  });

  it('never overwrites a trace entry when a trace write fails', async () => {
    const t = thread();
    await readConfig.execute(t.state, {});
    const result = await readConfig.execute(failNextWrite(t, KEYS.traceCount), {});
    expect(result).toMatchObject({ status: 'error', error_code: 'R407' });
    expect(result.error).toMatch(/storage unavailable/);
    await readConfig.execute(t.state, {});
    expect((await readTrace(t.state)).map((e) => [e.seq, e.status])).toEqual([
      [1, 'executed'],
      [2, 'failed'],
      [3, 'executed'],
    ]);
  });
});
