// Tests on the built site. The suite builds the site itself into a temporary
// directory, so it never reads a stale dist/ and works on a clean checkout.
// Expected page counts come from counts.ts (the plan's Phase 4 rule: compare
// against counts.ts, never literal numbers), and the diagnostics rows also
// from a line scan of the Standard.
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { loadCounts } from '../src/data/counts';
import { RESERVED_WORKFLOW_SLUGS } from '../src/data/workflows';
import { checkGeneratedHeadings, checkRouteCoverage, duplicateIds, pageFile } from '../src/lib/check-dist';
import { ROUTES, type Route } from '../src/lib/routes';
import {
  allCatalogSteps,
  diagnosticRowsPerSection,
  profileFiles,
  profileWorkflowIds,
  repoText,
  standardCheckpointCapabilities,
  standardFileVersions,
} from './independent';

let dist = '';

beforeAll(() => {
  dist = mkdtempSync(path.join(tmpdir(), 'acs-site-'));
  execFileSync('npx', ['astro', 'build', '--force', '--outDir', dist], { cwd: process.cwd(), stdio: 'pipe' });
}, 300_000);

afterAll(() => {
  if (dist) rmSync(dist, { recursive: true, force: true });
});

/** Directories directly under `dir` that hold an index.html. */
function pageDirs(dir: string): string[] {
  return readdirSync(path.join(dist, dir), { withFileTypes: true })
    .filter((e) => e.isDirectory() && existsSync(path.join(dist, dir, e.name, 'index.html')))
    .map((e) => e.name)
    .sort();
}

describe('built site', () => {
  it('has an index.html for every route in routes.ts', () => {
    const missing = ROUTES.filter((r) => !existsSync(path.join(dist, r.url, 'index.html'))).map((r) => r.url);
    expect(missing).toEqual([]);
  });

  it('builds the pages the Phase 4 done-check names', () => {
    for (const p of ['capabilities/detect', 'workflows/model-deployment', 'domains/data-analysis', 'spec/diagnostics']) {
      expect(existsSync(path.join(dist, p, 'index.html')), p).toBe(true);
    }
    expect(existsSync(path.join(dist, '404.html'))).toBe(true);
  });

  it('builds one capability page per capability, plus the overview', () => {
    const c = loadCounts();
    expect(pageDirs('capabilities').length).toBe(c.capabilityCount);
    expect(existsSync(path.join(dist, 'capabilities', 'index.html'))).toBe(true);
  });

  it('builds one page per layer', () => {
    expect(pageDirs('layers').length).toBe(loadCounts().layerCount);
  });

  it('builds one page per workflow, besides the reserved prose pages', () => {
    const dirs = pageDirs('workflows').filter((d) => !RESERVED_WORKFLOW_SLUGS.includes(d));
    expect(dirs.length).toBe(loadCounts().workflowCount);
  });

  it('builds one page per domain profile', () => {
    expect(pageDirs('domains').length).toBe(loadCounts().profileCount);
  });

  it('lists every diagnostic code, one row each', () => {
    const html = readFileSync(path.join(dist, 'spec/diagnostics/index.html'), 'utf8');
    const rows = [...html.matchAll(/<tr id="([a-z]\d{3})"/g)].map((m) => m[1]);
    const scanned = Object.values(diagnosticRowsPerSection(repoText(`spec/STANDARD-v${standardFileVersions()[0]}.md`)));
    expect(rows.length).toBe(loadCounts().diagnosticCount);
    expect(rows.length).toBe(scanned.reduce((a, b) => a + b, 0));
    expect(rows).toContain('v102');
  });

  it('marks each profile workflow that no catalog defines as proposed', () => {
    // Expected: ids each profile file lists that are not workflow keys in any catalog, by line scans.
    const defined = new Set(allCatalogSteps().keys());
    const want = profileFiles().flatMap((f) =>
      profileWorkflowIds(repoText(`schemas/profiles/${f}`)).filter((id) => !defined.has(id)),
    );
    expect(want.length).toBeGreaterThan(0);
    let proposed = 0;
    for (const d of pageDirs('domains')) {
      const html = readFileSync(path.join(dist, 'domains', d, 'index.html'), 'utf8');
      proposed += (html.match(/>Proposed, not yet in a catalog</g) ?? []).length;
    }
    expect(proposed).toBe(want.length);
    expect(proposed).toBe(loadCounts().undefinedProfileWorkflowCount);
  });

  it('marks exactly the capabilities §4.4 lists as needing a checkpoint, on their pages and tiles', () => {
    // Expected: the §4.4 table of the newest Standard, by line scan (mutate, send and rollback).
    const want = standardCheckpointCapabilities(repoText(`spec/STANDARD-v${standardFileVersions()[0]}.md`)).sort();
    expect(want).toContain('rollback');
    const badged = pageDirs('capabilities').filter((c) =>
      readFileSync(path.join(dist, 'capabilities', c, 'index.html'), 'utf8').includes('>Checkpoint required<'),
    );
    expect(badged).toEqual(want);
    const overview = readFileSync(path.join(dist, 'capabilities', 'index.html'), 'utf8');
    const tiles = [...overview.matchAll(/<a [^>]*data-capability="([a-z_]+)"[^>]*data-checkpoint="true"/g)].map((m) => m[1]);
    expect(tiles.sort()).toEqual(want);
  });

  it('builds no page outside the route table except 404', () => {
    expect(checkRouteCoverage(dist)).toEqual({ missing: [], extra: [] });
  });
});

