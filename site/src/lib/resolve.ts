// The one link resolver. The remark link plugin uses it for every link in a
// Markdown source, and later the Markdown copies and generated pages use it for
// paths found in YAML. Rules, in order:
// 1. A link with an http:, https: or mailto: scheme, or starting with //, is
//    left alone. Any other scheme (javascript:, data:, vbscript:, file:) is an
//    error: GitHub drops such links, so the site must not make them live.
// 2. A bare #fragment must be an anchor of the same file. A link with only a
//    query string is an error.
// 3. Anything else is a repository path. It is percent-decoded and resolved
//    against the linking file's folder (or the root, for a leading /). A path
//    that leaves the repository is an error. docs/schemas/ is a symlink to
//    schemas/, and git lists only the link, so the prefix is rewritten.
// 4. A tracked .md file with a route becomes the route's URL. Its #fragment
//    must be one of the target's anchors.
// 5. Any other tracked file becomes its GitHub blob/main URL. This covers YAML,
//    LICENSE, excluded .md files (whose anchors are still checked) and code.
// 6. A directory with a tracked file in it becomes its mapped page, or else its
//    GitHub tree/main URL.
// 7. Anything else is an error, with the reason.
import path from 'node:path';
import { anchorsOf } from './anchors';

export type LinkKind = 'external' | 'same-page' | 'route' | 'github-file' | 'directory-route' | 'github-tree';

export interface Resolved {
  ok: true;
  kind: LinkKind;
  url: string;
  /** The link carried a #fragment that was checked against the target's headings. */
  anchorChecked: boolean;
}

export interface Unresolved {
  ok: false;
  reason: string;
}

export type Resolution = Resolved | Unresolved;

export interface ResolverContext {
  tracked: ReadonlySet<string>;
  /** Route URL of a Markdown source, e.g. `/spec/1.1.0/`. */
  routeOf: (source: string) => string | undefined;
  /** Directory (repo path, no trailing slash) to page URL. */
  directories: Readonly<Record<string, string>>;
  read: (repoPath: string) => string;
  githubBase: string;
  /** Absolute site origin, e.g. https://acs.synapti.ai, for `md` mode. */
  site: string;
}

/** `html` links to pages; `md` links to the pages' Markdown copies, absolutely. */
export type LinkMode = 'html' | 'md';

const SCHEME = /^([a-z][a-z0-9+.-]*):/i;
const SAFE_SCHEMES: ReadonlySet<string> = new Set(['http', 'https', 'mailto']);

function splitHref(href: string): { pathPart: string; fragment: string | null } {
  const hash = href.indexOf('#');
  const noHash = hash === -1 ? href : href.slice(0, hash);
  const q = noHash.indexOf('?');
  return {
    pathPart: q === -1 ? noHash : noHash.slice(0, q),
    fragment: hash === -1 ? null : href.slice(hash + 1),
  };
}

function decode(s: string): string | null {
  try {
    return decodeURIComponent(s);
  } catch {
    return null;
  }
}

export function createResolver(ctx: ResolverContext) {
  const trackedDirs = new Set<string>();
  for (const p of ctx.tracked) {
    const parts = p.split('/');
    for (let i = 1; i < parts.length; i++) trackedDirs.add(parts.slice(0, i).join('/'));
  }

  const hasAnchor = (file: string, fragment: string): boolean => {
    const frag = decode(fragment) ?? fragment;
    return anchorsOf(file, ctx.read).all.has(frag);
  };

  /** Resolve `href` written in the repo file `from`. */
  return function resolve(from: string, href: string, mode: LinkMode = 'html'): Resolution {
    const raw = href.trim();
    if (raw === '') return { ok: false, reason: 'empty link' };
    const scheme = SCHEME.exec(raw)?.[1]?.toLowerCase();
    if (scheme !== undefined && !SAFE_SCHEMES.has(scheme)) {
      return { ok: false, reason: `unsafe link scheme "${scheme}:"; only http:, https: and mailto: are allowed` };
    }
    if (scheme !== undefined || raw.startsWith('//')) {
      return { ok: true, kind: 'external', url: raw, anchorChecked: false };
    }
    const { pathPart, fragment } = splitHref(raw);
    if (fragment !== null && fragment === '' && pathPart === '') return { ok: false, reason: 'empty fragment' };

    if (pathPart === '') {
      if (fragment === null) return { ok: false, reason: 'a link with only a query string has no target' };
      if (!hasAnchor(from, fragment)) return { ok: false, reason: `no heading or anchor "#${fragment}" in this file` };
      return { ok: true, kind: 'same-page', url: `#${fragment}`, anchorChecked: true };
    }

    const decoded = decode(pathPart);
    if (decoded === null) return { ok: false, reason: 'malformed percent-encoding' };
    const wantsDir = decoded.endsWith('/');
    const base = decoded.startsWith('/') ? '.' : path.posix.dirname(from);
    let target = path.posix.normalize(path.posix.join(base, decoded.replace(/^\/+/, '')));
    if (target === '..' || target.startsWith('../')) return { ok: false, reason: 'path leaves the repository' };
    target = target.replace(/\/+$/, '');
    if (target === '.') target = '';
    if (target === 'docs/schemas' || target.startsWith('docs/schemas/')) target = `schemas${target.slice('docs/schemas'.length)}`;

    const frag = fragment === null || fragment === '' ? '' : `#${fragment}`;

    if (!wantsDir && ctx.tracked.has(target)) {
      const isMd = target.endsWith('.md');
      if (isMd && fragment) {
        if (!hasAnchor(target, fragment)) return { ok: false, reason: `no heading or anchor "#${fragment}" in ${target}` };
      }
      const anchorChecked = isMd && Boolean(fragment);
      const route = isMd ? ctx.routeOf(target) : undefined;
      if (route !== undefined) {
        const url = mode === 'md' ? `${ctx.site}${route}index.md${frag}` : `${route}${frag}`;
        return { ok: true, kind: 'route', url, anchorChecked };
      }
      return { ok: true, kind: 'github-file', url: `${ctx.githubBase}/blob/main/${target}${frag}`, anchorChecked };
    }

    if (target === '' || trackedDirs.has(target)) {
      if (fragment) return { ok: false, reason: `a directory link cannot carry "#${fragment}"` };
      const mapped = ctx.directories[target];
      if (mapped !== undefined) {
        const url = mode === 'md' ? `${ctx.site}${mapped}index.md` : mapped;
        return { ok: true, kind: 'directory-route', url, anchorChecked: false };
      }
      const url = target === '' ? ctx.githubBase : `${ctx.githubBase}/tree/main/${target}`;
      return { ok: true, kind: 'github-tree', url, anchorChecked: false };
    }

    return { ok: false, reason: `${target} is not a file or directory tracked by git` };
  };
}

export type Resolver = ReturnType<typeof createResolver>;
