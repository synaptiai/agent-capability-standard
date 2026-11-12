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
import { checkDistDir } from '../scripts/check-dist.mjs';
import { bareHeadings, checkGeneratedHeadings, checkRouteCoverage, duplicateIds, pageFile } from '../src/lib/check-dist';
import { ROUTES, type Route } from '../src/lib/routes';
import { EXEMPT_RUNS, pageMatches } from '../src/lib/runs';
import {
  allCatalogSteps,
  claudeLayerTable,
  diagnosticRowsPerSection,
  ontologyEdgeTriples,
  profileFiles,
  profileWorkflowIds,
  repoText,
  sectionLines,
  standardCheckpointCapabilities,
  standardFileVersions,
  symmetricEdgeTypes,
} from './independent';

let work = '';
let dist = '';

// The build gets its own output and cache directories, so the test can run
// while another Astro command (astro check, astro dev, npm run build, another
// test run) uses site/. The output directory must be inside site/: for one
// outside it, Astro puts its prerender chunks in the shared site/.astro/.
beforeAll(() => {
  work = mkdtempSync(path.join(process.cwd(), 'node_modules', '.acs-dist-test-'));
  dist = path.join(work, 'dist');
  execFileSync('npx', ['astro', 'build', '--force', '--outDir', dist], {
    cwd: process.cwd(),
    stdio: 'pipe',
    env: { ...process.env, ACS_ASTRO_CACHE_DIR: path.join(work, 'cache') },
  });
}, 300_000);

