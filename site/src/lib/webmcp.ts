// Read-only WebMCP tools: an agent running in the visitor's browser can search
// the site and read its pages and data through these, instead of scraping the
// rendered HTML. Runs in the browser; the registering script is
// src/components/WebMcp.astro.
//
// The API, as read on 2026-11-13:
// - W3C Web Machine Learning CG, "WebMCP" draft of 12 November 2026,
//   https://webmachinelearning.github.io/webmcp/ : `partial interface Document
//   { readonly attribute ModelContext modelContext; }`, `registerTool(tool,
//   options)` with a tool of { name (1 to 128 of [A-Za-z0-9_.-]), title,
//   description, inputSchema, execute(input, options) => Promise<any>,
//   annotations: { readOnlyHint, untrustedContentHint, consequentialHint } }.
//   executeTool() hands the agent a string, so every tool here returns text.
// - Chrome, "WebMCP imperative API",
//   https://developer.chrome.com/docs/ai/webmcp/imperative-api : the same
//   shape on document.modelContext, string results in its examples.
// Earlier drafts put the API on navigator.modelContext; the registering
// script uses that only when document.modelContext is missing.
//
// Every tool only reads files the site already publishes, so all of them
// carry readOnlyHint and none carries consequentialHint. None carries
// untrustedContentHint: the text they return is the site's own content, built
// from the repository, not text written by visitors.
import { PAGE_CHUNK, pagePart, sectionNames } from '../worker/page-text';
import { CAPABILITY_ID, WORKFLOW_ID } from './agent-contract';
import { isRealMatch, wordsAt } from './search-match';

export interface ToolAnnotations {
  readOnlyHint?: boolean;
  untrustedContentHint?: boolean;
  consequentialHint?: boolean;
}

export interface ModelContextTool {
  name: string;
  title?: string;
  description: string;
  inputSchema: JsonSchemaObject;
  execute: (input: Record<string, unknown>, options?: { signal?: AbortSignal }) => Promise<string>;
  annotations?: ToolAnnotations;
}

export interface ModelContext {
  registerTool(tool: ModelContextTool, options?: { signal?: AbortSignal }): unknown;
}

declare global {
  interface Document {
    modelContext?: ModelContext;
  }
  interface Navigator {
    modelContext?: ModelContext;
  }
}

interface JsonSchemaObject {
  type: 'object';
  properties: Record<string, Record<string, unknown>>;
  required: string[];
  additionalProperties: false;
}

/** The parts of a Pagefind result the search tool reads. */
export interface PagefindResultData {
  url: string;
  excerpt: string;
  content: string;
  locations: number[];
  meta: Record<string, string | undefined>;
  filters: Record<string, string[] | undefined>;
}

/** The part of Pagefind's JavaScript API the search tool uses. */
export interface PagefindApi {
  search(query: string): Promise<{ results: { data(): Promise<PagefindResultData> }[] } | null>;
}

/** What the tools need from the page; the tests pass fakes. */
export interface ToolDeps {
  /** The site's origin, such as https://acs.synapti.ai; URLs in results are made absolute with it. */
  origin: string;
  /** fetch(), or a fake. */
  fetch: (url: string, init?: { signal?: AbortSignal }) => Promise<{ ok: boolean; status: number; text(): Promise<string> }>;
  /** Pagefind, loaded on first use; null when it could not load. */
  loadPagefind: () => Promise<PagefindApi | null>;
}

export const SEARCH_LIMIT_DEFAULT = 8;
export const SEARCH_LIMIT_MAX = 25;

export { CAPABILITY_ID, WORKFLOW_ID };

/** The paths of the data API (the site's static JSON under /api/v1/). */
export const capabilityPath = (id: string) => `/api/v1/capabilities/${id}.json`;
export const workflowPath = (id: string) => `/api/v1/workflows/${id}.json`;

function stringArg(input: Record<string, unknown> | undefined, key: string): string {
  const v = input?.[key];
  if (typeof v !== 'string' || v.trim() === '') throw new Error(`"${key}" must be a non-empty string.`);
  return v.trim();
}

