// The four read-only tools of the docs MCP server, their schemas and what
// they do. Each reads the site's own published files through SiteData.

import { CAPABILITY_ID, WORKFLOW_ID } from '../lib/agent-contract';
import type { PageEntry, RecordEntry, SiteData } from './data';
import { sitePath, unwrap } from './data';
import type { WorkerConfig } from './env';
import { PAGE_CHUNK, pagePart, sectionNames } from './page-text';
import { isCode, searchTerms, stem, words } from './terms';

type Json = Record<string, unknown>;

export interface ToolResult {
  content: { type: 'text'; text: string }[];
  structuredContent?: Json;
  isError: boolean;
}

/** Thrown for arguments that do not match a tool's inputSchema: a JSON-RPC -32602 error. */
export class InvalidParams extends Error {}

const ANNOTATIONS = { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false } as const;


export const TOOLS = [
  {
    name: 'read_capability',
    title: 'Read a capability',
    description:
      'Return the full record of an atomic capability in the ontology, by its id (for example "mutate" or "checkpoint"): its layer, description, input and output contracts, risk and safety flags, and the edges that connect it to other capabilities.',
    inputSchema: {
      type: 'object',
      properties: {
        id: { type: 'string', pattern: CAPABILITY_ID, description: 'The capability id, lower case, as search_standard returns it, e.g. "mutate".' },
      },
      required: ['id'],
      additionalProperties: false,
    },
    outputSchema: {
      type: 'object',
      properties: {
        id: { type: 'string', description: 'The capability id.' },
        url: { type: 'string', description: 'The capability page on the documentation site.' },
        markdownUrl: { type: 'string', description: 'The Markdown copy of that page.' },
        apiUrl: { type: 'string', description: 'The JSON record this result was read from.' },
        capability: { type: 'object', description: 'The capability record from the data API, unchanged.', additionalProperties: true },
      },
      required: ['id', 'url', 'markdownUrl', 'apiUrl', 'capability'],
      additionalProperties: false,
    },
    annotations: { title: 'Read a capability', ...ANNOTATIONS },
  },
  {
    name: 'read_page',
    title: 'Read a documentation page',
    description:
      `Return the Markdown text of one page of the documentation site, given its path from search_standard results (for example "/capabilities/mutate/" or "/spec/1.1.0/"). Use it for prose: the Standard, guides, RFCs, layer and domain pages. One call returns at most ${PAGE_CHUNK.toLocaleString('en')} characters, cut at a line end; when a page is longer, the result gives nextOffset to pass as offset for the next part, and the page's section headings. Pass section to read one section by its heading instead.`,
    inputSchema: {
      type: 'object',
      properties: {
        path: {
          type: 'string',
          minLength: 1,
          maxLength: 300,
          description: 'The page path, such as "/guides/getting-started/", or the page URL on the documentation site.',
        },
        section: {
          type: 'string',
          minLength: 1,
          maxLength: 200,
          description: 'A heading of the page, such as "Safety" (any level from ##, case ignored): return only that section, up to the next heading of its level. When a heading repeats, name it with the headings above it, such as "Claude Code skill > Inputs".',
        },
        offset: {
          type: 'integer',
          minimum: 0,
          default: 0,
          description: 'Where to start, in characters, in the page (or in the section): the nextOffset of the previous result.',
        },
      },
      required: ['path'],
      additionalProperties: false,
    },
    outputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'The page path.' },
        title: { type: 'string', description: 'The page title.' },
        url: { type: 'string', description: 'The HTML page.' },
        markdownUrl: { type: 'string', description: 'The Markdown copy the text was read from.' },
        section: { type: 'string', description: 'The section asked for, when one was.' },
        markdown: { type: 'string', description: 'The Markdown text: the page or the section, from offset, at most one part long.' },
        offset: { type: 'integer', description: 'Where this part starts, in characters.' },
        nextOffset: { type: ['integer', 'null'], description: 'The offset of the next part, or null when this part reaches the end.' },
        totalLength: { type: 'integer', description: 'The length in characters of the whole page, or of the section.' },
        sections: { type: 'array', items: { type: 'string' }, description: 'The page\'s ## headings, which section accepts; given when the text did not fit in one part.' },
      },
      required: ['path', 'title', 'url', 'markdownUrl', 'markdown', 'offset', 'nextOffset', 'totalLength'],
      additionalProperties: false,
    },
    annotations: { title: 'Read a documentation page', ...ANNOTATIONS },
  },
  {
    name: 'read_workflow',
    title: 'Read a workflow',
    description:
      'Return a reference workflow from the workflow catalogs, by its catalog id: the ordered capability steps, their bindings and gates, and the safety checkpoints the workflow places before mutations.',
    inputSchema: {
      type: 'object',
      properties: {
        id: { type: 'string', pattern: WORKFLOW_ID, description: 'The workflow id as the catalog names it, as search_standard returns it, e.g. "debug_code_change".' },
      },
      required: ['id'],
      additionalProperties: false,
    },
    outputSchema: {
      type: 'object',
      properties: {
        id: { type: 'string', description: 'The workflow id.' },
        apiUrl: { type: 'string', description: 'The JSON record this result was read from.' },
        url: { type: 'string', description: 'The workflow page on the documentation site, when the record names one.' },
        workflow: { type: 'object', description: 'The workflow record from the data API, unchanged.', additionalProperties: true },
      },
      required: ['id', 'apiUrl', 'workflow'],
      additionalProperties: false,
    },
    annotations: { title: 'Read a workflow', ...ANNOTATIONS },
  },
  {
    name: 'search_standard',
    title: 'Search the Standard',
    description:
      'Search the pages of the Agent Capability Standard site for the words of a query. It matches page titles, descriptions, headings, capability and workflow ids, and each page\'s search terms: the words that most set its text apart, and every diagnostic code it names (such as V102). It does not search every word of the full text. Results are ranked by where the words appear and how many of them a page has, so a page with only some of the words can still appear. Returns each match with its page path, URL, Markdown URL and, for a capability or workflow, the id to pass to read_capability or read_workflow. Start here.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', minLength: 1, maxLength: 200, description: 'Words to look for, e.g. "checkpoint before mutation".' },
        limit: { type: 'integer', minimum: 1, maximum: 25, default: 8, description: 'The most results to return (1 to 25, default 8).' },
      },
      required: ['query'],
      additionalProperties: false,
    },
    outputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'The query as received.' },
        terms: { type: 'array', items: { type: 'string' }, description: 'The search words taken from the query: stopwords dropped, lower case, stemmed.' },
        matched: { type: 'string', enum: ['all', 'any'], description: '"all" when at least one result has every search word (or nothing matched); "any" when no page has them all.' },
        total: { type: 'integer', description: 'How many entries matched, before the limit.' },
        results: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              kind: { type: 'string', enum: ['page', 'capability', 'workflow'], description: 'What the result is.' },
              id: { type: 'string', description: 'For a capability or workflow, the id to pass to read_capability or read_workflow.' },
              title: { type: 'string' },
              path: { type: 'string', description: 'The page path to pass to read_page.' },
              url: { type: 'string' },
              markdownUrl: { type: 'string' },
              section: { type: 'string' },
              description: { type: 'string' },
              matchedTerms: { type: 'integer', description: 'How many of the search words this result has.' },
              score: { type: 'number', description: 'Higher is a closer match.' },
            },
            required: ['kind', 'title', 'path', 'url', 'markdownUrl', 'matchedTerms', 'score'],
            additionalProperties: false,
          },
        },
      },
      required: ['query', 'terms', 'matched', 'total', 'results'],
      additionalProperties: false,
    },
    annotations: { title: 'Search the Standard', ...ANNOTATIONS },
  },
] as const;

