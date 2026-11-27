// Domain profiles (STANDARD 1.2.0 §5.21) in the binding: raised flags, a
// person requirement, grounding policies and the minimum confidence. The
// binding runs on the plain entry, so these tests give `bindingProfiles` a
// core of their own computing what `CoreContext` computes for the profiles
// they use; `packages/acs-core` tests the core's answers.
import { defineTool, type ThreadState, type ToolResult } from '@standardagents/spec';
import { afterEach, describe, expect, it } from 'vitest';
import { z } from 'zod';
import type { Json } from '@synaptiai/acs-core';
import type { CoreContext, Diagnostic, ProfileFlags, ProfilePolicy } from '@synaptiai/acs-core/wasm';
import { decideApproval } from '../src/acs/approval.js';
import { acsAnnotation, groundedTool } from '../src/acs/grounded.js';
import { effectiveFlags, type CapabilityId, type DeclaredFlags, type Risk } from '../src/acs/ontology.js';
import { configureLayer, registerTools, resetLayer } from '../src/acs/layer.js';
import { bindingProfiles, confidenceFailure, type ProfileCore } from '../src/acs/profiles.js';
import { actionRecord, readTrace } from '../src/acs/records.js';
import { memoryThread, user, type MemoryThread } from './memory_thread.js';
import effective from '../../../tests/conformance/profiles/effective.json' with { type: 'json' };

const NO_RULES: ProfilePolicy = { minimum_confidence: null, grounding: [], destinations: [], trust_weights: {} };

// The core's context is what a host passes to `bindingProfiles`.
const coreContextIsAProfileCore = (context: CoreContext): ProfileCore => context;
void coreContextIsAProfileCore;

/** A core for one profile: `require_human: low` when `person`, and `policy`; `warnings` its loading warnings. */
function core(policy: Partial<ProfilePolicy>, person = false, warnings: Diagnostic[] = []): ProfileCore {
  return {
    checkProfiles: () => ({ diagnostics: warnings, suggestions: [] }),
    profileFlags(_profiles: Json[], capability: CapabilityId): ProfileFlags {
      const { flags } = effectiveFlags(capability);
      return person ? { ...flags, requires_approval: true, person: true } : { ...flags, person: false };
    },
    profilePolicy(): ProfilePolicy {
      return { ...NO_RULES, ...policy };
    },
  };
}

const RANK: Record<Risk, number> = { low: 0, medium: 1, high: 2 };

/**
 * A core computing `risk_thresholds.require_human` and `block_autonomous`
 * as the core does (§5.21.3): at the effective risk with the declared
 * flags, a person when a profile's threshold covers it or lists the
 * capability.
 */
const THRESHOLDS: ProfileCore = {
  checkProfiles: () => ({ diagnostics: [], suggestions: [] }),
  profileFlags(profiles: Json[], capability: CapabilityId, declared?: DeclaredFlags): ProfileFlags {
    const { flags } = effectiveFlags(capability, declared);
    const person = profiles.some((p) => {
      const t = (p as { risk_thresholds?: { require_human?: Risk; block_autonomous?: string[] } }).risk_thresholds ?? {};
      const human = t.require_human;
      return (human !== undefined && RANK[flags.risk] >= RANK[human]) || (t.block_autonomous ?? []).includes(capability);
    });
    return { ...flags, requires_approval: flags.requires_approval || person, person };
  },
  profilePolicy: () => NO_RULES,
};

function classify(profiles: ReturnType<typeof bindingProfiles>, output: Record<string, unknown>) {
  return groundedTool({
    name: 'label_ticket',
    capability: 'classify',
    description: 'Label a ticket.',
    args: z.object({ item: z.string() }),
    profiles,
    execute: async () => output as never,
  });
}

function data(result: ToolResult): Record<string, unknown> {
  expect(result.status, result.error).toBe('success');
  return JSON.parse(result.result ?? 'null') as Record<string, unknown>;
}

const LABELS = { labels: ['bug'], confidence: 0.95, evidence_anchors: [{ ref: 'file:t.md', kind: 'file' }] };

