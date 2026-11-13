// The figure-gap sweep (visual spec 4.2 and 6.3). For every page of the built
// site it measures, at 1440px wide in the light theme, the longest vertical
// run of the page body with no information figure, after subtracting the
// exempt runs of src/lib/runs.ts, and prints every run longer than two
// viewport heights. It also reports each page's longest run at 360px.
//
// Enforcing: a run over the limit on a page in the enforced scope fails the
// check (npm run check:axe, which CI runs). ACS_RUNS_ENFORCE=0 turns it into
// a report that exits 0 on long runs, for local exploration only. An
// exempt-run entry whose heading is missing, or a page that does not load,
// fails the check in either mode, so the map cannot go stale silently.
//
// Run: node scripts/check-runs.mjs [path/to/dist] [--paths /a/,/b/] [--all]
// (--all also prints every page's longest run.)
// The browser is Playwright's Chromium; ACS_CHROMIUM names another binary.
import { isDeepStrictEqual } from 'node:util';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { serve, sitemapPaths } from './check-axe.mjs';
import { isMain } from './is-main.mjs';
import { templateOf } from './page-template.mjs';
import {
  EXEMPT_RUNS,
  exemptLabel,
  exemptRunsFor,
  INFO_FIGURE_SELECTOR,
  isEnforced,
  longestRun,
  measureRuns,
  MIN_DRAWING,
  pageMatches,
  RUN_LIMIT_VH,
  RUN_TARGET_VH,
  RUN_VIEWPORT,
} from '../src/lib/runs.ts';

const NARROW = 360;

/**
 * Runs in the page: the geometry measureRuns() needs, the body's classes
 * (withTemplate() reads the template from them) and the anchors of its exempt
 * entries that are missing. Self-contained, because Playwright serialises it.
 */
export function collectGeometry({ entries, selector, min, vh }) {
  const y = (el) => {
    const r = el.getBoundingClientRect();
    return { top: r.top + window.scrollY, bottom: r.bottom + window.scrollY, width: r.width, height: r.height };
  };
  const bodyEl = document.querySelector('.doc-main__body');
  if (!bodyEl) return null;
  const { top, bottom } = y(bodyEl);
  const body = { top, bottom };
  const figures = [];
  const small = [];
  for (const el of bodyEl.querySelectorAll(selector)) {
    const drawing = el.querySelector(':scope .fig__drawing') ?? el;
    const d = y(drawing);
    const f = y(el);
    if (d.width < min.width || d.height < min.height) small.push({ top: f.top, bottom: f.bottom });
    else figures.push({ top: f.top, bottom: f.bottom });
  }
  const headings = [...bodyEl.querySelectorAll('h1, h2, h3, h4, h5, h6')].filter((h) => !h.closest('figure'));
  const level = (h) => Number(h.tagName.slice(1));
  const exempt = [];
  const missing = [];
  for (const e of entries) {
    const label = e.label;
    if (e.anchor === '*') {
      exempt.push({ key: e.key, label, top: body.top, bottom: body.bottom });
      continue;
    }
    const h = document.getElementById(e.anchor);
    if (!h || !bodyEl.contains(h)) {
      missing.push(e.key);
      continue;
    }
    const i = headings.indexOf(h);
    const next = headings.slice(i + 1).find((n) => level(n) <= level(h));
    const span = { top: y(h).top, bottom: next ? y(next).top : body.bottom };
    if ((e.extent ?? 'section') === 'section') {
      exempt.push({ key: e.key, label, ...span });
      continue;
    }
    // open-first-example: the first open <details> in the section, whole,
    // when the code blocks in it are together taller than one viewport (the
    // example's code without its sentences). A closed <details> is passed
    // over: its fences have no height a reader sees.
    const open = [...bodyEl.querySelectorAll('details[open]')].find((d) => {
      const t = y(d).top;
      return t >= span.top && t < span.bottom;
    });
    if (!open) continue;
    const code = [...open.querySelectorAll('pre')].filter((p) => p.checkVisibility()).reduce((sum, p) => sum + y(p).height, 0);
    const box = y(open);
    if (code > vh) exempt.push({ key: e.key, label, top: box.top, bottom: box.bottom });
  }
  return { classes: [...document.body.classList], geometry: { body, figures, exempt }, small, missing };
}

/** collectGeometry's result with the page's template in place of its body classes ('' when none). */
export function withTemplate(raw) {
  if (!raw) return null;
  const { classes, ...rest } = raw;
  return { template: templateOf(classes) ?? '', ...rest };
}