describe('dist checks on a fixture', () => {
  const route = (url: string, extra: Partial<Route> = {}): Route => ({
    source: null,
    url,
    section: 'spec',
    order: 0,
    template: 'diagnostics',
    title: url,
    ...extra,
  });
  let dir = '';
  beforeAll(() => {
    dir = mkdtempSync(path.join(tmpdir(), 'acs-fixture-'));
    for (const f of ['index.html', 'a/index.html', 'stray/index.html', '404.html']) {
      mkdirSync(path.dirname(path.join(dir, f)), { recursive: true });
      writeFileSync(path.join(dir, f), '<html></html>');
    }
  });
  afterAll(() => rmSync(dir, { recursive: true, force: true }));

  it('maps a route URL to its page file', () => {
    expect(pageFile('/')).toBe('index.html');
    expect(pageFile('/spec/diagnostics/')).toBe('spec/diagnostics/index.html');
  });

  it('reports a route with no page and a page with no route', () => {
    expect(checkRouteCoverage(dir, [route('/'), route('/a/'), route('/b/')])).toEqual({
      missing: ['/b/'],
      extra: ['stray/index.html'],
    });
  });

  it('reports ids used twice', () => {
    expect(duplicateIds('<h2 id="x">a</h2><p id="y"></p><h3 id="x">b</h3>')).toEqual(['x']);
  });

  it('accepts ref- headings around the source headings', () => {
    const html = '<h1 id="ref-t">T</h1><h2 id="intro">Intro</h2><h2 id="ref-inputs">Inputs</h2><h2 id="inputs">Inputs</h2>';
    expect(checkGeneratedHeadings('/p/', html, ['intro', 'inputs'])).toEqual([]);
  });

  it('reports a generated heading without the prefix, a heading with no id, and a source id with the prefix', () => {
    expect(checkGeneratedHeadings('/p/', '<h2 id="inputs">Inputs</h2>', [])).toHaveLength(1);
    expect(checkGeneratedHeadings('/p/', '<h2>Inputs</h2>', [])).toEqual(['/p/: 1 heading(s) without an id']);
    expect(checkGeneratedHeadings('/p/', '<h2 id="ref-x">X</h2>', ['ref-x'])).toHaveLength(2);
  });
});
