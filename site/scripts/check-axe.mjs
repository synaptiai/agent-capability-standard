// Runs axe-core over every page of the built site, in the light and the dark
// theme, at a desktop and a phone width, and fails on any violation. At the
// phone width it also fails a page that scrolls sideways. It serves dist/
// itself and reads the page list from dist/sitemap.xml, so it checks exactly
// what the build wrote. Run it after `npm run build`.
//
// Run: node scripts/check-axe.mjs [path/to/dist] [--paths /a/,/b/]
// --paths checks only those pages (they must be in the sitemap), for a quick
// local run; CI runs every page.
// The browser is Playwright's Chromium (`npx playwright install chromium`);
// ACS_CHROMIUM names another Chromium binary to use instead.
import { createReadStream, existsSync, readFileSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { isMain } from './is-main.mjs';

/** The axe rule tags the site is held to: WCAG 2.0 to 2.2 A and AA, plus best practice. */
export const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'];
export const THEMES = ['light', 'dark'];
/** Viewport widths; the narrow one is the phone width the layout must fit without sideways scroll. */
export const WIDTHS = [1440, 360];
const NARROW = Math.min(...WIDTHS);

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.xml': 'application/xml',
  '.wasm': 'application/wasm',
};

/** The page paths in a sitemap, in its order: `https://host/a/b/` -> `/a/b/`. */
export function sitemapPaths(xml) {
  return [...xml.matchAll(/<loc>\s*([^<\s]+)\s*<\/loc>/g)].map((m) => new URL(m[1]).pathname);
}

/** The file under `dist` a request path names, or null: `/a/` -> `a/index.html`. */
export function fileFor(dist, urlPath) {
  const clean = decodeURIComponent(urlPath.split('?')[0].split('#')[0]);
  const rel = path.posix.normalize(clean).replace(/^\/+/, '');
  if (rel.startsWith('..')) return null;
  let file = path.join(dist, rel);
  if (existsSync(file) && statSync(file).isDirectory()) file = path.join(file, 'index.html');
  return existsSync(file) && statSync(file).isFile() ? file : null;
}

/** Serve `dist` on a free local port; resolves to the http.Server. */
export function serve(dist) {
  const server = createServer((req, res) => {
    const file = fileFor(dist, req.url ?? '/');
    if (!file) {
      res.writeHead(404, { 'content-type': TYPES['.html'] });
      createReadStream(path.join(dist, '404.html')).pipe(res);
      return;
    }
    res.writeHead(200, { 'content-type': TYPES[path.extname(file)] ?? 'application/octet-stream' });
    createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

/**
 * Figures that must fit their frame at the desktop width (run in the page):
 * a data-flow grid is a figure whose last columns would look like steps that
 * read nothing if they scrolled out of view. One line per grid that scrolls.
 */
export function wideScrollers() {
  const out = [];
  for (const grid of document.querySelectorAll('table.flow-grid')) {
    const wrap = grid.closest('.table-wrap') ?? grid.parentElement;
    const over = Math.round(wrap.scrollWidth - wrap.clientWidth);
    if (over > 1) out.push(`the data-flow grid "${grid.querySelector('caption')?.textContent?.trim() ?? ''}" scrolls sideways by ${over}px`);
  }
  return out;
}

/** One line per finding: `theme width path: rule (impact) xN first-target`. */
export async function runAxe(dist, { concurrency = 6, only = null, log = () => {} } = {}) {
  const { chromium } = await import('playwright');
  const { AxeBuilder } = await import('@axe-core/playwright');
  const all = sitemapPaths(readFileSync(path.join(dist, 'sitemap.xml'), 'utf8'));
  if (all.length === 0) throw new Error('check-axe: the sitemap lists no pages');
  const unknown = (only ?? []).filter((p) => !all.includes(p));
  if (unknown.length > 0) throw new Error(`check-axe: not in the sitemap: ${unknown.join(', ')}`);
  const paths = only ?? all;
  const server = await serve(dist);
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch(process.env.ACS_CHROMIUM ? { executablePath: process.env.ACS_CHROMIUM } : {});
  const findings = [];
  let runs = 0;
  try {
    for (const theme of THEMES) {
      for (const width of WIDTHS) {
        const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: theme });
        const queue = [...paths];
        await Promise.all(
          Array.from({ length: concurrency }, async () => {
            const page = await context.newPage();
            while (queue.length > 0) {
              const p = queue.shift();
              const where = `${theme} ${width} ${p}`;
              const res = await page.goto(base + p, { waitUntil: 'load' });
              if (!res || res.status() !== 200) {
                findings.push(`${where}: HTTP ${res ? res.status() : 'no response'}`);
                continue;
              }
              const result = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
              for (const v of result.violations) {
                findings.push(`${where}: ${v.id} (${v.impact}) x${v.nodes.length} ${v.nodes[0]?.target.join(' ') ?? ''}`);
              }
              if (width === NARROW) {
                const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
                if (over > 0) findings.push(`${where}: the page scrolls sideways by ${over}px`);
              } else {
                for (const s of await page.evaluate(wideScrollers)) findings.push(`${where}: ${s}`);
              }
              runs += 1;
            }
            await page.close();
          }),
        );
        await context.close();
        log(`check-axe: ${theme} ${width}px done`);
      }
    }
  } finally {
    await browser.close();
    server.close();
  }
  return { pages: paths.length, runs, findings };
}

/**
 * The pages a `--paths /a/,/b/` argument names, removed from `args`; null
 * when there is no --paths. Throws when it names no page, which would
 * otherwise check nothing and pass.
 */
export function pathsArg(args) {
  const at = args.indexOf('--paths');
  if (at === -1) return null;
  const paths = (args.splice(at, 2)[1] ?? '').split(',').filter(Boolean);
  if (paths.length === 0) throw new Error('--paths names no page; give a comma-separated list such as --paths /,/capabilities/');
  return paths;
}

if (isMain(import.meta.url)) {
  const args = process.argv.slice(2);
  const only = pathsArg(args);
  const dist = path.resolve(args[0] ?? fileURLToPath(new URL('../dist', import.meta.url)));
  const { pages, runs, findings } = await runAxe(dist, { only, log: (m) => console.log(m) });
  if (findings.length > 0) {
    console.error(`check-axe: ${findings.length} problem(s):\n  ${findings.join('\n  ')}`);
    process.exit(1);
  }
  console.log(`check-axe: ${pages} pages, ${runs} runs (${THEMES.join(' and ')} at ${WIDTHS.join(' and ')}px): no axe violations, no sideways scroll at ${NARROW}px, no data-flow grid scrolls at ${Math.max(...WIDTHS)}px`);
}