/** One page's result: its runs at `width`, and the exempt entries whose heading is missing. */
async function measurePage(page, url, width) {
  await page.evaluate(() => document.fonts.ready);
  // The template is known only once the page has loaded, so send every entry
  // that names this URL or any template, each with a unique key, and keep
  // the ones that apply after.
  const entries = EXEMPT_RUNS.map((e, i) => ({ ...e, key: String(i), label: exemptLabel(e) })).filter(
    (e) => e.page.startsWith('template:') || pageMatches(e.page, url, ''),
  );
  const raw = withTemplate(await page.evaluate(collectGeometry, { entries, selector: INFO_FIGURE_SELECTOR, min: MIN_DRAWING, vh: RUN_VIEWPORT.height }));
  if (!raw) return null;
  const applies = new Set(entries.filter((e) => pageMatches(e.page, url, raw.template)).map((e) => e.key));
  const geometry = { ...raw.geometry, exempt: raw.geometry.exempt.filter((e) => applies.has(e.key)) };
  return {
    template: raw.template,
    width,
    small: raw.small,
    runs: measureRuns(geometry),
    missing: raw.missing.filter((k) => applies.has(k)).map((k) => EXEMPT_RUNS[Number(k)]),
  };
}

const FIXTURE = new URL('../test/fixtures/runs-page.html', import.meta.url);
const FIXTURE_GEOMETRY = new URL('../test/fixtures/runs-page.json', import.meta.url);

/**
 * Measure the fixture page and compare with its hand-worked geometry, so a
 * browser or layout change that breaks the collector fails loudly instead of
 * reporting every page as clean. Returns a list of problems.
 */
export async function selfCheck(browser) {
  const want = JSON.parse(readFileSync(FIXTURE_GEOMETRY, 'utf8'));
  const page = await browser.newPage({ viewport: { width: RUN_VIEWPORT.width, height: RUN_VIEWPORT.height } });
  try {
    await page.setContent(readFileSync(FIXTURE, 'utf8'));
    const entries = want.entries.map((e, i) => ({ ...e, key: String(i), label: exemptLabel(e) }));
    const got = withTemplate(await page.evaluate(collectGeometry, { entries, selector: INFO_FIGURE_SELECTOR, min: MIN_DRAWING, vh: RUN_VIEWPORT.height }));
    const expected = { template: want.template, geometry: want.geometry, small: want.small, missing: want.missing };
    return isDeepStrictEqual(got, expected)
      ? []
      : [`the fixture page measured ${JSON.stringify(got)}, expected ${JSON.stringify(expected)}`];
  } finally {
    await page.close();
  }
}

/**
 * Measure every page. Returns per-page results and the problems: runs over
 * the limit on enforced pages (`over`) and exempt entries whose heading is on
 * none of their pages (`stale`).
 */
export async function runSweep(dist, { only = null, concurrency = 6, log = () => {} } = {}) {
  const { chromium } = await import('playwright');
  const all = sitemapPaths(readFileSync(path.join(dist, 'sitemap.xml'), 'utf8'));
  const unknown = (only ?? []).filter((p) => !all.includes(p));
  if (unknown.length > 0) throw new Error(`check-runs: not in the sitemap: ${unknown.join(', ')}`);
  const paths = only ?? all;
  const server = await serve(dist);
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch(process.env.ACS_CHROMIUM ? { executablePath: process.env.ACS_CHROMIUM } : {});
  const pages = new Map(paths.map((p) => [p, {}]));
  const failed = [];
  try {
    const broken = await selfCheck(browser);
    if (broken.length > 0) throw new Error(`check-runs: the collector is broken: ${broken.join('; ')}`);
    for (const width of [RUN_VIEWPORT.width, NARROW]) {
      const context = await browser.newContext({ viewport: { width, height: RUN_VIEWPORT.height }, colorScheme: 'light' });
      const queue = [...paths];
      await Promise.all(
        Array.from({ length: concurrency }, async () => {
          const page = await context.newPage();
          while (queue.length > 0) {
            const p = queue.shift();
            const res = await page.goto(base + p, { waitUntil: 'load' });
            if (!res || res.status() !== 200) {
              failed.push(`${p} at ${width}px: HTTP ${res ? res.status() : 'no response'}`);
              continue;
            }
            const r = await measurePage(page, p, width);
            if (r) pages.get(p)[width === NARROW ? 'narrow' : 'wide'] = r;
          }
          await page.close();
        }),
      );
      await context.close();
      log(`check-runs: ${width}px done`);
    }
  } finally {
    await browser.close();
    server.close();
  }
  return { ...summarise(pages, only === null), failed };
}

/**
 * Turn per-page measurements into the report. `complete` is true when every
 * page was measured, so an entry whose anchor no page has can be called stale.
 */
