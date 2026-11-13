// The content of /developers/, shared by the page and its Markdown copy: the
// ways an agent or a program can read the site, the endpoints of the JSON
// API (from the endpoint list the OpenAPI document is built from), curl
// examples, and the MCP and WebMCP tools.
import { loadCounts } from '../data/counts';
import {
  API_BASE,
  API_CATALOG_PATH,
  API_CATALOG_PROFILE,
  concretePath,
  DEVELOPERS_URL,
  ENDPOINTS,
  MCP_TOOLS,
  MCP_URL,
  OPENAPI_PATH,
  type Endpoint,
} from './api';
import { SITE_ORIGIN } from './origin';
import { ROUTES } from './routes';

export const DEVELOPERS_TITLE = 'Agent Capability Standard API and agent access';
export const DEVELOPERS_NAV_TITLE = 'API and agent access';

export function developersDescription(): string {
  return 'The open, read-only JSON API of the Agent Capability Standard, with its OpenAPI description, and the other ways agents can read the site: Markdown copies, llms.txt, an MCP server and WebMCP tools.';
}

export const LEAD =
  'Everything on this site can be read by a program. None of it needs an account, an API key or a cookie: every route below is open and read-only, and is rebuilt from the repository each time the site is published.';

// ------------------------------------------------------------------ figure 1

export interface AccessRoute {
  name: string;
  /** What comes back. */
  format: string;
  /** Where it is, as shown. */
  where: string;
  /** A link to it, when it is a file or page on the site. */
  href: string | null;
  line: string;
  glyph: string;
}

export function accessRoutes(): AccessRoute[] {
  const c = loadCounts();
  return [
    {
      name: 'Web pages',
      format: 'HTML',
      where: '/',
      href: '/',
      line: `${ROUTES.length} pages for people, each with a canonical URL and a link to its Markdown copy.`,
      glyph: 'section:spec',
    },
    {
      name: 'Markdown copies',
      format: 'Markdown',
      where: '<page>/index.md',
      href: '/index.md',
      line: 'The same content as each page, as Markdown, with links to the other copies.',
      glyph: 'source:document',
    },
    {
      name: 'llms.txt',
      format: 'Text',
      where: '/llms.txt',
      href: '/llms.txt',
      line: 'A list of every Markdown copy by section; llms-full.txt joins the Standard, capability and workflow pages in one file.',
      glyph: 'chapter:references',
    },
    {
      name: 'JSON API',
      format: 'JSON',
      where: `${API_BASE}/`,
      href: `${API_BASE}/index.json`,
      line: `${c.capabilityCount} capabilities, ${c.workflowCount} workflows, ${c.profileCount} domain profiles, ${c.diagnosticCount} diagnostic codes and a page index, described by OpenAPI.`,
      glyph: 'page:api',
    },
    {
      name: 'MCP server',
      format: 'MCP',
      where: '/mcp',
      href: null,
      line: `Tools to search the site and read a capability, a workflow or a page, over Streamable HTTP.`,
      glyph: 'flow:invoke',
    },
    {
      name: 'WebMCP tools',
      format: 'WebMCP',
      where: 'document.modelContext',
      href: null,
      line: 'The same kind of read-only tools, registered by each page for an agent that runs in the browser.',
      glyph: 'code',
    },
  ];
}

export const ACCESS_FIG_TITLE = 'Ways to read the site';
export function accessCaption(routes: AccessRoute[] = accessRoutes()): string {
  return `There are ${routes.length} ways in, from HTML for people to JSON and MCP tools for programs, and none of them needs a key.`;
}

// ------------------------------------------------------------------ figure 2

export interface EndpointRow {
  path: string;
  /** A file to open: the path itself, or an example for a path with a parameter. */
  href: string;
  operationId: string;
  summary: string;
  /** The values its parameter takes, for a path with one. */
  values: number | null;
}

export function endpointRows(): EndpointRow[] {
  return ENDPOINTS.map((e: Endpoint) => ({
    path: e.path,
    href: concretePath(e, e.example?.()),
    operationId: e.operationId,
    summary: e.summary,
    values: e.param ? e.param.values().length : null,
  }));
}

export const ENDPOINTS_FIG_TITLE = 'Endpoints of the JSON API';
export function endpointsCaption(rows: EndpointRow[] = endpointRows()): string {
  const files = rows.reduce((n, r) => n + (r.values ?? 1), 0);
  const params = rows.filter((r) => r.values !== null).length;
  return `${rows.length} GET operations, ${params} of them with a path parameter, serve ${files} JSON files in all.`;
}

/** What the Values column says. */
export function valuesText(r: EndpointRow): string {
  return r.values === null ? 'one file' : `one file per id (${r.values})`;
}

// ------------------------------------------------------------------ examples

export interface Example {
  what: string;
  command: string;
}

