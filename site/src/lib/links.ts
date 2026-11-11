// The resolver bound to this repository and route table, plus the counts the
// link plugin keeps so a build can report what it rewrote.
import { GITHUB_BASE, readRepoFile, TRACKED_FILES } from './repo';
import { createResolver, type LinkKind, type Resolver } from './resolve';
import { DIRECTORY_MAP, routeForSource } from './routes';
import { SITE_ORIGIN } from './origin';

export { SITE_ORIGIN };

let resolver: Resolver | undefined;

export function repoResolver(): Resolver {
  resolver ??= createResolver({
    tracked: TRACKED_FILES,
    routeOf: (source) => routeForSource(source)?.url,
    directories: DIRECTORY_MAP,
    read: readRepoFile,
    githubBase: GITHUB_BASE,
    site: SITE_ORIGIN,
  });
  return resolver;
}

export interface FileLinkStats {
  byKind: Record<LinkKind, number>;
  anchorsChecked: number;
}

export function emptyFileStats(): FileLinkStats {
  return {
    byKind: { external: 0, 'same-page': 0, route: 0, 'github-file': 0, 'directory-route': 0, 'github-tree': 0 },
    anchorsChecked: 0,
  };
}

/** Per-file counts, keyed by repo path, so a file rendered twice counts once. */
export const linkStats = new Map<string, FileLinkStats>();

export function totalLinkStats(stats: ReadonlyMap<string, FileLinkStats> = linkStats): FileLinkStats & { files: number } {
  const total = emptyFileStats();
  for (const s of stats.values()) {
    for (const k of Object.keys(total.byKind) as LinkKind[]) total.byKind[k] += s.byKind[k];
    total.anchorsChecked += s.anchorsChecked;
  }
  return { ...total, files: stats.size };
}

export function formatLinkStats(stats: ReadonlyMap<string, FileLinkStats> = linkStats): string {
  const t = totalLinkStats(stats);
  const k = t.byKind;
  return [
    `${t.files} Markdown file(s) scanned`,
    `${k.route + k['directory-route']} rewritten to site pages (${k.route} to files, ${k['directory-route']} to directories)`,
    `${k['github-file'] + k['github-tree']} sent to GitHub (${k['github-file']} files, ${k['github-tree']} directories)`,
    `${k['same-page']} same-page anchors`,
    `${t.anchorsChecked} anchors checked`,
    `${k.external} external links left as they are`,
  ].join('; ');
}
