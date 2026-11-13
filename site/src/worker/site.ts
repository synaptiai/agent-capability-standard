// The request-time layer of the site: what a static file cannot do alone.
// - Content negotiation: a page asked for with an Accept header that prefers
//   text/markdown over text/html gets the page's Markdown copy.
// - <page>.md (e.g. /capabilities/mutate.md) answers with <page>/index.md.
// - AI crawlers and agent fetchers named in MARKDOWN_AGENTS get the Markdown
//   copy of a page whatever they ask for.
// - Link headers on HTML pages point at the Markdown copy, the sitemap, the
//   OpenAPI description and the API catalog.
// - Not found: browsers keep the HTML 404 page; any other client gets a short
//   Markdown 404, and /api/v1/* gets an RFC 9457 problem+json 404.
// - /mcp is the docs MCP server (mcp.ts); its server card is at
//   /mcp/server-card and /.well-known/mcp/server-card.json.
// - A path with repeated slashes redirects to the same path with single ones.
// Every other request goes to the static files unchanged.

import { namesHtml, prefersMarkdown } from './accept';
import type { Env, WorkerConfig } from './env';
import { MCP_PATH, SERVER_CARD_TYPE, serverCard } from './identity';
import { CORS_HEADERS, handleMcp, mcpInternalError } from './mcp';

/**
 * User agents that get the Markdown copy of a page even when they ask for
 * HTML: the model-training crawlers (GPTBot, ClaudeBot), the fetchers that
 * act for one person's request (ChatGPT-User, Claude-User, Perplexity-User),
 * and PerplexityBot. The copy has the same text and links as the page, and a
 * Link rel="canonical" header names the HTML page as the address to cite.
 *
 * PerplexityBot is Perplexity's search-index crawler, so by the reason below
 * it would get HTML; it is in this list because the agent-readiness check
 * this work answers names it with GPTBot and ClaudeBot. Removing it is a
 * one-word change.
 *
 * The search-index crawlers OAI-SearchBot and Claude-SearchBot keep getting
 * HTML, as do Googlebot and Bingbot: a search result is built from the
 * page's title, description and structured data, which only the HTML has.
 */
export const MARKDOWN_AGENTS = ['GPTBot', 'ClaudeBot', 'PerplexityBot', 'ChatGPT-User', 'Claude-User', 'Perplexity-User'] as const;

const AGENT_RE = new RegExp(`(?:^|[^A-Za-z0-9-])(?:${MARKDOWN_AGENTS.join('|')})(?:$|[^A-Za-z0-9-])`, 'i');

export function isMarkdownAgent(userAgent: string | null): boolean {
  return userAgent !== null && AGENT_RE.test(userAgent);
}

export const PROBLEM_TYPE_NOT_FOUND = 'https://acs.synapti.ai/developers/#ref-errors';

/** A path that names a page rather than a file: it ends in "/", or its last segment has no extension. */
export function isPagePath(path: string): boolean {
  if (path.endsWith('/')) return true;
  const last = path.slice(path.lastIndexOf('/') + 1);
  return !last.includes('.');
}

/** "/a/b/" or "/a/b" -> "/a/b/". */
function withSlash(path: string): string {
  return path.endsWith('/') ? path : `${path}/`;
}

function robotsHeaders(url: URL): Record<string, string> {
  // The pages.dev copies stay out of search engines (public/_headers does the same for static files).
  return url.hostname.endsWith('.pages.dev') ? { 'X-Robots-Tag': 'noindex' } : {};
}

/** Link header value for an HTML page. */
export function pageLinks(pagePath: string): string {
  return [
    `<${pagePath}index.md>; rel="alternate"; type="text/markdown"`,
    '</sitemap.xml>; rel="sitemap"; type="application/xml"',
    '</openapi.json>; rel="service-desc"; type="application/vnd.oai.openapi+json"',
    '</.well-known/api-catalog>; rel="api-catalog"; type="application/linkset+json"',
  ].join(', ');
}