afterAll(() => {
  if (work) rmSync(work, { recursive: true, force: true });
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
    // The capability page shows the flag as the safety panel's "Needs checkpoint" cell (visual spec F-C3).
    const badged = pageDirs('capabilities').filter((c) =>
      /data-safety="checkpoint" data-on="true"/.test(readFileSync(path.join(dist, 'capabilities', c, 'index.html'), 'utf8')),
    );
    expect(badged).toEqual(want);
    const overview = readFileSync(path.join(dist, 'capabilities', 'index.html'), 'utf8');
    const tiles = [...overview.matchAll(/<a [^>]*data-capability="([a-z_]+)"[^>]*data-checkpoint="true"/g)].map((m) => m[1]);
    expect(tiles.sort()).toEqual(want);
  });

  it('draws the approval ladder with the outcome the spec rule gives at each risk level, including auto_approve none', () => {
    // Expected: each profile's threshold lines, by line scan, through the F-D2 rule as visual spec 3.5 words
    // it (low < medium < high < critical; human if require_human <= L, else review if require_review <= L,
    // else auto if auto_approve is not none and L <= auto_approve, else not covered). The page for a
    // profile is /domains/<file name with - for _>/. This replaced a check of the old "Approved
    // automatically" sentence, which the ladder figure took over (issue #125).
    const order = ['low', 'medium', 'high', 'critical'];
    const values = profileFiles().map((f) => {
      const text = repoText(`schemas/profiles/${f}`);
      const v = (k: string) => new RegExp(`^ {2}${k}: (\\w+)`, 'm').exec(text)?.[1];
      return { page: f.replace(/\.yaml$/, '').replaceAll('_', '-'), auto: v('auto_approve'), review: v('require_review'), human: v('require_human') };
    });
    expect(values.map((v) => v.auto)).toContain('none');
    for (const { page, auto, review, human } of values) {
      const want = ['low', 'medium', 'high'].map((l) => {
        const L = order.indexOf(l);
        if (human && order.indexOf(human) <= L) return 'human';
        if (review && order.indexOf(review) <= L) return 'review';
        if (auto && auto !== 'none' && L <= order.indexOf(auto)) return 'auto';
        return 'gap';
      });
      const html = readFileSync(path.join(dist, 'domains', page, 'index.html'), 'utf8');
      const table = /<table class="ladder"[\s\S]*?<\/table>/.exec(html)?.[0] ?? '';
      // One outcome at all three levels is a sentence, not a figure (visual spec 1.1 rule 5).
      if (new Set(want).size === 1) expect(table, page).toBe('');
      else expect([...table.matchAll(/data-outcome="(\w+)"/g)].map((m) => m[1]), page).toEqual(want);
    }
  });

  it('gives each generated capability and layer figure a matching figure block in the Markdown copy', () => {
    // Visual spec 6.1 and 6.3: the copy holds "**Figure: {title}.** {caption}" with the same words as the
    // page's figure title and figcaption, so the two outputs of one build are compared.
    const decode = (t: string) => t.replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
    const ids = ['ref-fig-relationships', 'ref-fig-contract', 'ref-fig-usage', 'ref-fig-layer-edges', 'ref-fig-layer-steps'];
    let seen = 0;
    for (const dir of ['capabilities', 'layers']) {
      for (const d of pageDirs(dir)) {
        const html = readFileSync(path.join(dist, dir, d, 'index.html'), 'utf8');
        const md = readFileSync(path.join(dist, dir, d, 'index.md'), 'utf8');
        for (const id of ids) {
          const fig = new RegExp(`<figure[^>]*id="${id}"[\\s\\S]*?</figure>`).exec(html)?.[0];
          if (!fig) continue;
          const title = decode(new RegExp(`id="${id}-title"[^>]*>([^<]*)<`).exec(fig)![1]!);
          const caption = decode(/<figcaption[^>]*>([^<]*)<\/figcaption>/.exec(fig)![1]!);
          expect(md, `${dir}/${d} ${id}`).toContain(`**Figure: ${title}.** ${caption}`);
          seen++;
        }
      }
    }
    expect(seen).toBeGreaterThan(pageDirs('capabilities').length);
  });

  it('draws one F-C1 tile per neighbour and one edge mark per relationship on every capability page', () => {
    // Expected: the line-scanned edge triples; a symmetric type counts once per pair (visual spec 6.3).
    const sym = new Set(symmetricEdgeTypes());
    const rel = new Map<string, Set<string>>();
    const add = (id: string, key: string) => rel.set(id, (rel.get(id) ?? new Set()).add(key));
    for (const t of ontologyEdgeTriples()) {
      if (sym.has(t.type)) {
        add(t.from, `${t.to} ${t.type}`);
        add(t.to, `${t.from} ${t.type}`);
      } else {
        add(t.from, `${t.to} ${t.type} out`);
        add(t.to, `${t.from} ${t.type} in`);
      }
    }
    expect(rel.get('mutate')?.size).toBeGreaterThan(0);
    for (const c of pageDirs('capabilities')) {
      const html = readFileSync(path.join(dist, 'capabilities', c, 'index.html'), 'utf8');
      const id = /<article [^>]*data-capability="([a-z_]+)"/.exec(html)![1]!;
      const want = rel.get(id) ?? new Set();
      const fig = /<figure[^>]*id="ref-fig-relationships"[\s\S]*?<\/figure>/.exec(html)?.[0] ?? '';
      expect((fig.match(/class="nbhd__cell"/g) ?? []).length, id).toBe(new Set([...want].map((k) => k.split(' ')[0])).size);
      expect((fig.match(/class="pg nbhd__mark"/g) ?? []).length, id).toBe(want.size);
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

  it('keeps the README heading order and draws the profile figures under its Domain Profile heading (visual spec 3.5)', () => {
    // Expected: each domain README's `# `, `## ` and `### ` lines, slugged by hand (lower case, spaces to
    // hyphens, dropping other punctuation), in file order. The figures replaced the README's own profile
    // text, which moved into a <details> under them with its H3s as H4s (issue #125).
    const slug = (line: string) => line.replace(/^#+ /, '').toLowerCase().replace(/[^a-z0-9 -]/g, '').replace(/ /g, '-');
    for (const d of pageDirs('domains')) {
      const lines = repoText(`docs/domains/${d}/README.md`).split('\n').filter((l) => !/^```/.test(l));
      const html = readFileSync(path.join(dist, 'domains', d, 'index.html'), 'utf8');
      const ids = [...html.matchAll(/<h[1-6][^>]*\sid="([^"]+)"/g)].map((m) => m[1]!);
      const h1 = slug(lines.find((l) => l.startsWith('# '))!);
      expect(ids.indexOf(h1), `${d} ${h1}`).toBe(0);
      const profile = html.indexOf('id="domain-profile"');
      const details = html.indexOf('<details class="domain-guide"');
      expect(profile, d).toBeGreaterThan(0);
      for (const kind of ['trust-weights', 'approval-ladder', 'checkpoint-policy', 'evidence-policy']) {
        const at = html.indexOf(`data-fig-kind="${kind}"`);
        // The ladder and the checkpoint policy are sentences when every level or trigger has one value.
        if (at === -1 && (kind === 'approval-ladder' || kind === 'checkpoint-policy')) continue;
        expect(at, `${d} ${kind}`).toBeGreaterThan(profile);
        expect(at, `${d} ${kind}`).toBeLessThan(details);
      }
      expect(html.indexOf('id="trust-weights"'), d).toBeGreaterThan(details);
      expect(/<h4 id="trust-weights"/.test(html), d).toBe(true);
    }
  });

  it('puts each workflow card directly under the README heading of its workflow (visual spec 3.5, F-D6)', () => {
    // Expected: the ids each profile lists, by line scan; each README H3 under "Available Workflows" with
    // its number removed, lower case, other characters as `_`.
    for (const f of profileFiles()) {
      const page = f.replace(/\.yaml$/, '').replaceAll('_', '-');
      const html = readFileSync(path.join(dist, 'domains', page, 'index.html'), 'utf8');
      const ids = profileWorkflowIds(repoText(`schemas/profiles/${f}`));
      expect(ids.length, f).toBeGreaterThan(0);
      for (const id of ids) {
        const card = html.search(new RegExp(`<div class="wf-card[^"]*" data-workflow="${id}"`));
        expect(card, `${page} ${id}`).toBeGreaterThan(0);
        const before = html.slice(0, card);
        const lastH3 = [...before.matchAll(/<h3[^>]*>([\s\S]*?)<\/h3>/g)].at(-1)!;
        const title = lastH3[1]!.replace(/<[^>]*>/g, '').replace(/^\d+\.\s*/, '').toLowerCase().replace(/[^a-z0-9]+/g, '_');
        expect(title, `${page} ${id}`).toBe(id);
        expect(before.slice(lastH3.index! + lastH3[0].length).replace(/<figure[\s\S]*$/, ''), `${page} ${id}`).not.toMatch(/<(p|ul|ol|pre|table)[\s>]/);
      }
    }
  });

  it('gives each domain profile figure a Figure block in the Markdown copy with the same caption', () => {
    for (const d of pageDirs('domains')) {
      const html = readFileSync(path.join(dist, 'domains', d, 'index.html'), 'utf8');
      const md = readFileSync(path.join(dist, 'domains', d, 'index.md'), 'utf8');
      // Every figure counts, the workflow cards included: each card's steps are a "Steps of" block in the
      // copy (visual spec 6.1), not only a line in the workflow list.
      const figs = [...html.matchAll(/<figure [^>]*data-fig-kind="(\w[\w-]*)"[\s\S]*?<figcaption class="fig__caption">([\s\S]*?)<\/figcaption>/g)]
        .map((m) => m[2]!.replace(/&#39;/g, "'").replace(/&amp;/g, '&'));
      expect(figs.length, d).toBeGreaterThan(3);
      expect((md.match(/^\*\*Figure: /gm) ?? []).length, d).toBe(figs.length);
      for (const c of figs) expect(md, `${d}: ${c}`).toContain(c);
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

  it('marks <html> with .js from the head script, which the no-JavaScript menu rules read', () => {
    for (const f of pages()) {
      expect(/^<!DOCTYPE html><html lang="en"><head><script>\s*\(\(\) => \{\s*document\.documentElement\.classList\.add\('js'\)/i.test(html(f)), f).toBe(true);
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
      for (const word of ['Agent Capability Standard', 'ACS', ' home']) expect(text, f).toContain(word);
    }
  });

  it('puts every table in a focusable region named by a label', () => {
    for (const f of pages()) {
      const h = html(f);
      const tables = (h.match(/<table[\s>]/g) ?? []).length;
      const wrapped = (h.match(/<div class="table-wrap" role="region" tabindex="0" aria-label="[^"]+"[^>]*><table[\s>]/g) ?? []).length;
      expect(wrapped, f).toBe(tables);
    }
  });

  it('points every internal link, script, stylesheet and alternate link at a file the build wrote', () => {
    const missing = new Set<string>();
    for (const f of pages()) {
      for (const m of html(f).matchAll(/\s(?:href|src)="(\/(?!\/)[^"#?]*)/g)) {
        const url = decodeURI(m[1]!);
        const file = url.endsWith('/') ? path.join(dist, url, 'index.html') : path.join(dist, url);
        if (!existsSync(file) && !existsSync(path.join(dist, url, 'index.html'))) missing.add(`${f} -> ${url}`);
      }
    }
    expect([...missing].slice(0, 10)).toEqual([]);
  });

  it('gives the capability table one wide column per layer in the CLAUDE.md table', () => {
    const layers = claudeLayerTable().length;
    expect(html('index.html')).toContain(`class="capability-table__grid" style="--layers: ${layers}"`);
  });
});

// Issue #125 rollout: the Standard's, the edge types page's and the
// diagnostics page's figures. Expected values come from scans of the
// ontology, the Standard and the built HTML, never from the figure code.
describe('Standard, edge types and diagnostics figures on the built site', () => {
  const page = (rel: string) => readFileSync(path.join(dist, rel), 'utf8');
  const figures = (h: string) => [...h.matchAll(/<figure\b([^>]*)>([\s\S]*?)<\/figure>/g)].map((m) => ({ attrs: m[1]!, body: m[2]! }));
  const SPEC_PAGES = ['spec/1.1.0/index.html', 'spec/1.0.0/index.html', 'spec/edge-types/index.html', 'spec/diagnostics/index.html'];

  it('draws where codes are raised with a row per family and a column per §5 section, and its transpose for narrow frames (F-S27)', () => {
    const std = repoText('spec/STANDARD-v1.1.0.md');
    const sections = std.split('\n').filter((l) => /^### 5\.\d+ /.test(l)).length;
    const families = sectionLines(std, /^### 9\.1 /).filter((l) => /^\| [A-Z]/.test(l) && !/^\| Category/.test(l)).length;
    const fig = figures(page('spec/1.1.0/index.html')).find((x) => x.attrs.includes('data-fig-kind="code-heat"'))!;
    const wide = /<table class="heat heat--wide">([\s\S]*?)<\/table>/.exec(fig.body)![1]!;
    const rows = [...wide.matchAll(/<tr data-family=/g)].length;
    expect(rows).toBe(families);
    const firstRow = /<tr data-family=[^>]*>([\s\S]*?)<\/tr>/.exec(wide)![1]!;
    expect([...firstRow.matchAll(/<td class="heat__cell/g)].length).toBe(sections);
    const narrow = /<div class="heat-grid heat-grid--narrow">[\s\S]*?<tbody>([\s\S]*?)<\/tbody>/.exec(fig.body)![1]!;
    expect([...narrow.matchAll(/<tr>/g)].length).toBe(sections);
  });

  it('names every figure by its title and gives it a caption, with no slot marker left behind', () => {
    for (const f of SPEC_PAGES) {
      const h = page(f);
      expect(h, f).not.toContain('data-fig-slot');
      const figs = figures(h).filter((x) => /class="fig\b/.test(x.attrs));
      expect(figs.length, f).toBeGreaterThan(0);
      for (const x of figs) {
        const label = /aria-labelledby="([^"]+)"/.exec(x.attrs)?.[1];
        expect(label, `${f}: ${x.attrs}`).toBeDefined();
        const title = new RegExp(`id="${label}"[^>]*>([^<]+)<`).exec(x.body)?.[1]?.trim();
        expect(title, `${f}: ${label}`).toBeTruthy();
        expect(x.body, `${f}: ${label}`).toMatch(/<figcaption class="fig__caption">[^<]+<\/figcaption>/);
      }
    }
  });

  it('hides each figure svg or names it as an image, and never puts a link inside an image', () => {
    // The F-E2 matrix names its image with aria-label; the rest point at their figure's title.
    for (const f of SPEC_PAGES) {
      for (const x of figures(page(f))) {
        for (const svg of x.body.matchAll(/<svg\b([^>]*)>([\s\S]*?)<\/svg>/g)) {
          const a = svg[1]!;
          const ok = /aria-hidden="true"/.test(a) || (/role="img"/.test(a) && /aria-label(ledby)?="[^"]+"/.test(a));
          expect(ok, `${f}: <svg${a.slice(0, 80)}>`).toBe(true);
          if (/role="img"/.test(a)) expect(svg[2]).not.toContain('<a ');
        }
      }
    }
  });

  it('draws one edge-type card figure per edge type of the ontology, each the first edge of its type', () => {
    const h = page('spec/edge-types/index.html');
    const triples = ontologyEdgeTriples();
    const types = [...new Set(triples.map((t) => t.type))];
    const cards = figures(h).filter((x) => /data-fig-kind="edge-type-card"/.test(x.attrs));
    expect(cards).toHaveLength(types.length);
    for (const t of types) {
      const first = triples.find((x) => x.type === t)!;
      const card = cards.find((c) => c.body.includes(`data-edge-type="${t}"`));
      expect(card, t).toBeDefined();
      expect(card!.body).toContain(`data-capability="${first.from}"`);
      expect(card!.body).toContain(`data-capability="${first.to}"`);
    }
    // The summary table and the declared-edges table are figures too.
    expect(figures(h).filter((x) => /data-fig-kind="edge-(summary|type-table)"/.test(x.attrs))).toHaveLength(2);
  });

  it('draws one code-grid tile per diagnostic code, each linking to its own row', () => {
    const h = page('spec/diagnostics/index.html');
    const grid = figures(h).find((x) => /data-fig-kind="code-grid"/.test(x.attrs))!;
    const tiles = [...grid.body.matchAll(/<a\b[^>]*>/g)].map((m) => m[0]).filter((a) => /class="diag-tile/.test(a)).map((a) => /href="#([a-z]\d{3})"/.exec(a)?.[1] ?? '');
    const scanned = Object.values(diagnosticRowsPerSection(repoText(`spec/STANDARD-v${standardFileVersions()[0]}.md`))).reduce((a, b) => a + b, 0);
    expect(tiles).toHaveLength(scanned);
    for (const t of tiles) expect(h).toContain(`<tr id="${t}"`);
  });

  it('turns every code of the current Standard\'s §9.2 to §9.7 tables into a tile linking to the diagnostics page', () => {
    const v = standardFileVersions()[0]!;
    const h = page(`spec/${v}/index.html`);
    const want = Object.values(diagnosticRowsPerSection(repoText(`spec/STANDARD-v${v}.md`))).reduce((a, b) => a + b, 0);
    const tables = figures(h).filter((x) => /data-fig-kind="code-table"/.test(x.attrs));
    const tiles = tables.flatMap((x) => [...x.body.matchAll(/<a\b[^>]*>/g)].map((m) => m[0]).filter((a) => /class="diag-tile/.test(a) && /href="\/spec\/diagnostics\/#[a-z]\d{3}"/.test(a)));
    expect(tiles).toHaveLength(want);
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

// Phase 6: Markdown copies, llms.txt, llms-full.txt, the sitemap and the
// redirect. Expected values come from walking the built directory and from
// the repository's own files, not from the route table or the loaders.
describe('agent files', () => {
  const ORIGIN = 'https://acs.synapti.ai';

  /**
   * Directories (as URL paths like /a/b/) that hold a file with this name, by
   * a walk of dist. The review pages under dist/_review/ (the glyph sheet and
   * the figure parts) are not published pages, so the walk leaves them out;
   * the last test of this block checks they are built and kept out.
   */
  function dirsWith(file: string, dir = '', out: string[] = []): string[] {
    for (const e of readdirSync(path.join(dist, dir), { withFileTypes: true })) {
      if (e.isDirectory() && dir === '' && e.name === '_review') continue;
      if (e.isDirectory()) dirsWith(file, path.posix.join(dir, e.name), out);
      else if (e.name === file) out.push(dir === '' ? '/' : `/${dir}/`);
    }
    return out.sort();
  }

  /** Heading lines outside fenced code, as written. */
  function headingLines(md: string): string[] {
    const out: string[] = [];
    let fence: string | null = null;
    for (const line of md.split('\n')) {
      const f = /^\s*(`{3,}|~{3,})/.exec(line)?.[1];
      if (f) {
        if (fence === null) fence = f[0]!;
        else if (f[0] === fence) fence = null;
        continue;
      }
      if (fence === null && /^#{1,6}\s/.test(line)) out.push(line.trim());
    }
    return out;
  }

  it('builds a Markdown copy beside every HTML page except the 404 page, and no other copy', () => {
    const html = dirsWith('index.html');
    const md = dirsWith('index.md');
    expect(html.length).toBeGreaterThan(0);
    expect(md).toEqual(html);
    expect(existsSync(path.join(dist, '404.html'))).toBe(true);
    expect(existsSync(path.join(dist, '404', 'index.md'))).toBe(false);
  });

  it('lists exactly the Markdown copies in llms.txt, each once', () => {
    const text = readFileSync(path.join(dist, 'llms.txt'), 'utf8');
    expect(text.startsWith('# Agent Capability Standard\n')).toBe(true);
    expect(text).toMatch(/^> /m);
    const listed = [...text.matchAll(/^- \[[^\]]+\]\(([^)]+)\)/gm)].map((m) => m[1]!);
    const want = dirsWith('index.md').map((d) => `${ORIGIN}${d}index.md`).sort();
    expect([...listed].sort()).toEqual(want);
    expect(new Set(listed).size).toBe(listed.length);
  });

  it('puts the current Standard first in llms-full.txt, then the rest of the Specification, Capabilities and Workflows sections', () => {
    const version = standardFileVersions()[0]!;
    const title = /^# (.+)$/m.exec(repoText(`spec/STANDARD-v${version}.md`))![1]!;
    const full = readFileSync(path.join(dist, 'llms-full.txt'), 'utf8');
    expect(full).toContain(`\n# ${title}\n`);
    const first = /<!-- (\S+) -->/.exec(full)![1];
    expect(first).toBe(`${ORIGIN}/spec/${version}/index.md`);
    // Every built page under /spec/, /capabilities/, /layers/ and /workflows/
    // (the design's Specification, Capabilities and Workflows sections), each
    // once, minus the older Standards named by the spec/STANDARD-v*.md files.
    const urls = [...full.matchAll(/^<!-- (\S+) -->$/gm)].map((m) => m[1]!.slice(ORIGIN.length));
    const older = new Set(standardFileVersions().slice(1).map((v) => `/spec/${v}/`));
    const want = dirsWith('index.md')
      .filter((d) => /^\/(spec|capabilities|layers|workflows)\//.test(d) && !older.has(d))
      .map((d) => `${d}index.md`)
      .sort();
    expect(older.size).toBeGreaterThan(0);
    expect([...urls].sort()).toEqual(want);
    expect(new Set(urls).size).toBe(urls.length);
    expect(want).toContain('/spec/diagnostics/index.md');
  });

  it('leaves no closing th, caption, dt, dd, summary or figcaption tag directly before another tag', () => {
    // Pagefind joins the words on either side of those tags (see lib/search-text.ts).
    const bad: string[] = [];
    for (const d of dirsWith('index.html')) {
      const html = readFileSync(path.join(dist, d, 'index.html'), 'utf8');
      const m = /<\/(th|caption|dt|dd|summary|figcaption)></.exec(html);
      if (m) bad.push(`${d}: ${m[0]}`);
    }
    expect(bad).toEqual([]);
  });

  it('keeps tile numbers and symbols, copy buttons and adjacent home links out of the indexed words', () => {
    // Pagefind joins these onto the next word: "1Rtretrieve", "2.0.0Copy", "specificationQuickstart".
    const bad: string[] = [];
    for (const d of dirsWith('index.html')) {
      const html = readFileSync(path.join(dist, d, 'index.html'), 'utf8');
      for (const m of html.matchAll(/<(?:span|button)\b[^>]*class="(?:capability-tile__index|capability-tile__symbol|[^"]*copy-block__button)"[^>]*>/g)) {
        if (!m[0].includes('data-pagefind-ignore')) bad.push(`${d}: ${m[0].slice(0, 60)}`);
      }
    }
    expect(bad).toEqual([]);
    const home = readFileSync(path.join(dist, 'index.html'), 'utf8');
    const links = /class="home-opening__links">([\s\S]*?)<\/p>/.exec(home)![1]!;
    expect(links).not.toContain('</a><a');
  });

  it('tags each older Standard with its version for search and weights its words down; the current one has neither', () => {
    const [current, ...older] = standardFileVersions();
    expect(older.length).toBeGreaterThan(0);
    for (const v of older) {
      const html = readFileSync(path.join(dist, 'spec', v, 'index.html'), 'utf8');
      expect(html).toContain(`<meta data-pagefind-filter="version[content]" content="${v}">`);
      expect(html).toMatch(/class="doc-main__body" data-pagefind-weight="0\.\d+"/);
    }
    const html = readFileSync(path.join(dist, 'spec', current!, 'index.html'), 'utf8');
    expect(html).not.toContain('data-pagefind-filter="version');
    expect(html).not.toContain('data-pagefind-weight');
  });

  it('frames the home page figures with a name and a caption, and writes each into the Markdown copy (visual spec 6.1)', () => {
    const html = readFileSync(path.join(dist, 'index.html'), 'utf8');
    const md = readFileSync(path.join(dist, 'index.md'), 'utf8');
    const figs = [...html.matchAll(/<figure class="fig[^"]*"[^>]*aria-labelledby="([^"]+)"[\s\S]*?<figcaption class="fig__caption">([^<]+)<\/figcaption>/g)];
    expect(figs.length).toBe(3);
    for (const [, label, caption] of figs) {
      const title = new RegExp(`id="${label}">([^<]+)<`).exec(html)![1]!;
      expect(md).toContain(`**Figure: ${title.replace(/&amp;/g, '&')}.** ${caption!.replace(/&amp;/g, '&')}`);
    }
    // One gallery strip per catalog workflow, as many squares as steps.
    const strips = [...html.matchAll(/<span role="img" aria-label="[^"]*" data-workflow="([^"]+)" data-steps="(\d+)" class="step-strip step-strip--20">/g)];
    expect(strips.map((m) => [m[1], Number(m[2])])).toEqual([...allCatalogSteps()].map(([id, c]) => [id, c.length]));
    // The story renders its final frame: no beat is hidden in the HTML.
    expect(html).not.toMatch(/data-beat="\d"[^>]*class="[^"]*is-off/);
  });

  it('gives the home page and its Markdown copy the same H2 headings and section sentences', () => {
    const html = readFileSync(path.join(dist, 'index.html'), 'utf8');
    const md = readFileSync(path.join(dist, 'index.md'), 'utf8');
    const text = (h: string) => h.replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').trim();
    const h2Html = [...html.matchAll(/<h2[^>]*>([\s\S]*?)<\/h2>/g)].map((m) => text(m[1]!));
    const h2Md = [...md.matchAll(/^## (.+)$/gm)].map((m) => m[1]!.trim());
    expect(h2Html.length).toBeGreaterThan(0);
    expect(h2Md).toEqual(h2Html);
    // The sentence under each of these headings, without its links, is in both.
    const plain = (s: string) => s.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').replace(/`/g, '').replace(/\s+/g, ' ');
    const htmlText = text(html).replace(/\s+/g, ' ');
    for (const sentence of ['They come from section', 'The steps below follow the reference workflow', 'Domain variants are parameters', 'Paste this into Claude Code']) {
      expect(htmlText).toContain(sentence);
      expect(plain(md)).toContain(sentence);
    }
  });

  it('links llms.txt, llms-full.txt, the sitemap and the page\'s own Markdown copy from every page footer', () => {
    const bad: string[] = [];
    for (const d of dirsWith('index.html')) {
      const html = readFileSync(path.join(dist, d, 'index.html'), 'utf8');
      const footer = /<footer[\s\S]*?<\/footer>/.exec(html)?.[0] ?? '';
      for (const href of ['/llms.txt', '/llms-full.txt', '/sitemap.xml', `${d}index.md`]) {
        if (!footer.includes(`href="${href}"`)) bad.push(`${d}: ${href}`);
      }
    }
    expect(bad).toEqual([]);
    const notFound = readFileSync(path.join(dist, '404.html'), 'utf8');
    expect(notFound).toContain('href="/llms.txt"');
    expect(notFound).not.toMatch(/href="\/404\/index\.md"/);
  });

  it('preloads both pixel fonts, which use font-display: optional, on every page', () => {
    // Design notes: the pixel fonts are "optional"; without a preload a first visit shows the fallback.
    const bad: string[] = [];
    for (const d of dirsWith('index.html')) {
      const html = readFileSync(path.join(dist, d, 'index.html'), 'utf8');
      for (const font of ['jersey-10', 'silkscreen']) {
        if (!new RegExp(`<link rel="preload" href="[^"]*${font}[^"]*\\.woff2" as="font"`).test(html)) bad.push(`${d}: ${font}`);
      }
    }
    expect(bad).toEqual([]);
  });

  it('offers a search for the missing path and a Search link on the 404 page', () => {
    const html = readFileSync(path.join(dist, '404.html'), 'utf8');
    expect(html).toMatch(/<button[^>]*data-not-found-query/);
    expect(html).toMatch(/<a href="https:\/\/duckduckgo\.com\/\?q=site%3Aacs\.synapti\.ai" data-not-found-open>Search<\/a>/);
  });

  it('lists every HTML page in the sitemap, minus the 404 page, and no Markdown or text file', () => {
    const xml = readFileSync(path.join(dist, 'sitemap.xml'), 'utf8');
    const locs = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]!.slice(ORIGIN.length)).sort();
    expect(locs).toEqual(dirsWith('index.html'));
    expect(locs.filter((u) => /\.(md|txt)$|404/.test(u))).toEqual([]);
    expect(readFileSync(path.join(dist, 'robots.txt'), 'utf8')).toContain(`Sitemap: ${ORIGIN}/sitemap.xml`);
  });

  it('redirects /spec/ to the newest Standard, by its file name, with a 302', () => {
    const version = standardFileVersions()[0]!;
    const rules = readFileSync(path.join(dist, '_redirects'), 'utf8')
      .split('\n')
      .filter((l) => l.trim() !== '' && !l.startsWith('#'))
      .map((l) => l.trim().split(/\s+/));
    expect(rules).toContainEqual(['/spec/', `/spec/${version}/`, '302']);
    expect(existsSync(path.join(dist, 'spec', version, 'index.html'))).toBe(true);
  });

  it('sets the Markdown and text content types and keeps pages.dev out of search engines', () => {
    const headers = readFileSync(path.join(dist, '_headers'), 'utf8');
    expect(headers).toMatch(/^\/\*\.md\n\s+Content-Type: text\/markdown/m);
    expect(headers).toMatch(/^\/llms\.txt\n\s+Content-Type: text\/plain/m);
    expect(headers).toMatch(/^\/llms-full\.txt\n\s+Content-Type: text\/plain/m);
    expect(headers).toMatch(/^https:\/\/:project\.pages\.dev\/\*\n\s+X-Robots-Tag: noindex/m);
  });

  it('leaves no relative link to a .md file in any Markdown copy', () => {
    const bad: string[] = [];
    for (const d of dirsWith('index.md')) {
      const text = readFileSync(path.join(dist, d, 'index.md'), 'utf8');
      for (const m of text.matchAll(/\]\(([^)\s]+)/g)) {
        const url = m[1]!;
        if (/^[a-z]+:/i.test(url) || url.startsWith('#')) continue;
        if (/\.md(#|$)/.test(url)) bad.push(`${d}: ${url}`);
      }
    }
    expect(bad).toEqual([]);
  });

  it('copies a Markdown page from its source, changing only link targets and adding a Source line', () => {
    // Pairs from the design notes' URL scheme: source file -> page. Pages
    // with no mermaid fence: a fence gains its text version after it in the
    // copy, which test/mermaid.test.ts checks. (The glossary was the prose
    // sample until it gained diagrams; the code of conduct has none.)
    const version = standardFileVersions()[0]!;
    const pairs: [string, string][] = [
      ['CODE_OF_CONDUCT.md', 'community/code-of-conduct'],
      ['spec/GOVERNANCE.md', 'community/governance'],
      [`spec/STANDARD-v${version}.md`, `spec/${version}`],
    ];
    const strip = (md: string) =>
      md
        .replace(/^Source: .*\n\n/m, '')
        .replace(/\]\([^)]*\)/g, ']()')
        .replace(/^\[([^\]]+)\]:\s*\S+/gm, '[$1]:')
        .trim();
    for (const [source, page] of pairs) {
      const src = repoText(source);
      // The current Standard's copy ends with the text equivalents of its
      // site-drawn figures (visual spec 3.9 and 6.1, "Figures on this page"),
      // which are not in the source; the rest must match it.
      const full = readFileSync(path.join(dist, page, 'index.md'), 'utf8');
      const appended = full.indexOf('\n## Figures on this page\n');
      if (source.startsWith('spec/STANDARD-')) expect(appended, source).toBeGreaterThan(-1);
      const copy = appended === -1 ? full : full.slice(0, appended + 1);
      expect(copy, source).toContain(`Source: [${source}](`);
      expect(headingLines(copy), source).toEqual(headingLines(src));
      expect(strip(copy), source).toBe(strip(src));
    }
  });
});

describe('check-dist.mjs on the built site', () => {
  it('finds no problem once Pagefind has run, and counts one page per route', () => {
    execFileSync('npx', ['pagefind', '--site', dist], { cwd: process.cwd(), stdio: 'pipe' });
    const { problems, stats } = checkDistDir(dist);
    expect(problems).toEqual({ files: [], links: [], 'md-links': [], copies: [], sitemap: [], figures: [], drawn: [], legends: [], review: [] });
    expect(stats.pages).toBe(ROUTES.length);
    expect(stats.copies).toBe(ROUTES.length);
  }, 120_000);
});

describe('review pages', () => {
  it('builds the glyph sheet and the figure parts, and keeps them out of the sitemap and llms.txt', () => {
    expect(existsSync(path.join(dist, '_review/glyphs/index.html'))).toBe(true);
    expect(existsSync(path.join(dist, '_review/parts/index.html'))).toBe(true);
    expect(readFileSync(path.join(dist, 'sitemap.xml'), 'utf8')).not.toContain('/_review/');
    expect(readFileSync(path.join(dist, 'llms.txt'), 'utf8')).not.toContain('/_review/');
  });

  it('removes the review pages in the deploy job before publishing', () => {
    const yml = readFileSync('../.github/workflows/site.yml', 'utf8');
    const deploy = yml.slice(yml.indexOf('\n  deploy:'));
    expect(deploy.indexOf('dist/_review')).toBeGreaterThan(-1);
    expect(deploy.indexOf('dist/_review')).toBeLessThan(deploy.indexOf('pages deploy dist'));
  });
});

// Visual spec 3.12: every exempt run names a heading that exists. A page
// entry needs its heading on that page; a template entry on at least one
// page of the template. (scripts/check-runs.mjs fails on the same thing in
// the browser; this catches it without one.)
describe('exempt runs', () => {
  it('name headings that exist on their pages', () => {
    const problems: string[] = [];
    for (const e of EXEMPT_RUNS) {
      const pages = ROUTES.filter((r) => pageMatches(e.page, r.url, r.template));
      if (pages.length === 0) {
        problems.push(`${e.page}: no page`);
        continue;
      }
      if (e.anchor === '*') continue;
      const has = pages.filter((r) => readFileSync(path.join(dist, pageFile(r.url)), 'utf8').includes(`id="${e.anchor}"`));
      if (e.page.startsWith('template:') ? has.length === 0 : has.length < pages.length) problems.push(`${e.page}#${e.anchor}`);
    }
    expect(problems).toEqual([]);
  });
});