/** Pagefind's excerpt is escaped HTML with <mark> around the matches; this gives plain text. */
export function excerptText(excerpt: string): string {
  return excerpt
    .replace(/<[^>]*>/g, '')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#0?39;/g, "'")
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * The site path of the Markdown copy of the page at `path` (a site path or a
 * URL on this site): `/capabilities/detect/` and `/capabilities/detect` give
 * `/capabilities/detect/index.md`. Throws for another origin.
 */
export function markdownPath(path: string, origin: string): string {
  let url: URL;
  try {
    url = new URL(path, origin);
  } catch {
    throw new Error(`"${path}" is not a path on this site.`);
  }
  if (url.origin !== new URL(origin).origin) throw new Error(`"${path}" is not on this site (${origin}).`);
  let p = url.pathname;
  if (p.endsWith('/index.md')) return p;
  if (p.endsWith('/index.html')) p = p.slice(0, -'index.html'.length);
  else if (p.endsWith('.md')) p = `${p.slice(0, -'.md'.length)}/`;
  if (!p.endsWith('/')) p += '/';
  return `${p}index.md`;
}

async function fetchText(deps: ToolDeps, path: string, missing: string, signal?: AbortSignal): Promise<string> {
  const url = new URL(path, deps.origin).href;
  const res = await deps.fetch(url, { signal });
  if (!res.ok) throw new Error(res.status === 404 ? missing : `Fetching ${url} failed with HTTP ${res.status}.`);
  return res.text();
}

/** The four read-only tools, in the order they are registered. */
export function webMcpTools(deps: ToolDeps): ModelContextTool[] {
  const readOnly: ToolAnnotations = { readOnlyHint: true };
  const abs = (p: string) => new URL(p, deps.origin).href;

  // The names, arguments and id patterns are those of the MCP server's tools
  // (src/worker/tools.ts). One difference: this search_standard runs the
  // site's full-text index (Pagefind), which the page has loaded; the MCP
  // server's runs over /api/v1/pages.json.
  const searchStandard: ModelContextTool = {
    name: 'search_standard',
    title: 'Search the Standard',
    description:
      'Full-text search over every page of the Agent Capability Standard site (the Standard, capabilities, layers, workflows, domain profiles, guides). Returns each matching page with its title, section, URL, the URL of its Markdown copy and a short excerpt. Use read_page on a result to read the page.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', minLength: 1, description: 'Words to search for, such as "checkpoint before mutate".' },
        limit: {
          type: 'integer',
          minimum: 1,
          maximum: SEARCH_LIMIT_MAX,
          default: SEARCH_LIMIT_DEFAULT,
          description: `The most results to return (1 to ${SEARCH_LIMIT_MAX}, default ${SEARCH_LIMIT_DEFAULT}).`,
        },
      },
      required: ['query'],
      additionalProperties: false,
    },
    annotations: readOnly,
    async execute(input) {
      const query = stringArg(input, 'query');
      const raw = input?.limit;
      const limit =
        raw === undefined ? SEARCH_LIMIT_DEFAULT : Number.isInteger(raw) ? Math.min(Math.max(raw as number, 1), SEARCH_LIMIT_MAX) : NaN;
      if (Number.isNaN(limit)) throw new Error(`"limit" must be an integer from 1 to ${SEARCH_LIMIT_MAX}.`);
      const pf = await deps.loadPagefind();
      if (!pf) throw new Error('The search index could not load. Try again, or read /llms.txt for a list of pages.');
      const found = await pf.search(query);
      const all = found?.results ?? [];
      // Keep only results that really match every query word, as the search
      // dialog does (lib/search-match.ts): Pagefind also returns pages matched
      // on a one-letter prefix of a made-up word.
      const items: PagefindResultData[] = [];
      for (let i = 0; i < all.length && items.length < limit; i += limit) {
        const batch = await Promise.all(all.slice(i, i + limit).map((r) => r.data()));
        for (const r of batch) {
          const matched = [...wordsAt(r.content, r.locations), ...(r.meta.title ?? '').split(/\s+/)];
          if (items.length < limit && isRealMatch(query, matched)) items.push(r);
        }
      }
      if (items.length === 0) return `No pages match "${query}".`;
      const lines = [`Pages matching "${query}" (best first):`];
      items.forEach((r, i) => {
        const section = [r.filters.section?.[0], r.filters.version?.[0] && `Standard v${r.filters.version[0]}`].filter(Boolean).join(', ');
        lines.push(
          '',
          `${i + 1}. ${r.meta.title ?? r.url}${section ? ` (${section})` : ''}`,
          `   URL: ${abs(r.url)}`,
          `   Markdown: ${abs(markdownPath(r.url, deps.origin))}`,
          `   Excerpt: ${excerptText(r.excerpt)}`,
        );
      });
      return lines.join('\n');
    },
  };

  const readCapability: ModelContextTool = {
    name: 'read_capability',
    title: 'Read a capability',
    description:
      'Returns a capability of the Standard as JSON, from the site\'s data API: its layer, description, input and output schemas and safety flags (risk, mutation, checkpoint and approval). The list of ids is at /api/v1/capabilities.json.',
    inputSchema: {
      type: 'object',
      properties: {
        id: { type: 'string', pattern: CAPABILITY_ID, description: 'The capability id, such as "retrieve", "checkpoint" or "mutate".' },
      },
      required: ['id'],
      additionalProperties: false,
    },
    annotations: readOnly,
    async execute(input, options) {
      const id = stringArg(input, 'id');
      if (!new RegExp(CAPABILITY_ID).test(id)) throw new Error(`"${id}" is not a capability id (lower case words joined by hyphens).`);
      return fetchText(deps, capabilityPath(id), `No capability "${id}". The ids are listed at ${abs('/api/v1/capabilities.json')}.`, options?.signal);
    },
  };

  const readWorkflow: ModelContextTool = {
    name: 'read_workflow',
    title: 'Read a workflow',
    description:
      'Returns a workflow from the Standard\'s workflow catalogs as JSON, from the site\'s data API: its goal, its steps and the capability each step uses. The list of ids is at /api/v1/workflows.json.',
    inputSchema: {
      type: 'object',
      properties: {
        id: { type: 'string', pattern: WORKFLOW_ID, description: 'The workflow id, its catalog key, such as "debug_code_change".' },
      },
      required: ['id'],
      additionalProperties: false,
    },
    annotations: readOnly,
    async execute(input, options) {
      const id = stringArg(input, 'id');
      if (!new RegExp(WORKFLOW_ID).test(id)) throw new Error(`"${id}" is not a workflow id (lower case words joined by underscores).`);
      return fetchText(deps, workflowPath(id), `No workflow "${id}". The ids are listed at ${abs('/api/v1/workflows.json')}.`, options?.signal);
    },
  };

  const readPage: ModelContextTool = {
    name: 'read_page',
    title: 'Read a page as Markdown',
    description: `Returns the Markdown copy of a page of this site, the same text as the rendered page without navigation. Give the page's path, such as "/capabilities/detect/" or "/spec/", or a URL from search_standard. A long page comes in parts of at most ${PAGE_CHUNK.toLocaleString('en')} characters: the end of each part says the offset of the next. Pass section to read one section by its heading.`,
    inputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string', minLength: 1, description: 'The page path on this site, such as "/workflows/", or its full URL.' },
        section: { type: 'string', minLength: 1, maxLength: 200, description: 'A heading of the page, such as "Safety" (case ignored): return only that section.' },
        offset: { type: 'integer', minimum: 0, default: 0, description: 'Where to start, in characters: the offset the previous part ends with.' },
      },
      required: ['path'],
      additionalProperties: false,
    },
    annotations: readOnly,
    async execute(input, options) {
      const path = stringArg(input, 'path');
      const section = input?.section === undefined ? undefined : stringArg(input, 'section');
      const rawOffset = input?.offset;
      if (rawOffset !== undefined && (!Number.isInteger(rawOffset) || (rawOffset as number) < 0)) throw new Error('"offset" must be an integer of 0 or more.');
      const md = markdownPath(path, deps.origin);
      const text = await fetchText(deps, md, `No page at "${path}". Use search_standard to find one, or read ${abs('/llms.txt')}.`, options?.signal);
      const part = pagePart(text, { section, offset: rawOffset as number | undefined });
      if (!part.ok) throw new Error(part.headings.length > 0 ? `${part.message} Its headings: ${part.headings.join(', ')}.` : part.message);
      if (part.offset === 0 && part.nextOffset === null) return part.markdown;
      const note = [`[Characters ${part.offset} to ${part.offset + part.markdown.length} of ${part.totalLength}.`];
      if (part.nextOffset !== null) note.push(`Call read_page with offset ${part.nextOffset}${section ? ` and the same section` : ''} for the next part.`);
      if (!section) note.push(`Sections: ${sectionNames(text).join('; ')}.`);
      return `${part.markdown}\n\n${note.join(' ')}]`;
    },
  };

  return [searchStandard, readCapability, readWorkflow, readPage];
}
