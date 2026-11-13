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
// Every other request goes to the static files unchanged.

import { namesHtml, prefersMarkdown } from './accept';
import type { Env, WorkerConfig } from './env';
import { MCP_PATH, SERVER_CARD_TYPE, serverCard } from './identity';
import { CORS_HEADERS, handleMcp } from './mcp';

/**
 * User agents that get the Markdown copy of a page even when they ask for
 * HTML: the model-training crawlers (GPTBot, ClaudeBot), Perplexity's
 * answer-engine crawler (PerplexityBot), and the fetchers that act for one
 * person's request (ChatGPT-User, Claude-User, Perplexity-User). The copy has
 * the same text and links as the page, and a Link rel="canonical" header
 * names the HTML page as the address to cite.
 *
 * The search-index crawlers OAI-SearchBot and Claude-SearchBot keep getting
 * HTML, as do Googlebot and Bingbot: a search result is built from the
 * page's title, description and structured data, which only the HTML has.
 * All of them read the same pages either way (robots.txt allows them all).
 */
export const MARKDOWN_AGENTS = ['GPTBot', 'ClaudeBot', 'PerplexityBot', 'ChatGPT-User', 'Claude-User', 'Perplexity-User'] as const;

const AGENT_RE = new RegExp(`(?:^|[^A-Za-z0-9-])(?:${MARKDOWN_AGENTS.join('|')})(?:$|[^A-Za-z0-9-])`, 'i');

export function isMarkdownAgent(userAgent: string | null): boolean {
  return userAgent !== null && AGENT_RE.test(userAgent);
}

export const PROBLEM_TYPE_NOT_FOUND = 'https://acs.synapti.ai/developers/#errors';

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

function markdownResponse(request: Request, url: URL, body: string, pagePath: string, cfg: WorkerConfig, vary: string | null): Response {
  const headers: Record<string, string> = {
    'Content-Type': 'text/markdown; charset=utf-8',
    'Cache-Control': 'public, max-age=0, must-revalidate',
    'X-Content-Type-Options': 'nosniff',
    Link: `<${cfg.origin}${pagePath}>; rel="canonical"`,
    ...robotsHeaders(url),
  };
  if (vary) headers.Vary = vary;
  return new Response(request.method === 'HEAD' ? null : body, { status: 200, headers });
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

/** The static file at `path`, read with GET whatever the request's method. */
function asset(env: Env, url: URL, path: string): Promise<Response> {
  return env.ASSETS.fetch(new Request(new URL(path, url), { method: 'GET' }));
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
    const url = new URL(request.url);
    const path = url.pathname;
    if (path === MCP_PATH) return handleMcp(request, env, cfg);
    if (path === `${MCP_PATH}/server-card` || path === '/.well-known/mcp/server-card.json') return serverCardResponse(request, url, cfg);
    if (request.method !== 'GET' && request.method !== 'HEAD') return env.ASSETS.fetch(request);

    const accept = request.headers.get('Accept');
    const agent = isMarkdownAgent(request.headers.get('User-Agent'));
    const wantsMarkdown = agent || prefersMarkdown(accept);
    // A browser names text/html in Accept; curl, HTTP libraries and most agents send */* or nothing.
    const markdown404 = wantsMarkdown || !namesHtml(accept);

    // A Markdown copy, asked for directly.
    if (path.endsWith('/index.md')) {
      const res = await asset(env, url, path);
      if (res.status === 200) return markdownResponse(request, url, await res.text(), path.slice(0, -'index.md'.length), cfg, null);
      return notFound(request, url, res, cfg, markdown404);
    }
    // <page>.md -> <page>/index.md, when no file has that name.
    if (path.endsWith('.md') && path.length > '/.md'.length) {
      const direct = await env.ASSETS.fetch(request);
      if (direct.status !== 404) return direct;
      const pagePath = `${path.slice(0, -'.md'.length)}/`;
      const res = await asset(env, url, `${pagePath}index.md`);
      if (res.status === 200) return markdownResponse(request, url, await res.text(), pagePath, cfg, null);
      return notFound(request, url, direct, cfg, true);
    }

    const page = isPagePath(path);
    if (page && wantsMarkdown) {
      const pagePath = withSlash(path);
      const res = await asset(env, url, `${pagePath}index.md`);
      if (res.status === 200) return markdownResponse(request, url, await res.text(), pagePath, cfg, 'Accept, User-Agent');
    }

    const res = await env.ASSETS.fetch(request);
    if (res.status === 404) return notFound(request, url, res, cfg, markdown404);
    if (!page || res.status !== 200 || !(res.headers.get('Content-Type') ?? '').startsWith('text/html')) return res;
    const out = new Response(res.body, res);
    out.headers.append('Vary', 'Accept, User-Agent');
    if (path.endsWith('/')) out.headers.append('Link', pageLinks(path));
    return out;
  };
}
