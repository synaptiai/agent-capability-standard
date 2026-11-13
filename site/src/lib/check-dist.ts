// Checks on the built site, run when a build finishes and by the tests:
// - every route in the table has an index.html, and no other page was built
//   (the 404 page aside);
// - no page uses an element id twice, and every heading on every page has an id;
// - on a generated page that shows a Markdown source, the headings the page
//   adds have `ref-` ids and the rest are exactly the ids GitHub gives the
//   source; on a generated page with no source, every heading id has the prefix.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { githubHeadingIds, REF_ID_PREFIX, renderedHeadingIds } from './check-slugs';
import { readRepoFile } from './repo';
import { REVIEW_DIR } from './review';
import { MARKDOWN_TEMPLATES, ROUTES, type Route } from './routes';

export { REF_ID_PREFIX };

/** dist path of a route's page: `/a/b/` -> `a/b/index.html`, `/` -> `index.html`. */
export function pageFile(url: string): string {
  return path.posix.join(url.replace(/^\//, ''), 'index.html');
}

/** HTML files under dir, the review pages (dist/_review/, not routes) aside. */
function htmlFiles(dir: string, base = dir): string[] {
  const out: string[] = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory() && dir === base && e.name === REVIEW_DIR) continue;
    if (e.isDirectory()) out.push(...htmlFiles(p, base));
    else if (e.name.endsWith('.html')) out.push(path.relative(base, p).split(path.sep).join('/'));
  }
  return out.sort();
}

export interface DistReport {
  missing: string[];
  extra: string[];
  problems: string[];
  pages: number;
}

/** Routes with no built page, and built pages with no route. */
export function checkRouteCoverage(distDir: string, routes: readonly Route[] = ROUTES): { missing: string[]; extra: string[] } {
  const want = new Set(routes.map((r) => pageFile(r.url)));
  const missing = routes.filter((r) => !existsSync(path.join(distDir, pageFile(r.url)))).map((r) => r.url);
  const extra = htmlFiles(distDir).filter((f) => !want.has(f) && f !== '404.html');
  return { missing, extra };
}

/** Every `id="..."` value on a page that occurs more than once. */
export function duplicateIds(html: string): string[] {
  const seen = new Map<string, number>();
  for (const m of html.matchAll(/\sid="([^"]*)"/g)) seen.set(m[1]!, (seen.get(m[1]!) ?? 0) + 1);
  return [...seen].filter(([, n]) => n > 1).map(([id]) => id);
}

/**
 * Heading ids of a generated page. `sourceIds` are the ids GitHub gives the
 * Markdown it shows (empty when it shows none). Returns problems, one per line.
 */
export function checkGeneratedHeadings(url: string, html: string, sourceIds: string[]): string[] {
  const problems: string[] = [];
  const ids = renderedHeadingIds(html);
  const own = ids.filter((id) => !id.startsWith(REF_ID_PREFIX));
  if (own.length !== sourceIds.length || own.some((id, i) => id !== sourceIds[i])) {
    problems.push(`${url}: heading ids without the ${REF_ID_PREFIX} prefix are [${own.join(', ')}], expected the source's [${sourceIds.join(', ')}]`);
  }
  const clash = sourceIds.filter((id) => id.startsWith(REF_ID_PREFIX));
  if (clash.length > 0) problems.push(`${url}: the source has heading ids with the ${REF_ID_PREFIX} prefix: ${clash.join(', ')}`);
  return problems;
}

/** A problem line when headings on the page have no id, else null. */
export function bareHeadings(url: string, html: string): string | null {
  const bare = [...html.matchAll(/<h[1-6](?![^>]*\sid=")[^>]*>/g)].length;
  return bare > 0 ? `${url}: ${bare} heading(s) without an id` : null;
}

/** Run every check on a built site. */
export function checkDist(distDir: string, routes: readonly Route[] = ROUTES): DistReport {
  const { missing, extra } = checkRouteCoverage(distDir, routes);
  const problems: string[] = [];
  let pages = 0;
  for (const r of routes) {
    const file = path.join(distDir, pageFile(r.url));
    if (!existsSync(file)) continue;
    pages += 1;
    const html = readFileSync(file, 'utf8');
    const dups = duplicateIds(html);
    if (dups.length > 0) problems.push(`${r.url}: ids used more than once: ${dups.join(', ')}`);
    const bare = bareHeadings(r.url, html);
    if (bare) problems.push(bare);
    const ownPage = r.source !== null && MARKDOWN_TEMPLATES.has(r.template) && !r.embed;
    if (ownPage) continue; // check-slugs.ts compares these with their sources, ref- ids aside.
    const sourceIds = r.source === null ? [] : githubHeadingIds(readRepoFile(r.source));
    problems.push(...checkGeneratedHeadings(r.url, html, sourceIds));
  }
  return { missing, extra, problems, pages };
}

export function formatDistReport(report: DistReport): string[] {
  return [
    ...report.missing.map((u) => `${u}: route has no built page`),
    ...report.extra.map((f) => `${f}: built page has no route`),
    ...report.problems,
  ];
}