export function summarise(pages, complete = true) {
  const limit = RUN_LIMIT_VH * RUN_VIEWPORT.height;
  const results = [];
  const missing = [];
  const found = new Set();
  for (const [url, r] of pages) {
    if (!r.wide) continue;
    const enforced = isEnforced(url, r.wide.template);
    const longest = longestRun(r.wide.runs);
    const narrow = r.narrow ? longestRun(r.narrow.runs) : null;
    const over = r.wide.runs.filter((run) => run.height > limit);
    for (const e of exemptRunsFor(url, r.wide.template)) if (!r.wide.missing.includes(e)) found.add(e);
    // An entry for this page (not a whole template) must find its heading here.
    for (const e of r.wide.missing) if (!e.page.startsWith('template:')) missing.push(`${url}#${e.anchor}`);
    results.push({ url, template: r.wide.template, enforced, longest, narrow, over, small: r.wide.small ?? [], failing: enforced ? over.filter((run) => run.net > limit) : [] });
  }
  // A template entry is stale when no page of the template has its heading.
  const stale = complete
    ? EXEMPT_RUNS.filter((e) => e.page.startsWith('template:') && !found.has(e) && results.some((r) => `template:${r.template}` === e.page)).map(
        (e) => `${e.page}#${e.anchor}`,
      )
    : [];
  return { limit, target: RUN_TARGET_VH * RUN_VIEWPORT.height, results, missing: [...missing, ...stale] };
}

/** Report lines: every run over the limit, then the missing anchors. */
export function reportLines({ limit, results, missing }) {
  const lines = [];
  const px = (n) => `${Math.round(n)}px`;
  for (const r of [...results].sort((a, b) => (b.longest?.net ?? 0) - (a.longest?.net ?? 0))) {
    for (const run of r.over) {
      const scope = r.enforced ? (run.net > limit ? 'FAIL' : 'exempt') : 'report';
      const ex = run.exempt > 0 ? `, ${px(run.exempt)} exempt (${run.labels.join(', ')}), net ${px(run.net)}` : '';
      const n = (r.small ?? []).filter((f) => f.top >= run.top && f.bottom <= run.bottom).length;
      const sm = n > 0 ? `; ${n} figure(s) inside drawn under ${MIN_DRAWING.width}x${MIN_DRAWING.height}px, not counted` : '';
      lines.push(`${scope.padEnd(6)} ${r.url} [${r.template}] run of ${px(run.height)} from y=${px(run.top)}${ex}${sm}; longest at 360px ${px(r.narrow?.net ?? 0)}`);
    }
  }
  for (const m of missing) lines.push(`STALE  exempt run ${m}: no such heading`);
  return lines;
}

if (isMain(import.meta.url)) {
  const args = process.argv.slice(2);
  const at = args.indexOf('--paths');
  const only = at === -1 ? null : (args.splice(at, 2)[1] ?? '').split(',').filter(Boolean);
  const all = args.includes('--all');
  if (all) args.splice(args.indexOf('--all'), 1);
  const dist = path.resolve(args[0] ?? fileURLToPath(new URL('../dist', import.meta.url)));
  const enforce = process.env.ACS_RUNS_ENFORCE !== '0';
  const summary = await runSweep(dist, { only, log: (m) => console.log(m) });
  for (const l of reportLines(summary)) console.log(`check-runs: ${l}`);
  // --all: every page's longest run at 1440 (net of exempt runs) and at 360.
  if (all)
    for (const r of [...summary.results].sort((a, b) => a.url.localeCompare(b.url)))
      console.log(
        `check-runs: page ${r.url} [${r.template}] ${r.enforced ? 'enforced' : 'report'} longest ${Math.round(r.longest?.net ?? 0)}px at 1440, ${Math.round(r.narrow?.net ?? 0)}px at 360`,
      );
  const failing = summary.results.filter((r) => r.failing.length > 0);
  const underTarget = summary.results.filter((r) => (r.longest?.net ?? 0) <= summary.target).length;
  console.log(
    `check-runs: ${summary.results.length} pages; ${underTarget} meet the ${summary.target}px target; ` +
      `${failing.length} enforced page(s) have a run over ${summary.limit}px (${enforce ? 'enforced' : 'report only, because ACS_RUNS_ENFORCE=0'})`,
  );
  for (const f of summary.failed) console.error(`check-runs: ${f}`);
  if (summary.failed.length > 0) process.exit(1);
  if (summary.missing.length > 0) {
    console.error(`check-runs: ${summary.missing.length} exempt run(s) name a heading that does not exist`);
    process.exit(1);
  }
  if (enforce && failing.length > 0) process.exit(1);
}
