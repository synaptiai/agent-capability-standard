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
import { bareHeadings, checkGeneratedHeadings, checkRouteCoverage, duplicateIds, pageFile } from '../src/lib/check-dist';
import { ROUTES, type Route } from '../src/lib/routes';
import {
  allCatalogSteps,
  claudeLayerTable,
  diagnosticRowsPerSection,
  ontologyEdgeTriples,
  profileFiles,
  profileWorkflowIds,
  repoText,
  standardCheckpointCapabilities,
  standardFileVersions,
  symmetricEdgeTypes,
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

  it('states the auto-approve threshold as a sentence, including none', () => {
    // Expected: each profile's `auto_approve:` line, by line scan; the page for a profile is /domains/<file name with - for _>/.
    const values = profileFiles().map((f) => ({
      page: f.replace(/\.yaml$/, '').replaceAll('_', '-'),
      level: /^ {2}auto_approve: (\w+)/m.exec(repoText(`schemas/profiles/${f}`))?.[1],
    }));
    expect(values.map((v) => v.level)).toContain('none');
    for (const { page, level } of values) {
      const html = readFileSync(path.join(dist, 'domains', page, 'index.html'), 'utf8');
      const dd = /<dt>Approved automatically<\/dt><dd>(.*?)<\/dd>/.exec(html)?.[1]?.replace(/<[^>]+>/g, '');
      expect(dd, page).toBe(level === 'none' ? 'Nothing' : `${level} risk`);
    }
  });

  it('puts each asymmetric edge in the From cell of its source and the To cell of its target', () => {
    // Expected: the line-scanned edge triples. Wording: CLAUDE.md says a requires `from` step "must run
    // before the target", and a precedes source "must come first".
    const cells = (cap: string, type: string): [string, string] => {
      const html = readFileSync(path.join(dist, 'capabilities', cap, 'index.html'), 'utf8');
      const row = new RegExp(`<tr data-edge-type="${type}"[^>]*>(.*?)</tr>`).exec(html)?.[1];
      expect(row, `${cap} ${type} row`).toBeDefined();
      const tds = [...row!.matchAll(/<td[^>]*>(.*?)<\/td>/g)].map((m) => m[1]!);
      expect(tds, `${cap} ${type} cells`).toHaveLength(2);
      return [tds[0]!, tds[1]!];
    };
    const link = (c: string) => `href="/capabilities/${c}/"`;
    const sym = symmetricEdgeTypes();
    const triples = ontologyEdgeTriples().filter((t) => !sym.includes(t.type));
    expect(triples.map((t) => `${t.type}:${t.from}>${t.to}`)).toContain('requires:checkpoint>mutate');
    for (const t of triples) {
      const [fromOut, fromIn] = cells(t.from, t.type);
      expect(fromOut, `${t.type} ${t.from}>${t.to} on ${t.from}`).toContain(link(t.to));
      expect(fromIn, `${t.type} ${t.from}>${t.to} on ${t.from}`).not.toContain(link(t.to));
      const [toOut, toIn] = cells(t.to, t.type);
      expect(toIn, `${t.type} ${t.from}>${t.to} on ${t.to}`).toContain(link(t.from));
      expect(toOut, `${t.type} ${t.from}>${t.to} on ${t.to}`).not.toContain(link(t.from));
      if (t.type === 'requires') {
        expect(fromOut).toMatch(/>Must run before</);
        expect(toIn).toMatch(/>Must run after</);
      }
      if (t.type === 'precedes') {
        expect(fromOut).toMatch(/>Comes before/);
        expect(toIn).toMatch(/>Comes after/);
      }
    }
  });

  it('gives every heading on every built page an id', () => {
    const bare = ROUTES.flatMap((r) => {
      const html = readFileSync(path.join(dist, pageFile(r.url)), 'utf8');
      return [...html.matchAll(/<h[1-6](?![^>]*\sid=")[^>]*>/g)].map(() => r.url);
    });
    expect(bare).toEqual([]);
  });

  it('links the RFC index to the decision-making part of the governance page (design notes, ia-home RFCs 1)', () => {
    const html = readFileSync(path.join(dist, 'rfcs', 'index.html'), 'utf8');
    expect(html).toContain('href="/community/governance/#decision-making"');
  });

  it('puts the profile values after the README title and lead and before the README sections (design notes, ia-home 6.6)', () => {
    // Expected: each domain README's first `# ` and `## ` lines, slugged by hand (lower case, spaces to hyphens).
    const slug = (line: string) => line.replace(/^#+ /, '').toLowerCase().replace(/ /g, '-');
    for (const d of pageDirs('domains')) {
      const lines = repoText(`docs/domains/${d}/README.md`).split('\n');
      const h1 = slug(lines.find((l) => l.startsWith('# '))!);
      const h2 = slug(lines.find((l) => l.startsWith('## '))!);
      const ids = [...readFileSync(path.join(dist, 'domains', d, 'index.html'), 'utf8').matchAll(/<h[1-6][^>]*\sid="([^"]+)"/g)].map((m) => m[1]);
      const at = (id: string) => ids.indexOf(id);
      expect(at(h1), `${d} ${h1}`).toBe(0);
      expect(at('ref-profile-values'), d).toBeGreaterThan(at(h1));
      expect(at('ref-workflows-in-this-profile'), d).toBeGreaterThan(at('ref-profile-values'));
      expect(at(h2), `${d} ${h2}`).toBeGreaterThan(at('ref-workflows-in-this-profile'));
    }
  });

  it('builds no page outside the route table except 404', () => {
    expect(checkRouteCoverage(dist)).toEqual({ missing: [], extra: [] });
  });
});

describe('design system on the built site', () => {
  const pages = () => [...ROUTES.map((r) => pageFile(r.url)), '404.html'];
  const html = (file: string) => readFileSync(path.join(dist, file), 'utf8');

  it('runs the theme script as the first child of <head> on every page', () => {
    for (const f of pages()) {
      expect(/^<!DOCTYPE html><html lang="en"><head><script>[^<]*localStorage\.getItem\('acs-theme'\)/i.test(html(f)), f).toBe(true);
    }
  });

  it('shows the newest Standard file version in the header chip, and a skip link to the main content', () => {
    // Expected: the highest version among spec/STANDARD-v*.md file names.
    const chip = `><span class="version-chip__word">Standard </span>v${standardFileVersions()[0]}</a>`;
    for (const f of pages()) {
      const h = html(f);
      expect(h.includes(chip), f).toBe(true);
      expect(h.includes('<a class="skip-link" href="#content">'), f).toBe(true);
      expect(h.includes('<main id="content"'), f).toBe(true);
    }
  });

  it('marks exactly one sidebar link as the current page, pointing at the page itself', () => {
    for (const r of ROUTES.filter((x) => x.section !== 'home')) {
      const current = [...html(pageFile(r.url)).matchAll(/<a href="([^"]+)" aria-current="page"/g)].map((m) => m[1]);
      expect(current, r.url).toEqual([r.url]);
    }
  });

  it('loads no font from Google and builds no design preview', () => {
    for (const f of pages()) expect(html(f).includes('fonts.googleapis'), f).toBe(false);
    expect(existsSync(path.join(dist, 'design-preview'))).toBe(false);
  });

  it('builds the favicon and the social image as PNG and SVG files of the stated sizes', () => {
    const size = (f: string) => {
      const b = readFileSync(path.join(dist, f));
      expect([...b.subarray(1, 4)].map((c) => String.fromCharCode(c)).join(''), f).toBe('PNG');
      return [b.readUInt32BE(16), b.readUInt32BE(20)];
    };
    // 1200x630 is the social image size the design names; the favicon is the
    // 12-cell mark at 2px a cell inside a 4px gap and frame on each side: 12*2 + 8.
    expect(size('og.png')).toEqual([1200, 630]);
    expect(size('favicon.png')).toEqual([32, 32]);
    expect(html('favicon.svg').startsWith('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"')).toBe(true);
    expect(html('fonts/OFL.txt')).toContain('SIL Open Font License');
  });

  it('names the home link from its visible wordmark, so "ACS" and the full name are both in it (WCAG 2.5.3)', () => {
    for (const f of pages()) {
      const link = /<a class="site-header__home"([^>]*)>([\s\S]*?)<\/a>/.exec(html(f));
      expect(link, f).not.toBeNull();
      const [, attrs = '', inner = ''] = link!;
      expect(attrs.includes('aria-label'), f).toBe(false);
      const text = inner
        .replace(/<svg[\s\S]*?<\/svg>/g, '')
        .replace(/<[^>]*aria-hidden="true"[^>]*>[\s\S]*?<\/span>/g, '')
        .replace(/<[^>]+>/g, '');
      for (const word of ['Agent Capability Standard', 'ACS', 'home']) expect(text, f).toContain(word);
    }
  });

  it('gives the capability table one wide column per layer in the CLAUDE.md table', () => {
    const layers = claudeLayerTable().length;
    expect(html('index.html')).toContain(`class="capability-table__grid" style="--layers: ${layers}"`);
  });
});

describe('dist checks on a fixture', () => {
  it('reports headings with no id, on any page', () => {
    expect(bareHeadings('/p/', '<h1>T</h1><h2 class="x">A</h2><h2 id="b">B</h2>')).toBe('/p/: 2 heading(s) without an id');
    expect(bareHeadings('/p/', '<h1 id="t">T</h1><header>x</header>')).toBeNull();
  });

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

  it('reports a generated heading without the prefix and a source id with the prefix', () => {
    expect(checkGeneratedHeadings('/p/', '<h2 id="inputs">Inputs</h2>', [])).toHaveLength(1);
    expect(checkGeneratedHeadings('/p/', '<h2 id="ref-x">X</h2>', ['ref-x'])).toHaveLength(2);
  });
});
