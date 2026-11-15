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

describe('profile load vectors', () => {
  for (const v of load.vectors) {
    it(v.name, async () => {
      const ctx = await repositoryContext();
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