describe('bindingProfiles', () => {
  it("keeps a profile's destination policy, which a send tool applies (§5.21.3; test/layer.test.ts)", () => {
    const profiles = bindingProfiles(core({ destinations: [['mailto:*']] }), [{ domain: 'd' }], { onWarning: () => {} });
    expect(profiles.policy.destinations).toEqual([['mailto:*']]);
    // A tool that does not send defines under it as under any profile.
    expect(() =>
      groundedTool({
        name: 'n',
        capability: 'retrieve',
        description: 'd',
        args: z.object({}),
        profiles,
        execute: async () => ({ data: 1, confidence: 1, evidence_anchors: [] }) as never,
      }),
    ).not.toThrow();
  });

  it("reports each loading warning and keeps it (§5.21.2's W604: the member is ignored)", () => {
    const w604: Diagnostic = {
      code: 'W604',
      name: 'UNKNOWN_FIELD',
      severity: 'warning',
      message: "unknown profile member 'risk_threshold' is ignored",
      location: { profile: 'd', field: 'risk_threshold' },
      suggestion: "did you mean 'risk_thresholds'?",
    };
    const documents = [{ domain: 'd', version: '1.0.0', risk_threshold: { require_human: 'low' } }];
    const seen: Diagnostic[] = [];
    const profiles = bindingProfiles(core({}, false, [w604]), documents, { onWarning: (d) => seen.push(d) });
    expect(seen).toEqual([w604]);
    expect(profiles.warnings).toEqual([w604]);
    // Without a callback each warning goes to console.warn.
    const logged: unknown[] = [];
    const original = console.warn;
    console.warn = (...args: unknown[]) => void logged.push(args.join(' '));
    try {
      bindingProfiles(core({}, false, [w604]), documents);
    } finally {
      console.warn = original;
    }
    expect(logged).toEqual([
      "bindingProfiles: W604 warning: unknown profile member 'risk_threshold' is ignored (did you mean 'risk_thresholds'?)",
    ]);
    expect(bindingProfiles(core({}), [{ domain: 'd' }], { onWarning: () => expect.fail('no warning') }).warnings).toEqual([]);
  });

  it('applies the minimum confidence as the core does', () => {
    expect(confidenceFailure({ confidence: 0.5 }, 0.9)?.reason).toBe('below_minimum_confidence');
    expect(confidenceFailure({ confidence: '0.95' }, 0.9)?.reason).toBe('invalid_confidence');
    expect(confidenceFailure({ confidence: 1.5 }, 0.9)?.reason).toBe('invalid_confidence');
    expect(confidenceFailure({ confidence: 0.9 }, 0.9)).toBeNull();
    expect(confidenceFailure({}, 0.9)).toBeNull();
    // The host's text is not repeated (§6.7): a string is named by its type.
    const secret = confidenceFailure({ confidence: 'AKIAIOSFODNN7EXAMPLE' }, 0.9)?.message;
    expect(secret).not.toContain('AKIA');
    expect(secret).toMatch(/^the output's confidence \(a string\) is not a number from 0 to 1/);
    expect(confidenceFailure({ confidence: 1.5 }, 0.9)?.message).toMatch(/confidence \(1\.5\) is not/);
  });
});

describe('a grounded tool under domain profiles (§5.21.3)', () => {
  it("fails an output below the profiles' minimum confidence with F504, after grounding", async () => {
    const profiles = bindingProfiles(core({ minimum_confidence: 0.9 }), [{ domain: 'd' }]);
    const t = memoryThread();
    expect(data(await classify(profiles, LABELS).execute(t.state, { item: 'x' }))).toMatchObject({ labels: ['bug'] });
    const low = await classify(profiles, { ...LABELS, confidence: 0.5 }).execute(t.state, { item: 'x' });
    expect(low.error_code).toBe('F504');
    const entry = (await readTrace(t.state)).at(-1)!;
    expect(entry).toMatchObject({ status: 'failed', code: 'F504', reason_code: 'below_minimum_confidence' });
    expect(actionRecord(entry, 's')).toMatchObject({ status: 'failed', reason_code: 'below_minimum_confidence' });
  });

  it("checks the profiles' grounding policy (required_anchor_types as kinds)", async () => {
    const profiles = bindingProfiles(
      core({ grounding: [{ require: ['classify'], kinds: ['file'] }], minimum_confidence: 0.9 }),
      [{ domain: 'd' }],
    );
    const t = memoryThread();
    // A log anchor is not a file anchor; grounding fails before the minimum.
    const log = { ...LABELS, confidence: 0.1, evidence_anchors: [{ ref: 'log:app#1', kind: 'log' }] };
    expect((await classify(profiles, log).execute(t.state, { item: 'x' })).error_code).toBe('F505');
    expect(data(await classify(profiles, LABELS).execute(t.state, { item: 'x' }))).toMatchObject({ confidence: 0.95 });
  });

  it("asks a person, counts only a person's approval and records person_required", async () => {
    const profiles = bindingProfiles(core({}, true), [{ domain: 'd' }]);
    const tool = classify(profiles, LABELS);
    const t = memoryThread();
    const first = await tool.execute(t.state, { item: 'x' });
    expect(first.error_code).toBe('F502');
    expect(first.error).toMatch(/person's approval/);
    const digest = first.error_data?.['digest'] as string;
    // An approval the deployment attests as an agent's does not count.
    await decideApproval(t.state, user('bot'), digest, 'approved', Date.now(), undefined, { kind: 'agent' });
    expect((await tool.execute(t.state, { item: 'x' })).error_code).toBe('F502');
    await decideApproval(t.state, user('alice'), digest, 'approved', Date.now());
    expect(data(await tool.execute(t.state, { item: 'x' }))).toMatchObject({ labels: ['bug'] });
    const entry = (await readTrace(t.state)).at(-1)!;
    expect(entry).toMatchObject({ status: 'executed', person_required: true });
    expect(entry.approval?.approvers).toEqual(['sa-user:alice']);
    expect(actionRecord(entry, 's').person_required).toBe(true);
  });

  it('puts the profiles in the configuration digest (§5.18.8)', async () => {
    const run = async (documents: Json[]) => {
      const t = memoryThread();
      await classify(bindingProfiles(core({}), documents), LABELS).execute(t.state, { item: 'x' });
      return (await readTrace(t.state)).at(-1)!.recorded_by?.config_sha256;
    };
    expect(await run([{ domain: 'a' }])).not.toBe(await run([{ domain: 'b' }]));
  });
});

describe('a composite under domain profiles (§5.18.4, §5.21.3)', () => {
  const args = z.object({}).passthrough();
  const save = groundedTool({
    name: 'save',
    capability: 'checkpoint',
    description: 'save',
    args,
    execute: async (_s, _a, call) => ({ checkpoint_id: `cp-${call.seq}`, evidence_anchors: [] }),
  });

  /**
   * `write` (mutate) and `batch` (invoke, `invokes: {write}`) under
   * `documents`, registered in a thread. `composite-only`: the profiles are
   * given to `batch` alone. `unprofiled-listed`: `batch` lists a definition
   * of `write` the profiles were not given to, and is not given them itself
   * (they would reach the `write` it lists), while the thread runs the
   * `write` they were given to.
   */
  function setup(documents: Json[], mode?: 'composite-only' | 'unprofiled-listed') {
    const profiles = bindingProfiles(THRESHOLDS, documents);
    const writeTool = (p?: typeof profiles) =>
      groundedTool({
        name: 'write',
        capability: 'mutate',
        description: 'write',
        args,
        ...(p !== undefined ? { profiles: p } : {}),
        execute: async () => ({ success: true, evidence_anchors: [] }),
      });
    const write = writeTool(mode === 'composite-only' ? undefined : profiles);
    const nested: ToolResult[] = [];
    const batch = groundedTool({
      name: 'batch',
      capability: 'invoke',
      invokes: { write: mode === 'unprofiled-listed' ? writeTool() : write } as never,
      description: 'batch',
      args,
      ...(mode === 'unprofiled-listed' ? {} : { profiles }),
      execute: async (state) => {
        nested.push(await state.invokeTool('write', {}));
        return { result: true, evidence_anchors: [] } as never;
      },
    });
    const t = memoryThread();
    for (const [n, tool] of Object.entries({ save, write, batch })) t.tools.set(n, tool);
    return { t, nested };
  }

  const run = (t: MemoryThread, n: string) => t.tools.get(n)!.execute(t.state, {});

  /** Ask for `batch`, approve it as `who`, and call it again. */
  async function batchApprovedBy(t: MemoryThread, who: 'agent' | 'person'): Promise<ToolResult> {
    expect((await run(t, 'save')).status).toBe('success');
    const asked = await run(t, 'batch');
    expect(asked.error_code).toBe('F502');
    const digest = asked.error_data?.['digest'] as string;
    if (who === 'agent') {
      await decideApproval(t.state, user('bot'), digest, 'approved', Date.now(), undefined, { kind: 'agent' });
    } else {
      await decideApproval(t.state, user('alice'), digest, 'approved', Date.now());
    }
    return run(t, 'batch');
  }

  it('takes R with the tools it invokes: require_human: high asks a person for an invoke of a mutate', async () => {
    const documents = [{ domain: 'd', version: '1.0.0', risk_thresholds: { require_human: 'high' } }];
    // An invoke alone is medium; with the mutate it lists, R is high. Only
    // the composite is given the profiles, so only its own R decides.
    const { t, nested } = setup(documents, 'composite-only');
    const refused = await batchApprovedBy(t, 'agent');
    expect(refused.error_code).toBe('F502');
    expect(refused.error).toMatch(/person's approval/);
    expect(nested).toEqual([]);
    expect((await readTrace(t.state)).filter((e) => e.action === 'write')).toEqual([]);

    const { t: t2, nested: nested2 } = setup(documents);
    expect((await batchApprovedBy(t2, 'person')).status).toBe('success');
    expect(nested2.map((r) => r.status)).toEqual(['success']);
    const trace = await readTrace(t2.state);
    const composite = trace.find((e) => e.action === 'batch' && e.status === 'executed')!;
    expect(composite).toMatchObject({ person_required: true, approval: { approvers: ['sa-user:alice'] } });
    expect(trace.find((e) => e.action === 'write')).toMatchObject({
      status: 'executed',
      person_required: true,
      covered_by: composite.seq,
    });
  });

  it('asks a person for a composite that invokes a tool a profile requires one for (block_autonomous)', async () => {
    const documents = [{ domain: 'd', version: '1.0.0', risk_thresholds: { block_autonomous: ['mutate'] } }];
    const { t, nested } = setup(documents);
    // C is invoke, which is not listed; the nested mutate is, and the
    // composite's approval would cover it.
    const refused = await batchApprovedBy(t, 'agent');
    expect(refused.error_code).toBe('F502');
    expect(nested).toEqual([]);

    const { t: t2, nested: nested2 } = setup(documents);
    expect((await batchApprovedBy(t2, 'person')).status).toBe('success');
    expect(nested2.map((r) => r.status)).toEqual(['success']);
    const trace = await readTrace(t2.state);
    expect(trace.find((e) => e.action === 'batch' && e.status === 'executed')).toMatchObject({ person_required: true });
    expect(trace.find((e) => e.action === 'write')).toMatchObject({ status: 'executed', person_required: true });
  });

  it('applies profiles given to the composite alone to the capabilities of the tools it invokes (block_autonomous)', async () => {
    // Only `batch` (invoke) is given `block_autonomous: [mutate]`; the
    // `write` it lists is not. Its approval would cover the nested mutate,
    // so the composite's profiles reach it: an agent's approval is not
    // enough, and nothing nested runs.
    const documents = [{ domain: 'd', version: '1.0.0', risk_thresholds: { block_autonomous: ['mutate'] } }];
    const { t, nested } = setup(documents, 'composite-only');
    const refused = await batchApprovedBy(t, 'agent');
    expect(refused.error_code).toBe('F502');
    expect(refused.error).toMatch(/person's approval/);
    expect(nested).toEqual([]);
    expect((await readTrace(t.state)).filter((e) => e.action === 'write')).toEqual([]);

    const { t: t2, nested: nested2 } = setup(documents, 'composite-only');
    expect((await batchApprovedBy(t2, 'person')).status).toBe('success');
    expect(nested2.map((r) => r.status)).toEqual(['success']);
    const trace = await readTrace(t2.state);
    const composite = trace.find((e) => e.action === 'batch' && e.status === 'executed')!;
    expect(composite).toMatchObject({ person_required: true });
    expect(trace.find((e) => e.action === 'write')).toMatchObject({ status: 'executed', covered_by: composite.seq });
  });

  it('passes the requirement on through a composite of composites', async () => {
    const profiles = bindingProfiles(THRESHOLDS, [
      { domain: 'd', version: '1.0.0', risk_thresholds: { block_autonomous: ['mutate'] } },
    ]);
    const write = groundedTool({
      name: 'write',
      capability: 'mutate',
      description: 'write',
      args,
      profiles,
      execute: async () => ({ success: true, evidence_anchors: [] }),
    });
    const inner = groundedTool({
      name: 'inner',
      capability: 'invoke',
      invokes: { write } as never,
      description: 'inner',
      args,
      execute: async () => ({ result: true, evidence_anchors: [] }) as never,
    });
    const outer = groundedTool({
      name: 'outer',
      capability: 'invoke',
      invokes: { inner } as never,
      description: 'outer',
      args,
      execute: async () => ({ result: true, evidence_anchors: [] }) as never,
    });
    const t = memoryThread();
    for (const [n, tool] of Object.entries({ save, outer })) t.tools.set(n, tool);
    expect((await run(t, 'save')).status).toBe('success');
    const asked = await run(t, 'outer');
    const digest = asked.error_data?.['digest'] as string;
    await decideApproval(t.state, user('bot'), digest, 'approved', Date.now(), undefined, { kind: 'agent' });
    const refused = await run(t, 'outer');
    expect(refused.error_code).toBe('F502');
    expect(refused.error).toMatch(/person's approval/);
  });

  it("checks a nested call that needs a person as a call of its own when the composite's approval was not a person's", async () => {
    const { t, nested } = setup(
      [{ domain: 'd', version: '1.0.0', risk_thresholds: { block_autonomous: ['mutate'] } }],
      'unprofiled-listed',
    );
    // The composite lists a `write` that needs no person, so it is approved
    // by an agent and runs; the `write` the thread runs needs a person, so
    // the composite's approval does not cover it.
    expect((await batchApprovedBy(t, 'agent')).status).toBe('success');
    expect(nested.map((r) => r.error_code)).toEqual(['F502']);
    const entry = (await readTrace(t.state)).find((e) => e.action === 'write')!;
    expect(entry).toMatchObject({ status: 'refused', code: 'F502', person_required: true });
    expect(entry.covered_by).toBeUndefined();
  });
});

/**
 * A core computing the members the call vectors use as the core does
 * (§5.21.3), for one capability at the risk declared: the thresholds,
 * `block_autonomous` and `checkpoint_policy`.
 */
const RULES: ProfileCore = {
  checkProfiles: () => ({ diagnostics: [], suggestions: [] }),
  profileFlags(profiles: Json[], capability: CapabilityId, declared?: DeclaredFlags): ProfileFlags {
    const { flags } = effectiveFlags(capability, declared);
    const r = RANK[flags.risk];
    let approval = flags.requires_approval;
    let checkpoint = flags.requires_checkpoint;
    let person = false;
    for (const p of profiles as {
      risk_thresholds?: { auto_approve?: string; require_review?: string; require_human?: string; block_autonomous?: string[] };
      checkpoint_policy?: Record<string, string>;
    }[]) {
      const t = p.risk_thresholds ?? {};
      const at = (level?: string) => (level === undefined || level === 'none' ? undefined : RANK[level as Risk]);
      const auto = t.auto_approve === undefined ? undefined : (at(t.auto_approve) ?? -1);
      const review = at(t.require_review);
      const human = at(t.require_human);
      const blocked = (t.block_autonomous ?? []).includes(capability);
      if ((auto !== undefined && r > auto) || (review !== undefined && r >= review)) approval = true;
      if ((human !== undefined && r >= human) || blocked) [approval, person] = [true, true];
      const value = p.checkpoint_policy?.[capability] ?? p.checkpoint_policy?.['*'];
      if (
        capability !== 'checkpoint' &&
        (value === 'always' || (value === 'high_risk' && r >= 2) || (value === 'medium_risk' && r >= 1))
      ) {
        checkpoint = true;
      }
    }
    return { ...flags, requires_checkpoint: checkpoint, requires_approval: approval, person };
  },
  profilePolicy: () => NO_RULES,
};

describe("a nested call is covered only by the decisions the composite's call counted (§5.18.4, §5.21.3)", () => {
  // Security round 5, batch 4: the composite's call counted only a person's
  // approval, but a nested call that needs one was covered by any approval
  // in the request still valid when it ran, so an agent's approval given
  // after the person's renewed it once the person's had expired.
  afterEach(() => resetLayer());
  const args = z.object({}).passthrough();
  const documents = [{ domain: 'd', version: '1.0.0', risk_thresholds: { block_autonomous: ['mutate'] } }];

  /**
   * `save`, `write` (mutate, its approval valid for a minute) and `batch`
   * (invoke, `invokes: {write}`, which works 10 s before its nested call).
   * `plain`: `write` is a plain tool with a binding record, registered, and
   * only `batch` is given the profiles. A person approves `batch` at T0;
   * with `agent`, an approver attested as an agent approves it 50 s later;
   * `batch` runs at T0 + 55 s, so the person's approval has lapsed when
   * `write` runs at T0 + 65 s and the agent's has not.
   */
  async function scenario(kind: 'grounded' | 'plain', agent: boolean) {
    let T = 1_000_000;
    const now = () => T;
    const profiles = bindingProfiles(THRESHOLDS, documents);
    const save = groundedTool({
      name: 'save',
      capability: 'checkpoint',
      description: 'save',
      args,
      now,
      execute: async (_s, _a, call) => ({ checkpoint_id: `cp-${call.seq}`, evidence_anchors: [] }),
    });
    let wrote = 0;
    const write =
      kind === 'grounded'
        ? groundedTool({
            name: 'write',
            capability: 'mutate',
            description: 'write',
            args,
            now,
            profiles,
            approval: { expires_ms: 60_000 },
            execute: async () => {
              wrote += 1;
              return { success: true, evidence_anchors: [] };
            },
          })
        : defineTool({
            description: 'write',
            args,
            annotations: {
              'ai.synapti/acs': { standard: '1.2.0', ontology: '2.2.0', capability: 'mutate', approval: { expires: '1m' } },
            },
            execute: async () => {
              wrote += 1;
              return { status: 'success', result: JSON.stringify({ success: true, evidence_anchors: [] }) };
            },
          });
    const nested: ToolResult[] = [];
    const batch = groundedTool({
      name: 'batch',
      capability: 'invoke',
      invokes: { write } as never,
      description: 'batch',
      args,
      now,
      profiles,
      execute: async (state) => {
        T += 10_000;
        nested.push(await state.invokeTool('write', { path: 'a' }));
        return { result: true, evidence_anchors: [] } as never;
      },
    });
    const t = memoryThread();
    for (const [n, tool] of Object.entries({ save, write, batch })) t.tools.set(n, tool as never);
    if (kind === 'plain') registerTools({ save, write, batch });
    const asked = await t.tools.get('batch')!.execute(t.state, {});
    expect(asked.error_code).toBe('F502');
    const digest = asked.error_data?.['digest'] as string;
    await decideApproval(t.state, user('alice'), digest, 'approved', T);
    if (agent) await decideApproval(t.state, user('review-bot'), digest, 'approved', T + 50_000, undefined, { kind: 'agent' });
    T += 55_000;
    expect((await t.tools.get('save')!.execute(t.state, {})).status).toBe('success');
    const result = await t.tools.get('batch')!.execute(t.state, {});
    return { result, nested, wrote, trace: await readTrace(t.state) };
  }

  for (const kind of ['grounded', 'plain'] as const) {
    it(`refuses a ${kind} nested call an agent's later approval would cover once the person's expired`, async () => {
      const { result, nested, wrote, trace } = await scenario(kind, true);
      expect(result.status).toBe('success');
      const composite = trace.find((e) => e.action === 'batch' && e.status === 'executed')!;
      expect(composite.approval?.approvers).toEqual(['sa-user:alice']);
      expect(nested.map((r) => r.error_code)).toEqual(['F502']);
      expect(wrote).toBe(0);
      expect(trace.some((e) => e.action === 'write' && e.status === 'executed')).toBe(false);
    });

    it(`refuses the same ${kind} nested call with no agent's approval (control)`, async () => {
      const { nested, wrote } = await scenario(kind, false);
      expect(nested.map((r) => r.error_code)).toEqual(['F502']);
      expect(wrote).toBe(0);
    });
  }

  it("covers a nested call while the person's approval the composite's call counted is valid (control)", async () => {
    let T = 1_000_000;
    const now = () => T;
    const profiles = bindingProfiles(THRESHOLDS, documents);
    const save = groundedTool({
      name: 'save',
      capability: 'checkpoint',
      description: 'save',
      args,
      now,
      execute: async (_s, _a, call) => ({ checkpoint_id: `cp-${call.seq}`, evidence_anchors: [] }),
    });
    const write = groundedTool({
      name: 'write',
      capability: 'mutate',
      description: 'write',
      args,
      now,
      profiles,
      approval: { expires_ms: 60_000 },
      execute: async () => ({ success: true, evidence_anchors: [] }),
    });
    const nested: ToolResult[] = [];
    const batch = groundedTool({
      name: 'batch',
      capability: 'invoke',
      invokes: { write } as never,
      description: 'batch',
      args,
      now,
      profiles,
      execute: async (state) => {
        T += 10_000;
        nested.push(await state.invokeTool('write', { path: 'a' }));
        return { result: true, evidence_anchors: [] } as never;
      },
    });
    const t = memoryThread();
    for (const [n, tool] of Object.entries({ save, write, batch })) t.tools.set(n, tool as never);
    const asked = await t.tools.get('batch')!.execute(t.state, {});
    const digest = asked.error_data?.['digest'] as string;
    await decideApproval(t.state, user('alice'), digest, 'approved', T);
    T += 5_000;
    expect((await t.tools.get('save')!.execute(t.state, {})).status).toBe('success');
    expect((await t.tools.get('batch')!.execute(t.state, {})).status).toBe('success');
    expect(nested.map((r) => r.status)).toEqual(['success']);
    const trace = await readTrace(t.state);
    const composite = trace.find((e) => e.action === 'batch' && e.status === 'executed')!;
    expect(trace.find((e) => e.action === 'write')).toMatchObject({ status: 'executed', covered_by: composite.seq });
  });
});

describe("a nested call needs the composite's decisions valid when the profiles raise its approval (§5.18.4, §5.21.3)", () => {
  // Security round 6: a nested call whose own flags need no approval, but
  // whose capability the profiles applied to the composite (or the layer's)
  // make need one, was covered by the composite's approval without its
  // decisions being checked at the nested call, so an approval that had
  // lapsed by then still covered it. A nested grounded tool was checked so
  // only when it was given the profiles itself.
  afterEach(() => resetLayer());
  const args = z.object({}).passthrough();
  const documents = [{ domain: 'd', version: '1.0.0', risk_thresholds: { block_autonomous: ['persist'] } }];

  type Kind = 'grounded' | 'grounded-own' | 'plain';
  type Where = 'composite' | 'layer';

  /**
   * `store` (persist, no approval of its own; `grounded-own` is given the
   * profiles too) and `batch` (invoke, its approval valid for a minute,
   * `invokes: {store}`, which works `work` ms before its nested call), the
   * profiles given to `batch` or put in force by the layer; with `deep`,
   * `batch` reaches `store` through `inner` (invoke, no profiles of its
   * own). A person approves `batch` at T0, and `batch` runs at T0 + 55 s.
   */
  async function scenario(kind: Kind, where: Where, deep: boolean, work: number) {
    let T = 1_000_000;
    const now = () => T;
    const profiles = bindingProfiles(THRESHOLDS, documents);
    if (where === 'layer') configureLayer({ profiles });
    const given = where === 'composite' ? { profiles } : {};
    let stored = 0;
    const store =
      kind === 'plain'
        ? defineTool({
            description: 'store',
            args,
            annotations: { 'ai.synapti/acs': { standard: '1.2.0', ontology: '2.2.0', capability: 'persist' } },
            execute: async () => {
              stored += 1;
              return { status: 'success', result: JSON.stringify({ stored: true, evidence_anchors: [] }) };
            },
          })
        : groundedTool({
            name: 'store',
            capability: 'persist',
            description: 'store',
            args,
            now,
            ...(kind === 'grounded-own' ? given : {}),
            execute: async () => {
              stored += 1;
              return { stored: true, evidence_anchors: [] };
            },
          });
    const nested: ToolResult[] = [];
    const inner = groundedTool({
      name: 'inner',
      capability: 'invoke',
      invokes: { store } as never,
      description: 'inner',
      args,
      now,
      execute: async (state) => {
        nested.push(await state.invokeTool('store', { key: 'a' }));
        return { result: true, evidence_anchors: [] } as never;
      },
    });
    const batch = groundedTool({
      name: 'batch',
      capability: 'invoke',
      invokes: (deep ? { inner } : { store }) as never,
      description: 'batch',
      args,
      now,
      ...given,
      approval: { expires_ms: 60_000 },
      execute: async (state) => {
        T += work;
        if (deep) await state.invokeTool('inner', {});
        else nested.push(await state.invokeTool('store', { key: 'a' }));
        return { result: true, evidence_anchors: [] } as never;
      },
    });
    const t = memoryThread();
    for (const [n, tool] of Object.entries({ store, inner, batch })) t.tools.set(n, tool as never);
    registerTools({ store, inner, batch });
    const asked = await t.tools.get('batch')!.execute(t.state, {});
    expect(asked.error_code).toBe('F502');
    await decideApproval(t.state, user('alice'), asked.error_data?.['digest'] as string, 'approved', T);
    T += 55_000;
    const result = await t.tools.get('batch')!.execute(t.state, {});
    return { result, nested, stored, trace: await readTrace(t.state) };
  }

  const cases: [Kind, Where, boolean][] = [
    ['plain', 'composite', false],
    ['grounded', 'composite', false],
    ['grounded-own', 'composite', false],
    ['plain', 'layer', false],
    ['grounded', 'layer', false],
    ['plain', 'composite', true],
    ['grounded', 'composite', true],
  ];
  for (const [kind, where, deep] of cases) {
    const label = `a ${kind} nested call${deep ? ' two composites deep' : ''}, the profiles the ${where}'s`;
    it(`refuses ${label}, made after the composite's approval lapsed`, async () => {
      const { result, nested, stored, trace } = await scenario(kind, where, deep, 10_000);
      expect(result.status).toBe('success');
      expect(nested.map((r) => r.error_code)).toEqual(['F502']);
      expect(stored).toBe(0);
      expect(trace.some((e) => e.action === 'store' && e.status === 'executed')).toBe(false);
    });

    it(`covers ${label}, while the approval is valid (control)`, async () => {
      const { nested, stored, trace } = await scenario(kind, where, deep, 1_000);
      expect(nested.map((r) => r.status)).toEqual(['success']);
      expect(stored).toBe(1);
      expect(trace.find((e) => e.action === 'store')).toMatchObject({ status: 'executed' });
      expect(trace.find((e) => e.action === 'store')?.covered_by).toBeDefined();
    });
  }
});

describe("the flags a composite's profiles raise reach a nested call that takes no token (§5.18.4, §5.21.3)", () => {
  // Security round 6: a nested grounded call whose arguments the runtime
  // validated (a zod default) takes no token, so it is checked as a call of
  // its own; the composite's profiles, which make persist need a person's
  // approval, did not reach it, and it ran with no approval at all.
  afterEach(() => resetLayer());
  const passthrough = z.object({}).passthrough();
  const documents = [{ domain: 'd', version: '1.0.0', risk_thresholds: { block_autonomous: ['persist'] } }];

  async function scenario(validated: boolean) {
    const profiles = bindingProfiles(THRESHOLDS, documents);
    const storeArgs = z.object({ key: z.string(), tags: z.array(z.string()).default([]) });
    let stored = 0;
    const store = groundedTool({
      name: 'store',
      capability: 'persist',
      description: 'store',
      args: storeArgs,
      execute: async () => {
        stored += 1;
        return { stored: true, evidence_anchors: [] };
      },
    });
    const nested: ToolResult[] = [];
    const batch = groundedTool({
      name: 'batch',
      capability: 'invoke',
      invokes: { store } as never,
      description: 'batch',
      args: passthrough,
      profiles,
      execute: async (state) => {
        nested.push(await state.invokeTool('store', validated ? { key: 'a' } : { key: 'a', tags: [] }));
        return { result: true, evidence_anchors: [] } as never;
      },
    });
    const t = memoryThread();
    // The runtime gives a tool its validated arguments (spec ToolDefinition).
    t.tools.set('store', { execute: (s: ThreadState, a: unknown) => store.execute(s, storeArgs.parse(a)) } as never);
    t.tools.set('batch', batch as never);
    registerTools({ store, batch });
    const asked = await t.tools.get('batch')!.execute(t.state, {});
    expect(asked.error_code).toBe('F502');
    await decideApproval(t.state, user('alice'), asked.error_data?.['digest'] as string, 'approved', 2);
    const result = await t.tools.get('batch')!.execute(t.state, {});
    return { result, nested, stored, trace: await readTrace(t.state) };
  }

  it('asks a person for a nested call whose validated arguments take no token', async () => {
    const { result, nested, stored, trace } = await scenario(true);
    expect(result.status).toBe('success');
    expect(nested.map((r) => r.error_code)).toEqual(['F502']);
    expect(nested[0]?.error).toContain("person's approval");
    expect(stored).toBe(0);
    expect(trace.find((e) => e.action === 'store')).toMatchObject({ status: 'refused', code: 'F502', person_required: true });
  });

  it('covers the nested call whose arguments are unchanged (control)', async () => {
    const { nested, stored, trace } = await scenario(false);
    expect(nested.map((r) => r.status)).toEqual(['success']);
    expect(stored).toBe(1);
    const composite = trace.find((e) => e.action === 'batch' && e.status === 'executed')!;
    expect(trace.find((e) => e.action === 'store')).toMatchObject({ status: 'executed', covered_by: composite.seq });
  });
});

describe('the call vectors (tests/conformance/profiles/effective.json, §5.21.3)', () => {
  // Each applied profile raises for every capability the call performs, at
  // the call's effective risk: `additional_capabilities` do not escape it.
  for (const v of effective.calls) {
    it(v.name, async () => {
      const binding = v.binding as { capability: CapabilityId; additional_capabilities?: CapabilityId[] };
      const tool = groundedTool({
        name: 'tool',
        capability: binding.capability,
        ...(binding.additional_capabilities !== undefined
          ? { additional_capabilities: binding.additional_capabilities }
          : {}),
        description: 'A tool of the vector.',
        args: z.object({}),
        profiles: bindingProfiles(RULES, v.profiles as Json[]),
        execute: async () => ({}) as never,
      });
      const annotation = acsAnnotation(tool)!;
      const t = memoryThread();
      await tool.execute(t.state, {});
      const entry = (await readTrace(t.state)).at(-1)!;
      expect({
        risk: annotation.risk,
        mutation: annotation.mutation,
        requires_checkpoint: annotation.requires_checkpoint,
        requires_approval: annotation.requires_approval,
        person: entry.person_required === true,
      }).toEqual(v.expect);
    });
  }
});