/**
 * The Markdown copy as the answer to `request`: the static file's own headers
 * (ETag, Last-Modified, Cache-Control, CORS) with the Markdown type, a
 * canonical link to the page and, for a negotiated URL, Vary. A 304 from the
 * static file stays a 304.
 */
function markdownResponse(request: Request, url: URL, copy: Response, pagePath: string, cfg: WorkerConfig, vary: string | null): Response {
  const headers = new Headers(copy.headers);
  headers.set('Content-Type', 'text/markdown; charset=utf-8');
  headers.set('X-Content-Type-Options', 'nosniff');
  headers.set('Link', `<${cfg.origin}${pagePath}>; rel="canonical"`);
  if (vary) headers.append('Vary', vary);
  for (const [k, v] of Object.entries(robotsHeaders(url))) headers.set(k, v);
  const body = request.method === 'HEAD' || copy.status === 304 ? null : copy.body;
  return new Response(body, { status: copy.status, headers });
}

export function notFoundMarkdown(path: string, cfg: WorkerConfig): string {
  return [
    '# Page not found',
    '',
    `There is no page at \`${path}\` on ${cfg.origin}.`,
    '',
    `- [llms.txt](${cfg.origin}/llms.txt): every page, with a summary and a link to its Markdown copy`,
    `- [sitemap.xml](${cfg.origin}/sitemap.xml): every page address`,
    `- [Developers](${cfg.origin}/developers/): the data API, the MCP server and the Markdown copies`,
    '',
  ].join('\n');
}

export function problemNotFound(path: string, cfg: WorkerConfig) {
  return {
    type: PROBLEM_TYPE_NOT_FOUND,
    title: 'Not Found',
    status: 404,
    detail: `There is no resource at ${path}. /api/v1/index.json lists the resources, and ${cfg.origin}/openapi.json describes them.`,
    instance: path,
  };
}

function serverCardResponse(request: Request, url: URL, cfg: WorkerConfig): Response {
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS_HEADERS });
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return new Response('Method Not Allowed\n', { status: 405, headers: { Allow: 'GET, HEAD, OPTIONS', 'Content-Type': 'text/plain; charset=utf-8' } });
  }
  const type = url.pathname.endsWith('.json') ? 'application/json' : SERVER_CARD_TYPE;
  return new Response(request.method === 'HEAD' ? null : `${JSON.stringify(serverCard(cfg), null, 2)}\n`, {
    status: 200,
    headers: { 'Content-Type': type, 'Cache-Control': 'public, max-age=3600', ...CORS_HEADERS, ...robotsHeaders(url) },
  });
}

/** The static file at `path`, read with GET, with the request's conditional headers so a fresh cached copy gets a 304. */
function asset(env: Env, request: Request, url: URL, path: string): Promise<Response> {
  const headers = new Headers();
  for (const h of ['If-None-Match', 'If-Modified-Since']) {
    const v = request.headers.get(h);
    if (v !== null) headers.set(h, v);
  }
  // Set the path on a copy of the request URL rather than resolving it, so
  // the host is always the request's own.
  const target = new URL(url);
  target.pathname = path;
  target.search = '';
  return env.ASSETS.fetch(new Request(target, { method: 'GET', headers }));
}

/** Whether a static-file answer is the copy itself (200) or a "not modified" for it (304). */
function found(res: Response): boolean {
  return res.status === 200 || res.status === 304;
}

