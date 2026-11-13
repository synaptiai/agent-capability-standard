// The four read-only tools of the docs MCP server, their schemas and what
// they do. Each reads the site's own published files through SiteData.

import type { PageEntry, RecordEntry, SiteData } from './data';
import { sitePath, unwrap } from './data';
import type { WorkerConfig } from './env';

type Json = Record<string, unknown>;

export interface ToolResult {
  content: { type: 'text'; text: string }[];
  structuredContent?: Json;
  isError: boolean;
}

/** Thrown for arguments that do not match a tool's inputSchema: a JSON-RPC -32602 error. */
export class InvalidParams extends Error {}

const ANNOTATIONS = { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false } as const;

const ID_PATTERN = '^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$';

export const TOOLS = [
  {
    name: 'read_capability',
    title: 'Read a capability',
    description:
      'Return the full record of an atomic capability in the ontology, by its id (for example "mutate" or "checkpoint"): its layer, description, input and output contracts, risk and safety flags, and the edges that connect it to other capabilities.',
    inputSchema: {
      type: 'object',
      properties: {
        id: { type: 'string', pattern: ID_PATTERN, description: 'The capability id, lower case, as search_standard returns it, e.g. "mutate".' },
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
      'Return the full Markdown text of one page of the documentation site, given its path from search_standard results (for example "/capabilities/mutate/" or "/spec/1.1.0/"). Use it for prose: the Standard, guides, RFCs, layer and domain pages.',
    inputSchema: {
      type: 'object',
      properties: {
        path: {
          type: 'string',
          minLength: 1,
          maxLength: 300,
          description: 'The page path, such as "/guides/getting-started/", or the page URL on the documentation site.',
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
        markdown: { type: 'string', description: 'The full Markdown text of the page.' },
      },
      required: ['path', 'title', 'url', 'markdownUrl', 'markdown'],
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
        id: { type: 'string', pattern: ID_PATTERN, description: 'The workflow id as the catalog names it, as search_standard returns it.' },
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
      'Search every page of the Agent Capability Standard site and the capability names and descriptions for words in a query. Returns ranked matches with their page path, URL, Markdown URL and, for capabilities and workflows, the id to pass to read_capability or read_workflow. Start here.',
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
        matched: { type: 'string', enum: ['all', 'any'], description: '"all" when every result has every search word; "any" when no page had them all and results have some.' },
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
              score: { type: 'number', description: 'Higher is a closer match.' },
            },
            required: ['kind', 'title', 'path', 'url', 'markdownUrl', 'score'],
            additionalProperties: false,
          },
        },
      },
      required: ['query', 'matched', 'total', 'results'],
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

const ID_RE = new RegExp(ID_PATTERN);

// ------------------------------------------------------------ results

function ok(data: Json): ToolResult {
  return { content: [{ type: 'text', text: JSON.stringify(data) }], structuredContent: data, isError: false };
}

function failed(message: string): ToolResult {
  return { content: [{ type: 'text', text: message }], isError: true };
}

// ------------------------------------------------------------ search

function words(s: string): string[] {
  return s.toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? [];
}

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

/** Words too common to narrow a search. */
const STOPWORDS = new Set(
  'a an and are as at be before by can do does for from how i in into is it its of on or should that the then this to what when where which who why with'.split(' '),
);

/** A crude stem, so "mutation", "mutates" and "mutate" meet at "mutat". */
export function stem(word: string): string {
  for (const suffix of ['ations', 'ation', 'ions', 'ion', 'ing', 'ies', 'ed', 'es', 's', 'e']) {
    if (word.endsWith(suffix) && word.length - suffix.length >= 4) return word.slice(0, -suffix.length);
  }
  return word;
}

/** The search terms of a query: its words without stopwords (all of them when every word is one), stemmed. */
export function searchTerms(query: string): string[] {
  const all = words(query);
  const kept = all.filter((w) => !STOPWORDS.has(w));
  return [...new Set((kept.length > 0 ? kept : all).map(stem))];
}

/**
 * Score one page against the search terms. With `all`, a page that misses a
 * term scores 0; without it, each term that matches adds to the score.
 */
export function scorePage(page: PageEntry, terms: readonly string[], phrase: string, record: RecordEntry | undefined, all = true): number {
  const title = page.title.toLowerCase();
  const titleWords = words(title).map(stem);
  const path = page.path.toLowerCase();
  const desc = `${page.description} ${record?.description ?? ''}`.toLowerCase();
  const heads = page.headings.join(' \n ').toLowerCase();
  const section = page.section.toLowerCase();
  let score = 0;
  for (const t of terms) {
    let s = 0;
    if (titleWords.includes(t)) s += 6;
    else if (title.includes(t)) s += 4;
    if (path.includes(t)) s += 3;
    if (desc.includes(t)) s += 2;
    if (heads.includes(t)) s += 2;
    if (section.includes(t)) s += 1;
    if (record && stem(record.id.toLowerCase()) === t) s += 10;
    if (s === 0 && all) return 0;
    score += s;
  }
  if (phrase.length > 0 && title.includes(phrase)) score += 8;
  return score;
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
  const entries = pages.map((p) => ({ p, k: kindOf(p.path, caps, flows, capList !== null) }));
  const rank = (all: boolean) =>
    entries
      .map((e) => ({ ...e, score: scorePage(e.p, terms, phrase, e.k.record, all) }))
      .filter((e) => e.score > 0)
      .sort((x, y) => y.score - x.score || x.p.path.localeCompare(y.p.path));
  // Pages that match every term first; when none does, pages that match any.
  let scored = rank(true);
  const matched: 'all' | 'any' = scored.length > 0 || terms.length === 1 ? 'all' : 'any';
  if (matched === 'any') scored = rank(false);
  const results = scored.slice(0, limit).map(({ p, k, score }) => ({
    kind: k.kind,
    ...(k.id ? { id: k.id } : {}),
    title: p.title,
    path: p.path,
    url: `${cfg.origin}${p.path}`,
    markdownUrl: `${cfg.origin}${p.markdownPath}`,
    section: p.section,
    description: p.description || k.record?.description || '',
    score,
  }));
  return ok({ query, matched, total: scored.length, results });
}

// ------------------------------------------------------------ reads

async function readCapability(a: Json, data: SiteData, cfg: WorkerConfig): Promise<ToolResult> {
  onlyKeys(a, ['id'], 'read_capability');
  const id = requiredString(a, 'id', 'read_capability', { max: 128, pattern: ID_RE });
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
  const id = requiredString(a, 'id', 'read_workflow', { max: 128, pattern: ID_RE });
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

async function readPage(a: Json, data: SiteData, cfg: WorkerConfig): Promise<ToolResult> {
  onlyKeys(a, ['path'], 'read_page');
  const raw = requiredString(a, 'path', 'read_page', { max: 300 });
  const path = normalizePagePath(raw, cfg.origin);
  if (path === null) throw new InvalidParams(`read_page: "${raw}" is not a page path on ${cfg.origin}`);
  const pages = await data.pages();
  if (pages === null) return failed('The page index (/api/v1/pages.json) could not be read, so the page cannot be looked up. Try again later.');
  const page = pages.find((p) => p.path === path);
  if (!page) return failed(`There is no page at ${path}. Use a path from search_standard results, such as "/capabilities/mutate/".`);
  const markdown = await data.text(page.markdownPath);
  if (markdown === null) return failed(`The Markdown copy of ${path} (${page.markdownPath}) could not be read.`);
  return ok({ path, title: page.title, url: `${cfg.origin}${path}`, markdownUrl: `${cfg.origin}${page.markdownPath}`, markdown });
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