export type ToolName = (typeof TOOLS)[number]['name'];

export function isToolName(name: unknown): name is ToolName {
  return TOOLS.some((t) => t.name === name);
}

// ------------------------------------------------------------ argument checks

function args(raw: unknown): Json {
  if (raw === undefined || raw === null) return {};
  if (typeof raw !== 'object' || Array.isArray(raw)) throw new InvalidParams('arguments must be an object');
  return raw as Json;
}

function onlyKeys(a: Json, keys: readonly string[], tool: string) {
  for (const k of Object.keys(a)) if (!keys.includes(k)) throw new InvalidParams(`${tool}: unknown argument "${k}"; it takes ${keys.join(', ')}`);
}

function requiredString(a: Json, key: string, tool: string, { max, pattern }: { max: number; pattern?: RegExp }): string {
  const v = a[key];
  if (typeof v !== 'string' || v.trim() === '') throw new InvalidParams(`${tool}: "${key}" is required and must be a non-empty string`);
  if (v.length > max) throw new InvalidParams(`${tool}: "${key}" is longer than ${max} characters`);
  if (pattern && !pattern.test(v)) throw new InvalidParams(`${tool}: "${key}" must match ${pattern.source}`);
  return v;
}

const CAPABILITY_RE = new RegExp(CAPABILITY_ID);
const WORKFLOW_RE = new RegExp(WORKFLOW_ID);