export function curlExamples(): Example[] {
  const at = (p: string) => `${SITE_ORIGIN}${p}`;
  const cap = ENDPOINTS.find((e) => e.operationId === 'readCapability')!;
  const capId = cap.example!();
  return [
    { what: 'The entry point: every collection, its size and the versions.', command: `curl -s ${at(`${API_BASE}/index.json`)}` },
    { what: `The capability ${capId}, with its schemas and safety flags.`, command: `curl -s ${at(concretePath(cap, capId))}` },
    { what: 'The id of every workflow.', command: `curl -s ${at(`${API_BASE}/workflows.json`)} | jq -r '.workflows[].id'` },
    { what: 'The capabilities that need a checkpoint before they run.', command: `curl -s ${at(`${API_BASE}/capabilities.json`)} | jq -r '.capabilities[] | select(.requires_checkpoint) | .id'` },
    { what: 'The OpenAPI description.', command: `curl -s ${at(OPENAPI_PATH)}` },
    { what: 'The API catalog (RFC 9727).', command: `curl -s ${at(API_CATALOG_PATH)}` },
  ];
}

export function markdownExamples(): Example[] {
  const at = (p: string) => `${SITE_ORIGIN}${p}`;
  return [
    { what: 'The Markdown copy of a page: its URL followed by index.md.', command: `curl -s ${at('/start/quickstart/index.md')}` },
    { what: 'The same copy, asked for by its media type.', command: `curl -s -H 'Accept: text/markdown' ${at('/start/quickstart/')}` },
    { what: 'The index of the copies, by section.', command: `curl -s ${at('/llms.txt')}` },
  ];
}

// ------------------------------------------------------------------ prose

export const API_FACTS: readonly string[] = [
  'Open: no authentication and no API key. Send a plain GET with no credentials.',
  'Read-only: the files are built from the repository at the commit each file names in generated_from.commit, and change only when the site is rebuilt.',
  'Not paginated: each list returns the whole collection in one response, with its size in count.',
  'Every file starts with api_version, a version block (Standard, ontology and plugin versions) and generated_from. Field names are snake_case, as in the YAML sources. A field the source does not set is null, not missing.',
];

export const VERSIONING: readonly string[] = [
  `The major version is in the path: ${API_BASE}. Adding a field or a file is not a breaking change.`,
  'Removing or renaming a field or a file gets a new major path, /api/v2. The old path then stays for at least one minor version of the Standard.',
  'Before an old path is removed, its responses carry Deprecation and Sunset headers that give the date.',
];

export const ERRORS =
  `A path under ${API_BASE}/ that names no file, such as an id that is not in the enum, returns status 404 with an RFC 9457 problem details body (application/problem+json): type, title, status, detail and instance. The OpenAPI document defines it as the Problem schema.`;

export function catalogLine(): string {
  return `The API catalog at ${API_CATALOG_PATH} lists the API for discovery (RFC 9727). It is served as application/linkset+json with the profile ${API_CATALOG_PROFILE}, and links to the OpenAPI document and to this page.`;
}

export const MARKDOWN_LINES: readonly string[] = [
  'Every page has a Markdown copy at its URL followed by index.md; the home page\'s is /index.md. Each HTML page links to it with <link rel="alternate" type="text/markdown">.',
  'The same copy is served at the page\'s URL with .md in place of the final slash (/capabilities/mutate.md), and at the page\'s own URL to a request whose Accept header prefers text/markdown. A page that does not exist answers 404 in Markdown to a client that is not a browser.',
  'Each copy opens with front matter (title, description, canonical and last_updated), then the page with a top-level heading. Links in a copy point at the other pages\' copies, so an agent can follow them without reading HTML. Figures are given as tables or lists with the same data.',
  `llms.txt lists the main pages of each section and links one llms.txt per section, which lists every copy. llms-full.txt holds the current Standard, every capability page and every workflow page in one file. The sitemap is at /sitemap.xml.`,
];

export const MCP_LEAD =
  `The site's worker serves a read-only MCP server at ${MCP_URL}. It speaks Streamable HTTP, keeps no session and needs no authentication. Its tools read the same data as the JSON API and the Markdown copies:`;

export const MCP_FIG_TITLE = 'Tools of the MCP server';
export function mcpCaption(): string {
  return `The server has ${MCP_TOOLS.length} tools, all read-only: one searches, the others each read a capability, a workflow or a page.`;
}

export const MCP_CLAUDE_CODE = `claude mcp add --transport http agent-capability-standard ${MCP_URL}`;
export function mcpConfig(): string {
  return JSON.stringify({ mcpServers: { 'agent-capability-standard': { type: 'http', url: MCP_URL } } }, null, 2);
}

/** The WebMCP tools each page registers, by name, as src/lib/webmcp.ts defines them. */
export const WEBMCP_TOOLS: readonly string[] = ['search_docs', 'read_capability', 'read_workflow', 'read_page_markdown'];

export const WEBMCP_LINES: readonly string[] = [
  'Each page registers read-only tools with the browser\'s WebMCP interface (document.modelContext, or navigator.modelContext in earlier drafts) when the browser has it. An agent that runs in the browser can call them without leaving the page.',
  `The tools are ${WEBMCP_TOOLS.slice(0, -1).join(', ')} and ${WEBMCP_TOOLS[WEBMCP_TOOLS.length - 1]}. They search the site and read a capability, a workflow or a page's Markdown copy, through the same JSON files and copies described here. They change nothing and send nothing anywhere but this site.`,
];

export { DEVELOPERS_URL, MCP_TOOLS, MCP_URL };
