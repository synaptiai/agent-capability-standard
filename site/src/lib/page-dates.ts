// When each page last changed: the date of the last commit that touched one
// of the repository files the page is built from. The sitemap's <lastmod>
// and the last_updated field of each Markdown copy's front matter read it.
//
// A page rendered from a Markdown source is built from that source (and the
// data file of a generated page that embeds one). A generated page is built
// from the data files it reads; a section overview lists the pages of its
// section, so it is built from their files.
//
// The dates come from one `git log` pass over the whole history. In a shallow
// clone every file would get the date of the one commit there is, so a
// shallow clone is an error, not a quiet wrong answer (CI checks out the full
// history for this reason).
import { execFileSync } from 'node:child_process';
import { loadProfiles } from '../data/profiles';
import { loadVersions } from '../data/versions';
import { CORE_CATALOG, loadWorkflows } from '../data/workflows';
import { REPO_ROOT } from './repo';
import { ROUTES, type Route } from './routes';

const ONTOLOGY = 'schemas/capability_ontology.yaml';

function git(args: string[]): string {
  return execFileSync('git', args, { cwd: REPO_ROOT, encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 });
}

/**
 * Parse `git log --format=%x00%cI --name-only` output into the newest
 * committer date of each path. Commits come newest first, so the first date
 * seen for a path is its last change.
 */
export function parseLogDates(log: string): Map<string, string> {
  const dates = new Map<string, string>();
  for (const chunk of log.split('\0')) {
    const lines = chunk.split('\n');
    const date = lines[0]?.trim();
    if (!date) continue;
    for (const p of lines.slice(1)) {
      const file = p.trim();
      if (file !== '' && !dates.has(file)) dates.set(file, date);
    }
  }
  return dates;
}

let cached: Map<string, string> | undefined;

/** The newest commit date (ISO 8601, committer time) of every path in the history. */
export function fileDates(): Map<string, string> {
  if (cached) return cached;
  if (git(['rev-parse', '--is-shallow-repository']).trim() === 'true') {
    throw new Error('page-dates: the repository is a shallow clone, so file dates would be wrong; fetch the full history (actions/checkout with fetch-depth: 0)');
  }
  cached = parseLogDates(git(['log', '--format=%x00%cI', '--name-only', '--no-renames', 'HEAD']));
  return cached;
}

/** The repository files a page is built from, sorted. Throws for a page that names none. */
export function pageSources(route: Route, routes: readonly Route[] = ROUTES): string[] {
  const own = [route.source, route.data].filter((p): p is string => typeof p === 'string');
  const extra: string[] = [];
  const current = loadVersions().standard.current.source;
  switch (route.template) {
    case 'home':
      extra.push(ONTOLOGY, CORE_CATALOG, current, 'CITATION.cff', '.claude-plugin/plugin.json');
      break;
    case 'listing':
    case 'rfcs-index':
      for (const r of routes) if (r.section === route.section && r.url !== route.url) extra.push(...pageSources(r, routes));
      break;
    case 'workflows-index':
      extra.push(...loadWorkflows().all.map((w) => w.source));
      break;
    case 'domains-index':
      extra.push(...loadProfiles().map((p) => p.profileFile));
      break;
    case 'diagnostics':
    case 'schemas':
      extra.push(current);
      break;
    default:
      break;
  }
  const all = [...new Set([...own, ...extra])].sort();
  if (all.length === 0) throw new Error(`page-dates: ${route.url} (${route.template}) names no file it is built from`);
  return all;
}

/** The latest of the dates of a page's files, or null when none of them is in the history yet. */
export function pageLastModified(route: Route, dates: ReadonlyMap<string, string> = fileDates()): string | null {
  let best: string | null = null;
  let bestMs = -Infinity;
  for (const p of pageSources(route)) {
    const d = dates.get(p);
    if (d === undefined) continue;
    const ms = Date.parse(d);
    if (ms > bestMs) {
      best = d;
      bestMs = ms;
    }
  }
  return best;
}