// ------------------------------------------------------------ results

function ok(data: Json): ToolResult {
  return { content: [{ type: 'text', text: JSON.stringify(data) }], structuredContent: data, isError: false };
}

function failed(message: string): ToolResult {
  return { content: [{ type: 'text', text: message }], isError: true };
}

// ------------------------------------------------------------ search

interface Kind {
  kind: 'page' | 'capability' | 'workflow';
  id?: string;
  record?: RecordEntry;
}

/** What a page shows: a capability or workflow (with its id) when a record names the page, else a page. */
function kindOf(path: string, caps: Map<string, RecordEntry>, flows: Map<string, RecordEntry>, capsKnown: boolean): Kind {
  const cap = caps.get(path);
  if (cap) return { kind: 'capability', id: cap.id, record: cap };
  const flow = flows.get(path);
  if (flow) return { kind: 'workflow', id: flow.id, record: flow };
  // Without the capability index, a capability page is still known by its path.
  const m = capsKnown ? null : /^\/capabilities\/([a-z][a-z0-9_-]*)\/$/.exec(path);
  return m ? { kind: 'capability', id: m[1]! } : { kind: 'page' };
}

/** How one page matches a query: how many of its search terms it has, and a score for ranking. */
export interface PageMatch {
  matched: number;
  score: number;
}

/**
 * Match one page against the search terms. Each term the page has counts in
 * `matched` and adds to the score: most for the capability or workflow id
 * and for a diagnostic code the page defines (`defines`), then the title,
 * the path, the description and headings, the section, and least the page's
 * own search terms (its body text). The query as a phrase adds more in the
 * title or a heading. The score is then scaled by the share of the terms the
 * page has, so a page with every word outranks a page with half of them
 * unless the half sits in its title or id.
 */
export function scorePage(
  page: PageEntry,
  terms: readonly string[],
  phrase: string,
  record: RecordEntry | undefined,
  defines: ReadonlySet<string> = new Set(),
): PageMatch {
  // Terms match whole stemmed words, never parts of words: "e" must not
  // match every page that has an "e" in its title.
  const stems = (x: string) => new Set(words(x).map(stem));
  const title = page.title.toLowerCase();
  const titleWords = stems(title);
  const pathWords = stems(page.path);
  const descWords = stems(`${page.description} ${record?.description ?? ''}`);
  const heads = page.headings.join(' \n ').toLowerCase();
  const headWords = stems(heads);
  const sectionWords = stems(page.section);
  // An id such as debug_code_change is several words; it counts when the query has all of them.
  const idWords = record ? [...stems(record.id)] : [];
  const idMatched = idWords.length > 0 && idWords.every((w) => terms.includes(w));
  let score = 0;
  let matched = 0;
  for (const t of terms) {
    let s = 0;
    if (titleWords.has(t)) s += 6;
    if (pathWords.has(t)) s += 3;
    if (descWords.has(t)) s += 2;
    if (headWords.has(t)) s += 2;
    if (sectionWords.has(t)) s += 1;
    if (page.terms.includes(t)) s += 1;
    if (idMatched && idWords.includes(t)) s += 10 / idWords.length;
    if (defines.has(t)) s += 10;
    if (s > 0) matched += 1;
    score += s;
  }
  if (matched === 0) return { matched, score: 0 };
  if (phrase.includes(' ')) {
    if (title.includes(phrase)) score += 8;
    else if (heads.includes(phrase)) score += 4;
  } else if (phrase.length > 0 && title.includes(phrase)) score += 8;
  return { matched, score: Math.round((score * matched * 100) / terms.length) / 100 };
}

