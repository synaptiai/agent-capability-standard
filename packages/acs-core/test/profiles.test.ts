// The domain profile vectors (Standard 1.2.0 section 5.21, section 10.3)
// through the core, run from TypeScript: one implementation of the loader.
import { describe, expect, it } from 'vitest';
import load from '../../../tests/conformance/profiles/load.json' with { type: 'json' };
import effective from '../../../tests/conformance/profiles/effective.json' with { type: 'json' };
import type { Json } from '../src/canonical.js';
import type { CapabilityId, DeclaredFlags } from '../src/ontology.js';
import { CoreError } from '../src/wasm.js';
import { repositoryContext } from './core.js';

type Found = string[];
const key = (d: { code: string; profile: string; field: string }) => `${d.code} ${d.profile} ${d.field}`;

/** Whether `value` holds a number with no exact JSON form (I-JSON): an
 * integer beyond 2^53, which the core's loader reports as S303. */
const inexact = (value: unknown): boolean =>
  typeof value === 'number'
    ? Number.isInteger(value) && Math.abs(value) > 2 ** 53
    : typeof value === 'object' && value !== null && Object.values(value).some(inexact);

describe('profile load vectors', () => {
  for (const v of load.vectors) {
    it(v.name, async () => {
      const ctx = await repositoryContext();
      if (inexact(v.profiles)) {
        // The WebAssembly interface takes only I-JSON requests, so such a
        // profile is refused before the loader reports it: refused either way.
        expect(v.expect.errors.map((e) => e.code)).toEqual(['S303']);
        expect(() => ctx.checkProfiles(v.profiles as Json[])).toThrow(/bad_request: .*I-JSON/);
        return;
      }
      const report = ctx.checkProfiles(v.profiles as Json[]);
      const of = (severity: string): Found =>
        report.diagnostics
          .filter((d) => d.severity === severity)
          .map((d) => key({ code: d.code, profile: String(d.location.profile), field: String(d.location.field) }))
          .sort();
      expect(of('error')).toEqual(v.expect.errors.map(key).sort());
      expect(of('warning')).toEqual(v.expect.warnings.map(key).sort());
    });
  }
});

describe('profile effect vectors', () => {
  for (const v of effective.flags) {
    it(v.name, async () => {
      const ctx = await repositoryContext();
      const declared = 'declared' in v ? (v.declared as DeclaredFlags) : undefined;
      expect(ctx.profileFlags(v.profiles as Json[], v.capability as CapabilityId, declared)).toEqual(v.expect);
    });
  }
  for (const v of effective.policy) {
    it(v.name, async () => {
      const ctx = await repositoryContext();
      expect(ctx.profilePolicy(v.profiles as Json[])).toEqual(v.expect);
    });
  }
  it('refuses profiles with an error', async () => {
    const ctx = await repositoryContext();
    expect(() => ctx.profilePolicy([{ domain: 'd' }])).toThrow(CoreError);
  });
});

describe('a run under a profile rule no executor check reads yet', () => {
  // The core refuses to start a run under a profile's grounding or
  // destination policy rather than run as if it were absent (section 5.21.3).
  const catalog = {
    w: {
      goal: 'g',
      risk: 'low',
      spec_version: '1.1',
      steps: [{ capability: 'retrieve', purpose: 'p', store_as: 'r', input_bindings: { target: 'x' } }],
    },
  };
  const rules: [string, Record<string, Json>][] = [
    ['require_grounding', { evidence_policy: { require_grounding: ['retrieve'] } }],
    ['allowed_destinations', { allowed_destinations: [] }],
  ];
  for (const [member, rule] of rules) {
    it(`is refused at start: ${member}`, async () => {
      const ctx = await repositoryContext();
      const profiles = [{ domain: 'd', version: '1.0.0', ...rule }] as Json[];
      let caught: unknown;
      try {
        ctx.start({ catalog, workflow: 'w', header: null, runId: 'r', nowMs: 0, profiles });
      } catch (e) {
        caught = e;
      }
      expect(caught).toBeInstanceOf(CoreError);
      expect((caught as CoreError).kind).toBe('start');
      expect((caught as CoreError).message).toContain(member);
    });
  }
  it('starts under the rules it applies', async () => {
    const ctx = await repositoryContext();
    const profiles = [{ domain: 'd', version: '1.0.0', evidence_policy: { minimum_confidence: 0.5 } }] as Json[];
    const run = ctx.start({ catalog, workflow: 'w', header: null, runId: 'r', nowMs: 0, profiles });
    expect((run.next() as unknown as Record<string, Json>).kind).toBe('InvokeCapability');
    run.dispose();
  });
});
