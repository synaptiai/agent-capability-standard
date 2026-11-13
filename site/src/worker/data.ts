// Reading the site's own static files through the ASSETS binding: the page
// index and records of the data API (/api/v1/*) and the Markdown copies.
// Nothing here calls another host.

import type { Assets } from './env';

export interface PageEntry {
  /** Root-relative page path with a trailing slash, e.g. "/capabilities/mutate/". */
  path: string;
  /** Root-relative path of the page's Markdown copy, e.g. "/capabilities/mutate/index.md". */
  markdownPath: string;
  title: string;
  description: string;
  section: string;
  headings: string[];
  /** The page's search terms: stems of its body text and the diagnostic codes it names. */
  terms: string[];
}

/** A capability or a workflow, from /api/v1/capabilities.json or /api/v1/workflows.json. */
export interface RecordEntry {
  id: string;
  description: string;
  /** Root-relative path of its page, when the record names one. */
  path: string | null;
}

function str(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

/** "https://acs.synapti.ai/a/b/" or "/a/b/" -> "/a/b/"; null for another origin or no path. */
export function sitePath(value: unknown, origin: string): string | null {
  const s = str(value).trim();
  if (s === '') return null;
  if (s.startsWith('/') && !s.startsWith('//')) return s;
  try {
    const u = new URL(s);
    return u.origin === origin ? u.pathname : null;
  } catch {
    return null;
  }
}

/** The list a collection file holds: the file itself when it is an array, else its first array-valued field of the given names. */
function listOf(json: unknown, keys: readonly string[]): unknown[] {
  if (Array.isArray(json)) return json;
  if (json && typeof json === 'object') {
    for (const k of keys) {
      const v = (json as Record<string, unknown>)[k];
      if (Array.isArray(v)) return v;
    }
  }
  return [];
}

/** One entry of /api/v1/pages.json, or null when it has no page path on this site. */
export function toPageEntry(raw: unknown, origin: string): PageEntry | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const path = sitePath(r.url ?? r.path, origin);
  if (path === null || !path.endsWith('/')) return null;
  const md = sitePath(r.markdown ?? r.markdownUrl ?? r.markdown_url ?? r.md, origin) ?? `${path}index.md`;
  const headings = Array.isArray(r.headings)
    ? r.headings
        .map((h) => (typeof h === 'string' ? h : h && typeof h === 'object' ? str((h as Record<string, unknown>).text ?? (h as Record<string, unknown>).title) : ''))
        .filter((h) => h !== '')
    : [];
  const terms = str(r.search_terms).split(' ').filter((t) => t !== '');
  return { path, markdownPath: md, title: str(r.title), description: str(r.description), section: str(r.section), headings, terms };
}

export function toRecordEntry(raw: unknown, origin: string): RecordEntry | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const id = str(r.id);
  if (id === '') return null;
  return { id, description: str(r.description) || str(r.goal), path: sitePath(r.page_url ?? r.url, origin) };
}

/**
 * The record inside a single-resource file: the data API wraps it with its
 * version and provenance ({..., "capability": {...}}); a bare record is used as it is.
 */
export function unwrap(json: unknown, key: string): Record<string, unknown> | null {
  if (!json || typeof json !== 'object' || Array.isArray(json)) return null;
  const inner = (json as Record<string, unknown>)[key];
  if (inner && typeof inner === 'object' && !Array.isArray(inner)) return inner as Record<string, unknown>;
  return json as Record<string, unknown>;
}

/** Reads the site's files. One instance per request; each index is read at most once in it. */
export class SiteData {
  private pagesP: Promise<PageEntry[] | null> | null = null;
  private readonly records = new Map<string, Promise<RecordEntry[] | null>>();

  constructor(
    private readonly assets: Assets,
    /** The origin the request came to; ASSETS ignores the host, but needs an absolute URL. */
    private readonly base: string,
    /** The production origin, for reading absolute URLs in the data. */
    private readonly origin: string,
  ) {}

  /** GET a file; null when it is not there (any status but 200). */
  async file(path: string): Promise<Response | null> {
    const res = await this.assets.fetch(new Request(new URL(path, this.base), { method: 'GET', headers: { Accept: '*/*' } }));
    return res.status === 200 ? res : null;
  }

  async text(path: string): Promise<string | null> {
    const res = await this.file(path);
    return res === null ? null : res.text();
  }

  async json(path: string): Promise<unknown> {
    const t = await this.text(path);
    if (t === null) return null;
    try {
      return JSON.parse(t) as unknown;
    } catch {
      return null;
    }
  }

  /** Every page in /api/v1/pages.json; null when the file is missing or unreadable. */
  pages(): Promise<PageEntry[] | null> {
    this.pagesP ??= this.json('/api/v1/pages.json').then((j) => {
      if (j === null) return null;
      return listOf(j, ['pages', 'items', 'data'])
        .map((p) => toPageEntry(p, this.origin))
        .filter((p): p is PageEntry => p !== null);
    });
    return this.pagesP;
  }

  /** The records of a collection file, e.g. ("capabilities") -> /api/v1/capabilities.json; null when it is missing or unreadable. */
  collection(name: 'capabilities' | 'workflows'): Promise<RecordEntry[] | null> {
    let p = this.records.get(name);
    if (!p) {
      p = this.json(`/api/v1/${name}.json`).then((j) => {
        if (j === null) return null;
        return listOf(j, [name, 'items', 'data'])
          .map((r) => toRecordEntry(r, this.origin))
          .filter((r): r is RecordEntry => r !== null);
      });
      this.records.set(name, p);
    }
    return p;
  }
}