async function notFound(request: Request, url: URL, original: Response, cfg: WorkerConfig, markdown: boolean): Promise<Response> {
  const path = url.pathname;
  const head = request.method === 'HEAD';
  if (path.startsWith('/api/')) {
    return new Response(head ? null : JSON.stringify(problemNotFound(path, cfg)), {
      status: 404,
      headers: { 'Content-Type': 'application/problem+json', 'Cache-Control': 'no-store', ...CORS_HEADERS, ...robotsHeaders(url) },
    });
  }
  if (markdown) {
    return new Response(head ? null : notFoundMarkdown(path, cfg), {
      status: 404,
      headers: { 'Content-Type': 'text/markdown; charset=utf-8', 'Cache-Control': 'no-store', Vary: 'Accept, User-Agent', ...robotsHeaders(url) },
    });
  }
  const res = new Response(original.body, original);
  res.headers.append('Vary', 'Accept, User-Agent');
  return res;
}

export function createHandler(cfg: WorkerConfig) {
  return async function handle(request: Request, env: Env): Promise<Response> {
    try {
      return await route(request, env, cfg);
    } catch {
      // Fail open: if anything here breaks, the static files are still served as they are.
      return env.ASSETS.fetch(request);
    }
  };
}

async function route(request: Request, env: Env, cfg: WorkerConfig): Promise<Response> {
  const url = new URL(request.url);
  const path = url.pathname;
  // A path with "//" would read as a host name where it is resolved as a
  // URL ("//evil.example/a" -> https://evil.example/a) and would end up in a
  // canonical link. Send the client to the same path with single slashes.
  if (path.includes('//')) {
    const status = request.method === 'GET' || request.method === 'HEAD' ? 301 : 308;
    return new Response(null, { status, headers: { Location: `${path.replace(/\/{2,}/g, '/')}${url.search}`, ...robotsHeaders(url) } });
  }
  if (path === MCP_PATH) {
    // The MCP endpoint is not a file: if handling it fails, the client gets a
    // JSON-RPC error, never the static 404 that failing open would give.
    try {
      return await handleMcp(request, env, cfg);
    } catch {
      return mcpInternalError();
    }
  }
  if (path === `${MCP_PATH}/server-card` || path === '/.well-known/mcp/server-card.json') return serverCardResponse(request, url, cfg);
  if (request.method !== 'GET' && request.method !== 'HEAD') return env.ASSETS.fetch(request);

  const accept = request.headers.get('Accept');
  const agent = isMarkdownAgent(request.headers.get('User-Agent'));
  const wantsMarkdown = agent || prefersMarkdown(accept);
  // A browser names text/html in Accept; curl, HTTP libraries and most agents send */* or nothing.
  const markdown404 = wantsMarkdown || !namesHtml(accept);

  // A Markdown copy, asked for directly.
  if (path.endsWith('/index.md')) {
    const res = await asset(env, request, url, path);
    if (found(res)) return markdownResponse(request, url, res, path.slice(0, -'index.md'.length), cfg, null);
    return notFound(request, url, res, cfg, markdown404);
  }
  // <page>.md -> <page>/index.md, when no file has that name.
  if (path.endsWith('.md') && path.length > '/.md'.length) {
    const direct = await env.ASSETS.fetch(request);
    if (direct.status !== 404) return direct;
    const pagePath = `${path.slice(0, -'.md'.length)}/`;
    const res = await asset(env, request, url, `${pagePath}index.md`);
    if (found(res)) return markdownResponse(request, url, res, pagePath, cfg, null);
    return notFound(request, url, direct, cfg, true);
  }

  const page = isPagePath(path);
  if (page && wantsMarkdown) {
    const pagePath = withSlash(path);
    const res = await asset(env, request, url, `${pagePath}index.md`);
    if (found(res)) return markdownResponse(request, url, res, pagePath, cfg, 'Accept, User-Agent');
  }

  const res = await env.ASSETS.fetch(request);
  if (res.status === 404) return notFound(request, url, res, cfg, markdown404);
  if (!page || res.status !== 200 || !(res.headers.get('Content-Type') ?? '').startsWith('text/html')) return res;
  const out = new Response(res.body, res);
  out.headers.append('Vary', 'Accept, User-Agent');
  if (path.endsWith('/')) out.headers.append('Link', pageLinks(path));
  return out;
}