/** Each diagnostic code (lower case, as a search term) and the path of the page that defines it, from /api/v1/diagnostics.json. */
async function codePages(data: SiteData, cfg: WorkerConfig): Promise<Map<string, string>> {
  const out = new Map<string, string>();
  const j = (await data.json('/api/v1/diagnostics.json')) as { diagnostics?: unknown } | null;
  if (!j || !Array.isArray(j.diagnostics)) return out;
  for (const d of j.diagnostics as Record<string, unknown>[]) {
    const p = typeof d.code === 'string' ? sitePath(String(d.page_url ?? '').replace(/#.*$/, ''), cfg.origin) : null;
    if (p !== null) out.set((d.code as string).toLowerCase(), p);
  }
  return out;
}

async function searchStandard(a: Json, data: SiteData, cfg: WorkerConfig): Promise<ToolResult> {
  onlyKeys(a, ['query', 'limit'], 'search_standard');
  const query = requiredString(a, 'query', 'search_standard', { max: 200 });
  let limit = 8;
  if (a.limit !== undefined) {
    if (typeof a.limit !== 'number' || !Number.isInteger(a.limit) || a.limit < 1 || a.limit > 25) {
      throw new InvalidParams('search_standard: "limit" must be an integer from 1 to 25');
    }
    limit = a.limit;
  }
  const terms = searchTerms(query);
  if (terms.length === 0) throw new InvalidParams('search_standard: "query" has no letters or digits to search for');
  const pages = await data.pages();
  if (pages === null) return failed('The page index (/api/v1/pages.json) could not be read, so the search cannot run. Try again later.');
  const capList = await data.collection('capabilities');
  const byPath = (list: RecordEntry[] | null) => new Map((list ?? []).filter((r) => r.path !== null).map((r) => [r.path!, r]));
  const caps = byPath(capList);
  const flows = byPath(await data.collection('workflows'));
  const phrase = words(query).join(' ');
  const codes = terms.some(isCode) ? await codePages(data, cfg) : new Map<string, string>();
  const defines = (path: string) => new Set(terms.filter((t) => codes.get(t) === path));
  // A page whose address redirects (such as /spec/) is never what a reader sees there, so it is not a result.
  const entries = pages.filter((p) => redirectedPage(cfg, p.path) === p.path).map((p) => ({ p, k: kindOf(p.path, caps, flows, capList !== null) }));
  const scored = entries
    .map((e) => ({ ...e, ...scorePage(e.p, terms, phrase, e.k.record, defines(e.p.path)) }))
    .filter((e) => e.matched > 0)
    .sort((x, y) => y.score - x.score || y.matched - x.matched || x.p.path.localeCompare(y.p.path));
  const matched: 'all' | 'any' = scored.length === 0 || scored.some((e) => e.matched === terms.length) ? 'all' : 'any';
  const results = scored.slice(0, limit).map(({ p, k, score, matched: has }) => ({
    kind: k.kind,
    ...(k.id ? { id: k.id } : {}),
    title: p.title,
    path: p.path,
    url: `${cfg.origin}${p.path}`,
    markdownUrl: `${cfg.origin}${p.markdownPath}`,
    section: p.section,
    description: p.description || k.record?.description || '',
    matchedTerms: has,
    score,
  }));
  return ok({ query, terms, matched, total: scored.length, results });
}

// ------------------------------------------------------------ reads

async function readCapability(a: Json, data: SiteData, cfg: WorkerConfig): Promise<ToolResult> {
  onlyKeys(a, ['id'], 'read_capability');
  const id = requiredString(a, 'id', 'read_capability', { max: 64, pattern: CAPABILITY_RE });
  const apiPath = `/api/v1/capabilities/${id}.json`;
  const record = unwrap(await data.json(apiPath), 'capability');
  if (record === null) {
    return failed(`There is no capability with the id "${id}". Ids are lower case, such as "mutate"; search_standard lists them, and /api/v1/capabilities.json has all of them.`);
  }
  const page = sitePath(record.page_url, cfg.origin) ?? `/capabilities/${id}/`;
  const md = sitePath(record.markdown_url, cfg.origin) ?? `${page}index.md`;
  return ok({ id, url: `${cfg.origin}${page}`, markdownUrl: `${cfg.origin}${md}`, apiUrl: `${cfg.origin}${apiPath}`, capability: record });
}

async function readWorkflow(a: Json, data: SiteData, cfg: WorkerConfig): Promise<ToolResult> {
  onlyKeys(a, ['id'], 'read_workflow');
  const id = requiredString(a, 'id', 'read_workflow', { max: 128, pattern: WORKFLOW_RE });
  const apiPath = `/api/v1/workflows/${id}.json`;
  const record = unwrap(await data.json(apiPath), 'workflow');
  if (record === null) {
    return failed(`There is no workflow with the id "${id}". search_standard returns workflow ids, and /api/v1/workflows.json lists all of them.`);
  }
  const page = sitePath(record.page_url ?? record.url, cfg.origin);
  return ok({ id, apiUrl: `${cfg.origin}${apiPath}`, ...(page ? { url: `${cfg.origin}${page}` } : {}), workflow: record });
}

/** "/a/b", "a/b/", "/a/b/index.md", "/a/b.md" or the page URL -> "/a/b/"; null when it cannot be a page path. */
export function normalizePagePath(input: string, origin: string): string | null {
  let s = input.trim();
  if (/^[a-z][a-z0-9+.-]*:/i.test(s)) {
    try {
      const u = new URL(s);
      if (u.origin !== origin) return null;
      s = u.pathname;
    } catch {
      return null;
    }
  }
  s = s.replace(/[?#].*$/, '');
  if (!s.startsWith('/')) s = `/${s}`;
  s = s.replace(/\/index\.(md|html)$/, '/').replace(/\.md$/, '/');
  if (!s.endsWith('/')) s = `${s}/`;
  if (s.split('/').some((seg) => seg === '..' || seg === '.')) return null;
  return s;
}

/** The page a path shows: the target of a redirect to a page, or the path itself. */
export function redirectedPage(cfg: WorkerConfig, path: string): string {
  const target = Object.prototype.hasOwnProperty.call(cfg.redirects, path) ? cfg.redirects[path]! : null;
  return target !== null && target.endsWith('/') ? target : path;
}

async function readPage(a: Json, data: SiteData, cfg: WorkerConfig): Promise<ToolResult> {
  onlyKeys(a, ['path', 'section', 'offset'], 'read_page');
  const raw = requiredString(a, 'path', 'read_page', { max: 300 });
  const section = a.section === undefined ? undefined : requiredString(a, 'section', 'read_page', { max: 200 });
  if (a.offset !== undefined && (typeof a.offset !== 'number' || !Number.isInteger(a.offset) || a.offset < 0)) {
    throw new InvalidParams('read_page: "offset" must be an integer of 0 or more');
  }
  const offset = (a.offset as number | undefined) ?? 0;
  const path = normalizePagePath(raw, cfg.origin);
  if (path === null) throw new InvalidParams(`read_page: "${raw}" is not a page path on ${cfg.origin}`);
  const pages = await data.pages();
  if (pages === null) return failed('The page index (/api/v1/pages.json) could not be read, so the page cannot be looked up. Try again later.');
  // A page address that redirects (such as /spec/) reads the page it redirects to, as a browser would.
  const shown = redirectedPage(cfg, path);
  const page = pages.find((p) => p.path === shown);
  if (!page) return failed(`There is no page at ${path}. Use a path from search_standard results, such as "/capabilities/mutate/".`);
  const markdown = await data.text(page.markdownPath);
  if (markdown === null) return failed(`The Markdown copy of ${path} (${page.markdownPath}) could not be read.`);
  const part = pagePart(markdown, { section, offset });
  if (!part.ok) return failed(part.headings.length > 0 ? `${part.message} Its headings: ${part.headings.join(', ')}.` : part.message);
  const cut = part.offset > 0 || part.nextOffset !== null;
  return ok({
    path: page.path,
    title: page.title,
    url: `${cfg.origin}${page.path}`,
    markdownUrl: `${cfg.origin}${page.markdownPath}`,
    ...(section !== undefined ? { section } : {}),
    markdown: part.markdown,
    offset: part.offset,
    nextOffset: part.nextOffset,
    totalLength: part.totalLength,
    ...(cut && section === undefined ? { sections: sectionNames(markdown) } : {}),
  });
}

/** Run a tool. Throws InvalidParams for arguments that do not fit its inputSchema. */
export async function callTool(name: ToolName, rawArgs: unknown, data: SiteData, cfg: WorkerConfig): Promise<ToolResult> {
  const a = args(rawArgs);
  switch (name) {
    case 'search_standard':
      return searchStandard(a, data, cfg);
    case 'read_capability':
      return readCapability(a, data, cfg);
    case 'read_workflow':
      return readWorkflow(a, data, cfg);
    case 'read_page':
      return readPage(a, data, cfg);
  }
}
