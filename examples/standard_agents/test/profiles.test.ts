// Domain profiles (STANDARD 1.2.0 §5.21) in the binding: raised flags, a
// person requirement, grounding policies and the minimum confidence. The
// binding runs on the plain entry, so these tests give `bindingProfiles` a
// core of their own computing what `CoreContext` computes for the profiles
// they use; `packages/acs-core` tests the core's answers.
import type { ToolResult } from '@standardagents/spec';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import type { Json } from '@synaptiai/acs-core';
import type { ProfileFlags, ProfilePolicy } from '@synaptiai/acs-core/wasm';
import { decideApproval } from '../src/acs/approval.js';
import { groundedTool } from '../src/acs/grounded.js';
import { effectiveFlags, type CapabilityId } from '../src/acs/ontology.js';
import { bindingProfiles, confidenceFailure, type ProfileCore } from '../src/acs/profiles.js';
import { actionRecord, readTrace } from '../src/acs/records.js';
import { memoryThread, user } from './memory_thread.js';

const NO_RULES: ProfilePolicy = { minimum_confidence: null, grounding: [], destinations: [], trust_weights: {} };

/** A core for one profile: `require_human: low` when `person`, and `policy`. */
function core(policy: Partial<ProfilePolicy>, person = false): ProfileCore {
  return {
    profileFlags(_profiles: Json[], capability: CapabilityId): ProfileFlags {
      const { flags } = effectiveFlags(capability);
      return person ? { ...flags, requires_approval: true, person: true } : { ...flags, person: false };
    },
    profilePolicy(): ProfilePolicy {
      return { ...NO_RULES, ...policy };
    },
  };
}

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
  it('refuses a destination policy the binding does not check (§5.21.4)', () => {
    expect(() => bindingProfiles(core({ destinations: [['mailto:*']] }), [{ domain: 'd' }])).toThrow(
      /allowed_destinations/,
    );
    const handmade = { documents: [], policy: { ...NO_RULES, destinations: [[]] }, flags: core({}).profileFlags };
    expect(() =>
      groundedTool({
        name: 'n',
        capability: 'retrieve',
        description: 'd',
        args: z.object({}),
        profiles: { ...handmade, flags: (c: CapabilityId) => handmade.flags([], c) },
        execute: async () => ({ data: 1, confidence: 1, evidence_anchors: [] }) as never,
      }),
    ).toThrow(/allowed_destinations/);
  });

  it('applies the minimum confidence as the core does', () => {
    expect(confidenceFailure({ confidence: 0.5 }, 0.9)?.reason).toBe('below_minimum_confidence');
    expect(confidenceFailure({ confidence: '0.95' }, 0.9)?.reason).toBe('invalid_confidence');
    expect(confidenceFailure({ confidence: 1.5 }, 0.9)?.reason).toBe('invalid_confidence');
    expect(confidenceFailure({ confidence: 0.9 }, 0.9)).toBeNull();
    expect(confidenceFailure({}, 0.9)).toBeNull();
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
