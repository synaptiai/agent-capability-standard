// Every validator fixture (tests/fixtures/*.workflow_catalog.yaml), parsed by
// the core and validated with the header it returns and the profiles
// EXPECTATIONS.json names, gives exactly its expected codes.
import { describe, expect, it } from 'vitest';
import expectations from '../../../tests/fixtures/EXPECTATIONS.json' with { type: 'json' };
import type { Json } from '../src/canonical.js';
import { loadCore, repositoryContext } from './core.js';

const CATALOGS = import.meta.glob<string>('../../../tests/fixtures/*.workflow_catalog.yaml', {
  eager: true,
  import: 'default',
  query: '?raw',
});
const PROFILES = import.meta.glob<string>('../../../tests/fixtures/profiles/*.yaml', {
  eager: true,
  import: 'default',
  query: '?raw',
});

interface Expectation {
  should_pass: boolean;
  expected_error_codes?: string[];
  expected_warning_codes?: string[];
  profiles?: string[];
}

describe('validator fixtures through the core', () => {
  for (const [name, meta] of Object.entries(expectations as Record<string, Expectation>)) {
    it(name, async () => {
      const core = await loadCore();
      const ctx = await repositoryContext();
      const text = CATALOGS[`../../../tests/fixtures/${name}.workflow_catalog.yaml`];
      expect(text, name).toBeDefined();
      const { catalog, header } = core.parseCatalog(text as string);
      const profiles: Json[] = (meta.profiles ?? []).map((p) => core.parseYaml(PROFILES[`../../../${p}`] as string));
      const report = ctx.validate(catalog, { header, profiles });
      const codes = (severity: string) =>
        [...new Set(report.diagnostics.filter((d) => d.severity === severity).map((d) => d.code))].sort();
      const errors = codes('error');
      expect(errors.length === 0).toBe(meta.should_pass);
      if (errors.length) expect(errors).toEqual([...(meta.expected_error_codes ?? [])].sort());
      expect(codes('warning')).toEqual([...(meta.expected_warning_codes ?? [])].sort());
    });
  }
});
