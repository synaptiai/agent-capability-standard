// Every validator fixture (tests/fixtures/*.workflow_catalog.yaml), parsed by
// the core and validated with the header it returns and the profiles, other
// catalogs and agent manifests EXPECTATIONS.json names, gives exactly its
// expected codes and the locations it lists.
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
// The other catalogs of a fixture's set and its agent manifests (section 10.3).
const SET_FILES: Record<string, string> = {
  ...import.meta.glob<string>('../../../tests/fixtures/catalogs/*.yaml', { eager: true, import: 'default', query: '?raw' }),
  ...import.meta.glob<string>('../../../tests/fixtures/agents/*.yaml', { eager: true, import: 'default', query: '?raw' }),
};

interface Expectation {
  should_pass: boolean;
  expected_error_codes?: string[];
  expected_warning_codes?: string[];
  profiles?: string[];
  /** Further catalogs of the fixture's set, relative to tests/fixtures/. */
  catalogs?: string[];
  /** Agent manifests, relative to tests/fixtures/. */
  agents?: string[];
  /** Diagnostics the report must locate at a `path` (section 9.8). */
  expected_locations?: { code: string; path: string }[];
}

function setFile(path: string): string {
  const text = SET_FILES[`../../../tests/fixtures/${path}`];
  expect(text, path).toBeDefined();
  return text as string;
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
      const catalogs = (meta.catalogs ?? []).map((c) => core.parseCatalog(setFile(c)));
      const agents = (meta.agents ?? []).map((a) => core.parseYaml(setFile(a)));
      const report = ctx.validate(catalog, { header, profiles, catalogs, agents });
      const codes = (severity: string) =>
        [...new Set(report.diagnostics.filter((d) => d.severity === severity).map((d) => d.code))].sort();
      const errors = codes('error');
      expect(errors.length === 0).toBe(meta.should_pass);
      if (errors.length) expect(errors).toEqual([...(meta.expected_error_codes ?? [])].sort());
      expect(codes('warning')).toEqual([...(meta.expected_warning_codes ?? [])].sort());
      const located = report.diagnostics.map((d) => `${d.code} ${String(d.location.path)}`);
      for (const { code, path } of meta.expected_locations ?? []) expect(located).toContain(`${code} ${path}`);
    });
  }
});
