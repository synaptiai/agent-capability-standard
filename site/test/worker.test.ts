// The request-time layer (src/worker/): content negotiation, the .md form of
// page URLs, the AI-agent user agents, 404s, Link headers, the docs MCP
// server and its server card. The handler runs against a fake ASSETS binding
// that serves hand-written files; expected values are written out here, or
// read from the repository (plugin.json), never from the code under test.
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { parseAccept, prefersMarkdown } from '../src/worker/accept';
import type { Env, WorkerConfig } from '../src/worker/env';
import { createHandler } from '../src/worker/site';
import { pageSearchTerms, TERMS_PER_PAGE } from '../src/worker/terms';
import { REPO_ROOT } from '../src/lib/repo';

const PLUGIN_VERSION = (JSON.parse(readFileSync(path.join(REPO_ROOT, '.claude-plugin/plugin.json'), 'utf8')) as { version: string }).version;
const CFG: WorkerConfig = { version: PLUGIN_VERSION, standardVersion: '1.1.0', origin: 'https://acs.synapti.ai' };
const BASE = 'https://acs.synapti.ai';

const HOME_MD = '# Agent Capability Standard\n\nHome page copy.\n';
const MUTATE_MD = '# mutate\n\nChange persistent state\n';
const GUIDE_MD = '# Getting started\n\nInstall the plugin.\n';
const NOT_FOUND_HTML = '<!DOCTYPE html><html lang="en"><title>Page not found</title><h1>Page not found</h1></html>';

const PAGES_JSON = {
  api_version: 'v1',
  count: 4,
  pages: [
    { url: `${BASE}/`, markdown_url: `${BASE}/index.md`, title: 'Agent Capability Standard', description: 'What an AI agent can do.', section: 'home', headings: [{ level: 2, text: 'Layers' }] },
    {
      url: `${BASE}/capabilities/mutate/`,
      markdown_url: `${BASE}/capabilities/mutate/index.md`,
      title: 'mutate',
      description: null,
      section: 'capabilities',
      headings: [{ level: 2, text: 'Safety' }],
    },
    {
      url: `${BASE}/guides/getting-started/`,
      markdown_url: `${BASE}/guides/getting-started/index.md`,
      title: 'Getting started',
      description: 'Install the plugin and run a workflow with a checkpoint.',
      section: 'guides',
      headings: [{ level: 2, text: 'Install' }],
    },
    {
      url: `${BASE}/workflows/debug-code-change/`,
      markdown_url: `${BASE}/workflows/debug-code-change/index.md`,
      title: 'Debug a code change',
      description: 'Find a bug, checkpoint, then mutate the code.',
      section: 'workflows',
      headings: [],
    },
  ],
};
const MUTATE_RECORD = { id: 'mutate', layer: 'EXECUTE', description: 'Change persistent state', risk: 'high', page_url: `${BASE}/capabilities/mutate/`, markdown_url: `${BASE}/capabilities/mutate/index.md` };
const FLOW_RECORD = { id: 'debug_code_change', goal: 'Debug a code change safely', page_url: `${BASE}/workflows/debug-code-change/`, steps: [{ index: 0, capability: 'checkpoint' }] };

interface FakeFile {
  body: string;
  type: string;
}

const FILES: Record<string, FakeFile> = {
  '/index.html': { body: '<!DOCTYPE html><html lang="en"><h1>Home</h1></html>', type: 'text/html; charset=utf-8' },
  '/index.md': { body: HOME_MD, type: 'text/markdown; charset=utf-8' },
  '/capabilities/mutate/index.html': { body: '<!DOCTYPE html><h1>mutate</h1>', type: 'text/html; charset=utf-8' },
  '/capabilities/mutate/index.md': { body: MUTATE_MD, type: 'text/markdown; charset=utf-8' },
  '/guides/getting-started/index.html': { body: '<!DOCTYPE html><h1>Getting started</h1>', type: 'text/html; charset=utf-8' },
  '/guides/getting-started/index.md': { body: GUIDE_MD, type: 'text/markdown; charset=utf-8' },
  '/_astro/site.css': { body: 'body{}', type: 'text/css' },
  '/llms.txt': { body: '# Agent Capability Standard\n', type: 'text/plain; charset=utf-8' },
  '/spec/1.1.0/index.md': { body: '# The Standard\n', type: 'text/markdown; charset=utf-8' },
  '/api/v1/pages.json': { body: JSON.stringify(PAGES_JSON), type: 'application/json' },
  '/api/v1/capabilities.json': { body: JSON.stringify({ count: 1, capabilities: [MUTATE_RECORD] }), type: 'application/json' },
  '/api/v1/capabilities/mutate.json': { body: JSON.stringify({ api_version: 'v1', capability: MUTATE_RECORD }), type: 'application/json' },
  '/api/v1/workflows.json': { body: JSON.stringify({ count: 1, workflows: [FLOW_RECORD] }), type: 'application/json' },
  '/api/v1/workflows/debug_code_change.json': { body: JSON.stringify({ api_version: 'v1', workflow: FLOW_RECORD }), type: 'application/json' },
};

/** A stand-in for the Pages asset server: directory paths get index.html, a missing file the 404 page. */
function fakeEnv(files: Record<string, FakeFile> = FILES): Env & { calls: string[] } {
  const calls: string[] = [];
  return {
    calls,
    ASSETS: {
      async fetch(input: Request | string | URL) {
        const req = input instanceof Request ? input : new Request(input);
        const p = new URL(req.url).pathname;
        calls.push(p);
        const f = files[p.endsWith('/') ? `${p}index.html` : p];
        const body = (b: string) => (req.method === 'HEAD' ? null : b);
        if (!f) return new Response(body(NOT_FOUND_HTML), { status: 404, headers: { 'Content-Type': 'text/html; charset=utf-8' } });
        // Like Pages: an ETag per file, CORS open, and a 304 for a matching If-None-Match.
        const headers = { 'Content-Type': f.type, ETag: `"etag-${p}"`, 'Access-Control-Allow-Origin': '*' };
        if (req.headers.get('If-None-Match') === headers.ETag) return new Response(null, { status: 304, headers });
        return new Response(body(f.body), { status: 200, headers });
      },
    },
  };
}

const handle = createHandler(CFG);

function get(p: string, headers: Record<string, string> = {}, method = 'GET', env = fakeEnv()) {
  return handle(new Request(`${BASE}${p}`, { method, headers }), env);
}

const BROWSER_ACCEPT = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8';

describe('Accept negotiation', () => {
  it.each([
    ['text/markdown', true],
    ['text/html', false],
    ['*/*', false],
    ['text/*', false],
    ['', false],
    [BROWSER_ACCEPT, false],
    ['text/markdown, */*', true],
    ['text/markdown, text/html', true],
    ['text/html, text/markdown', false],
    ['text/markdown;q=0.9, text/html', false],
    ['text/html;q=0.5, text/markdown;q=0.8', true],
    ['text/markdown;q=0', false],
    ['text/plain, text/markdown;q=0.1, text/html;q=0.05', true],
    ['TEXT/MARKDOWN', true],
  ])('Accept "%s" prefers Markdown: %s', (accept, want) => {
    expect(prefersMarkdown(accept)).toBe(want);
  });

  it('reads q-values and drops entries that are not media ranges', () => {
    expect(parseAccept('text/markdown;q=0.4, nonsense, text/html; level=1; q=0.7')).toEqual([
      { type: 'text', subtype: 'markdown', q: 0.4, index: 0 },
      { type: 'text', subtype: 'html', q: 0.7, index: 2 },
    ]);
  });
});

describe('pages and their Markdown copies', () => {
  it('answers Accept: text/markdown on a page with its Markdown copy, Vary and a canonical link', async () => {
    const res = await get('/', { Accept: 'text/markdown' });
    expect(res.status).toBe(200);
    expect(res.headers.get('Content-Type')).toBe('text/markdown; charset=utf-8');
    expect(res.headers.get('Vary')).toContain('Accept');
    expect(res.headers.get('Link')).toBe('<https://acs.synapti.ai/>; rel="canonical"');
    expect(await res.text()).toBe(HOME_MD);
  });

  it('answers an HTML request with the page, Vary: Accept and the discovery Link headers', async () => {
    const res = await get('/capabilities/mutate/', { Accept: BROWSER_ACCEPT });
    expect(res.status).toBe(200);
    expect(res.headers.get('Content-Type')).toBe('text/html; charset=utf-8');
    expect(res.headers.get('Vary')).toContain('Accept');
    const link = res.headers.get('Link') ?? '';
    expect(link).toContain('</capabilities/mutate/index.md>; rel="alternate"; type="text/markdown"');
    expect(link).toContain('</sitemap.xml>; rel="sitemap"');
    expect(link).toContain('</openapi.json>; rel="service-desc"');
    expect(link).toContain('</.well-known/api-catalog>; rel="api-catalog"');
    expect(await res.text()).toBe(FILES['/capabilities/mutate/index.html']!.body);
  });

  it('keeps HTML for curl\'s */*', async () => {
    const res = await get('/', { Accept: '*/*' });
    expect(res.headers.get('Content-Type')).toBe('text/html; charset=utf-8');
  });

  it('serves <page>.md as the page\'s Markdown copy', async () => {
    const res = await get('/capabilities/mutate.md');
    expect(res.status).toBe(200);
    expect(res.headers.get('Content-Type')).toBe('text/markdown; charset=utf-8');
    expect(res.headers.get('Link')).toBe('<https://acs.synapti.ai/capabilities/mutate/>; rel="canonical"');
    expect(await res.text()).toBe(MUTATE_MD);
  });

  it('serves <page>/index.md with the Markdown type and a canonical link', async () => {
    const res = await get('/guides/getting-started/index.md');
    expect(res.headers.get('Content-Type')).toBe('text/markdown; charset=utf-8');
    expect(res.headers.get('Link')).toBe('<https://acs.synapti.ai/guides/getting-started/>; rel="canonical"');
    expect(await res.text()).toBe(GUIDE_MD);
  });

  it('keeps the static file\'s ETag and CORS header on a Markdown answer', async () => {
    for (const [p, headers] of [
      ['/capabilities/mutate/index.md', {}],
      ['/capabilities/mutate.md', {}],
      ['/capabilities/mutate/', { Accept: 'text/markdown' }],
    ] as const) {
      const res = await get(p, headers);
      expect(res.headers.get('ETag'), p).toBe('"etag-/capabilities/mutate/index.md"');
      expect(res.headers.get('Access-Control-Allow-Origin'), p).toBe('*');
    }
  });

  it('answers a conditional request for a fresh Markdown copy with 304', async () => {
    const res = await get('/capabilities/mutate/', { Accept: 'text/markdown', 'If-None-Match': '"etag-/capabilities/mutate/index.md"' });
    expect(res.status).toBe(304);
    expect(res.headers.get('Vary')).toContain('Accept');
    expect(await res.text()).toBe('');
    const stale = await get('/capabilities/mutate/', { Accept: 'text/markdown', 'If-None-Match': '"other"' });
    expect(stale.status).toBe(200);
  });

  it('negotiates a page path given without its trailing slash', async () => {
    const res = await get('/capabilities/mutate', { Accept: 'text/markdown' });
    expect(await res.text()).toBe(MUTATE_MD);
  });

  it('gives GPTBot, ClaudeBot, PerplexityBot and the user fetchers Markdown even when they ask for HTML', async () => {
    for (const ua of [
      'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)',
      'Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)',
      'Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)',
      'Mozilla/5.0 (compatible; ChatGPT-User/1.0; +https://openai.com/bot)',
      'Claude-User/1.0',
      'Perplexity-User/1.0',
    ]) {
      const res = await get('/', { 'User-Agent': ua, Accept: 'text/html' });
      expect(res.headers.get('Content-Type'), ua).toBe('text/markdown; charset=utf-8');
      expect(res.headers.get('Vary'), ua).toContain('User-Agent');
    }
  });

  it('gives the search-index crawlers and browsers HTML', async () => {
    for (const ua of ['Mozilla/5.0 (compatible; OAI-SearchBot/1.0)', 'Mozilla/5.0 (compatible; Claude-SearchBot/1.0)', 'Mozilla/5.0 (compatible; Googlebot/2.1)']) {
      const res = await get('/', { 'User-Agent': ua, Accept: 'text/html' });
      expect(res.headers.get('Content-Type'), ua).toBe('text/html; charset=utf-8');
    }
  });

  it('leaves static assets untouched and does not look for a Markdown copy', async () => {
    const env = fakeEnv();
    const res = await get('/_astro/site.css', { Accept: 'text/markdown' }, 'GET', env);
    expect(res.headers.get('Content-Type')).toBe('text/css');
    expect(res.headers.get('Link')).toBeNull();
    expect(env.calls).toEqual(['/_astro/site.css']);
  });

  it('sends no body for HEAD', async () => {
    const res = await get('/', { Accept: 'text/markdown' }, 'HEAD');
    expect(res.status).toBe(200);
    expect(res.headers.get('Content-Type')).toBe('text/markdown; charset=utf-8');
    expect(await res.text()).toBe('');
  });

  it('falls back to the static file when its own work fails', async () => {
    const env = fakeEnv();
    let first = true;
    const inner = env.ASSETS.fetch.bind(env.ASSETS);
    env.ASSETS.fetch = async (input) => {
      if (first) {
        first = false;
        throw new Error('asset read failed');
      }
      return inner(input);
    };
    const res = await handle(new Request(`${BASE}/`, { headers: { Accept: 'text/markdown' } }), env);
    expect(res.status).toBe(200);
    expect(await res.text()).toBe(FILES['/index.html']!.body);
  });

  it('marks responses on a pages.dev host noindex', async () => {
    const res = await handle(new Request('https://abc.acs-docs.pages.dev/', { headers: { Accept: 'text/markdown' } }), fakeEnv());
    expect(res.headers.get('X-Robots-Tag')).toBe('noindex');
  });
});

describe('not found', () => {
  it('keeps the HTML 404 page for a browser', async () => {
    const res = await get('/no/such/page/', { Accept: BROWSER_ACCEPT });
    expect(res.status).toBe(404);
    expect(res.headers.get('Content-Type')).toBe('text/html; charset=utf-8');
    expect(await res.text()).toBe(NOT_FOUND_HTML);
  });

  it.each([['*/*'], ['text/markdown'], ['application/json']])('answers Accept "%s" with a Markdown 404 that points to llms.txt, the sitemap and the developer page', async (accept) => {
    const res = await get('/no/such/page/', { Accept: accept });
    expect(res.status).toBe(404);
    expect(res.headers.get('Content-Type')).toBe('text/markdown; charset=utf-8');
    const body = await res.text();
    expect(body.startsWith('# ')).toBe(true);
    for (const target of ['https://acs.synapti.ai/llms.txt', 'https://acs.synapti.ai/sitemap.xml', 'https://acs.synapti.ai/developers/']) expect(body).toContain(target);
  });

  it('answers a <page>.md with no page with a Markdown 404', async () => {
    const res = await get('/capabilities/nothing.md', { Accept: BROWSER_ACCEPT });
    expect(res.status).toBe(404);
    expect(res.headers.get('Content-Type')).toBe('text/markdown; charset=utf-8');
  });

  it('answers an unknown /api/v1/ path with RFC 9457 problem details', async () => {
    const res = await get('/api/v1/capabilities/nothing.json', { Accept: BROWSER_ACCEPT });
    expect(res.status).toBe(404);
    expect(res.headers.get('Content-Type')).toBe('application/problem+json');
    expect(await res.json()).toEqual({
      type: 'https://acs.synapti.ai/developers/#ref-errors',
      title: 'Not Found',
      status: 404,
      detail: 'There is no resource at /api/v1/capabilities/nothing.json. /api/v1/index.json lists the resources, and https://acs.synapti.ai/openapi.json describes them.',
      instance: '/api/v1/capabilities/nothing.json',
    });
  });

  it('passes an existing API file through', async () => {
    const res = await get('/api/v1/capabilities/mutate.json');
    expect(res.status).toBe(200);
    expect(res.headers.get('Content-Type')).toBe('application/json');
  });
});

// ------------------------------------------------------------------ MCP

const MODERN = '2026-07-28';
const META = { 'io.modelcontextprotocol/protocolVersion': MODERN, 'io.modelcontextprotocol/clientCapabilities': {} };

let nextId = 1;
async function rpc(method: string, params?: Record<string, unknown>, opts: { headers?: Record<string, string>; modern?: boolean; env?: Env } = {}) {
  const id = nextId++;
  const modern = opts.modern ?? false;
  const headers: Record<string, string> = { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' };
  let p = params;
  if (modern) {
    p = { ...(params ?? {}), _meta: META };
    headers['MCP-Protocol-Version'] = MODERN;
    headers['Mcp-Method'] = method;
    if (method === 'tools/call') headers['Mcp-Name'] = String(params?.name);
    if (method === 'resources/read') headers['Mcp-Name'] = String(params?.uri);
  }
  Object.assign(headers, opts.headers ?? {});
  const res = await handle(
    new Request(`${BASE}/mcp`, { method: 'POST', headers, body: JSON.stringify({ jsonrpc: '2.0', id, method, ...(p ? { params: p } : {}) }) }),
    opts.env ?? fakeEnv(),
  );
  return { res, body: (await res.json()) as { id: number; result?: Record<string, any>; error?: { code: number; message: string; data?: any } } };
}

const callTool = (name: string, args: unknown, modern = false) => rpc('tools/call', { name, arguments: args }, { modern });

describe('MCP server: request bodies', () => {
  const LIMIT = 64 * 1024; // the 64 KiB limit the server states in its 413 message
  const HEADERS = { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' };

  /** A chunked body with no Content-Length: `chunks` chunks of `size` bytes, counting what the server pulls. */
  function streamed(chunks: number, size: number) {
    let pulled = 0;
    let sent = 0;
    const stream = new ReadableStream<Uint8Array>({
      pull(c) {
        if (sent === chunks) return c.close();
        sent += 1;
        pulled += size;
        c.enqueue(new Uint8Array(size).fill(0x20));
      },
    });
    return { stream, pulled: () => pulled };
  }

  it('stops reading a chunked body without Content-Length once it passes 64 KiB, and answers 413', async () => {
    const body = streamed(128, 16 * 1024); // 2 MiB in all
    const env = fakeEnv();
    const res = await handle(new Request(`${BASE}/mcp`, { method: 'POST', headers: HEADERS, body: body.stream, duplex: 'half' } as RequestInit), env);
    expect(res.status).toBe(413);
    expect(((await res.json()) as any).error.code).toBe(-32600);
    expect(body.pulled()).toBeLessThanOrEqual(LIMIT + 2 * 16 * 1024);
  });

  it('counts bytes, not characters', async () => {
    // 40,000 two-byte characters: 80,000 bytes, under 64 Ki characters.
    const text = JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'ping', params: { pad: '\u00e9'.repeat(40_000) } });
    expect(text.length).toBeLessThan(LIMIT);
    expect(new TextEncoder().encode(text).length).toBeGreaterThan(LIMIT);
    const enc = new TextEncoder().encode(text);
    const stream = new ReadableStream<Uint8Array>({ start(c) { c.enqueue(enc); c.close(); } });
    const res = await handle(new Request(`${BASE}/mcp`, { method: 'POST', headers: HEADERS, body: stream, duplex: 'half' } as RequestInit), fakeEnv());
    expect(res.status).toBe(413);
  });

  it('answers a body that fails to read with a JSON-RPC internal error, not a static file', async () => {
    const stream = new ReadableStream<Uint8Array>({
      pull(c) {
        c.error(new Error('connection reset'));
      },
    });
    const env = fakeEnv();
    const res = await handle(new Request(`${BASE}/mcp`, { method: 'POST', headers: HEADERS, body: stream, duplex: 'half' } as RequestInit), env);
    expect(res.status).toBe(500);
    expect(res.headers.get('Content-Type')).toBe('application/json');
    expect(res.headers.get('Access-Control-Allow-Origin')).toBe('*');
    expect(await res.json()).toEqual({ jsonrpc: '2.0', id: null, error: { code: -32603, message: 'Internal error' } });
    expect(env.calls).toEqual([]);
  });
});

describe('MCP server: protocol', () => {
  it('answers initialize with the server name, the plugin version and instructions that start with search_standard', async () => {
    const { res, body } = await rpc('initialize', { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 't', version: '1' } });
    expect(res.status).toBe(200);
    expect(res.headers.get('Content-Type')).toBe('application/json');
    expect(res.headers.get('Mcp-Session-Id')).toBeNull();
    expect(body.result!.protocolVersion).toBe('2025-06-18');
    expect(body.result!.serverInfo).toMatchObject({ name: 'ai.synapti.acs/mcp', title: 'Agent Capability Standard docs', version: PLUGIN_VERSION });
    expect(body.result!.instructions).toContain('Start with search_standard');
    expect(body.result!.capabilities).toEqual({ tools: { listChanged: false }, resources: { listChanged: false, subscribe: false } });
  });

  it('offers its newest initialize-based version for one it does not support', async () => {
    const { body } = await rpc('initialize', { protocolVersion: '2024-11-05', capabilities: {}, clientInfo: { name: 't', version: '1' } });
    expect(body.result!.protocolVersion).toBe('2025-11-25');
  });

  it('accepts a notification with 202 and no body', async () => {
    const res = await handle(
      new Request(`${BASE}/mcp`, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' }, body: '{"jsonrpc":"2.0","method":"notifications/initialized"}' }),
      fakeEnv(),
    );
    expect(res.status).toBe(202);
    expect(await res.text()).toBe('');
  });

  it('answers server/discover (2026-07-28) with versions, capabilities, identity in _meta and resultType', async () => {
    const { res, body } = await rpc('server/discover', {}, { modern: true });
    expect(res.status).toBe(200);
    expect(body.result!.resultType).toBe('complete');
    expect(body.result!.supportedVersions).toEqual(['2026-07-28', '2025-11-25', '2025-06-18', '2025-03-26']);
    expect(body.result!._meta['io.modelcontextprotocol/serverInfo']).toMatchObject({ name: 'ai.synapti.acs/mcp', version: PLUGIN_VERSION });
    expect(body.result!.cacheScope).toBe('public');
  });

  it('rejects a modern request without the MCP-Protocol-Version header (400, -32020)', async () => {
    const { res, body } = await rpc('tools/list', {}, { modern: true, headers: { 'MCP-Protocol-Version': '' } });
    expect(res.status).toBe(400);
    expect(body.error!.code).toBe(-32020);
  });

  it('rejects an Mcp-Name header that differs from the tool name (400, -32020), and decodes a base64 one', async () => {
    const bad = await rpc('tools/call', { name: 'search_standard', arguments: { query: 'mutate' } }, { modern: true, headers: { 'Mcp-Name': 'read_page' } });
    expect(bad.res.status).toBe(400);
    expect(bad.body.error!.code).toBe(-32020);
    const encoded = `=?base64?${btoa('search_standard')}?=`;
    const good = await rpc('tools/call', { name: 'search_standard', arguments: { query: 'mutate' } }, { modern: true, headers: { 'Mcp-Name': encoded } });
    expect(good.res.status).toBe(200);
    expect(good.body.result!.isError).toBe(false);
  });

  it('rejects an unsupported modern version (400, -32022) and lists the supported ones', async () => {
    const { res, body } = await rpc('tools/list', { _meta: { ...META, 'io.modelcontextprotocol/protocolVersion': '2099-01-01' } }, { headers: { 'MCP-Protocol-Version': '2099-01-01', 'Mcp-Method': 'tools/list' } });
    expect(res.status).toBe(400);
    expect(body.error!.code).toBe(-32022);
    expect(body.error!.data).toEqual({ supported: ['2026-07-28', '2025-11-25', '2025-06-18', '2025-03-26'], requested: '2099-01-01' });
  });

  it('rejects a modern request without client capabilities (400, -32602)', async () => {
    const { res, body } = await rpc('tools/list', { _meta: { 'io.modelcontextprotocol/protocolVersion': MODERN } }, { headers: { 'MCP-Protocol-Version': MODERN, 'Mcp-Method': 'tools/list' } });
    expect(res.status).toBe(400);
    expect(body.error!.code).toBe(-32602);
  });

  it('answers an unknown method with -32601: HTTP 404 for a modern request, 200 for an initialize-based one', async () => {
    const modern = await rpc('prompts/list', {}, { modern: true });
    expect(modern.res.status).toBe(404);
    expect(modern.body.error!.code).toBe(-32601);
    const legacy = await rpc('prompts/list', {});
    expect(legacy.res.status).toBe(200);
    expect(legacy.body.error!.code).toBe(-32601);
  });

  it('answers a body that is not JSON with -32700 and a batch with -32600', async () => {
    const post = (body: string) =>
      handle(new Request(`${BASE}/mcp`, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' }, body }), fakeEnv());
    const parse = await post('{nope');
    expect(parse.status).toBe(400);
    expect(((await parse.json()) as { error: { code: number } }).error.code).toBe(-32700);
    const batch = await post('[{"jsonrpc":"2.0","id":1,"method":"tools/list"}]');
    expect(batch.status).toBe(400);
    expect(((await batch.json()) as { error: { code: number } }).error.code).toBe(-32600);
  });

  it('answers GET with 405 (no server-initiated stream) and OPTIONS with CORS headers', async () => {
    const g = await handle(new Request(`${BASE}/mcp`, { headers: { Accept: 'text/event-stream' } }), fakeEnv());
    expect(g.status).toBe(405);
    expect(g.headers.get('Allow')).toBe('POST, OPTIONS');
    const o = await handle(new Request(`${BASE}/mcp`, { method: 'OPTIONS', headers: { Origin: 'https://example.com' } }), fakeEnv());
    expect(o.status).toBe(204);
    expect(o.headers.get('Access-Control-Allow-Origin')).toBe('*');
  });

  it('refuses an Origin header that is not an origin (403) and accepts any web origin', async () => {
    const bad = await rpc('tools/list', {}, { headers: { Origin: 'javascript:alert(1)' } });
    expect(bad.res.status).toBe(403);
    const ok = await rpc('tools/list', {}, { headers: { Origin: 'https://example.com' } });
    expect(ok.res.status).toBe(200);
  });

  it('refuses a client that does not accept JSON (406)', async () => {
    const { res } = await rpc('tools/list', {}, { headers: { Accept: 'text/event-stream' } });
    expect(res.status).toBe(406);
  });
});

describe('MCP server: tools', () => {
  it('lists exactly the four read-only tools, in name order, with typed schemas and distinct descriptions', async () => {
    const { body } = await rpc('tools/list');
    const tools = body.result!.tools as any[];
    expect(tools.map((t) => t.name)).toEqual(['read_capability', 'read_page', 'read_workflow', 'search_standard']);
    for (const t of tools) {
      expect(t.annotations, t.name).toMatchObject({ readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false });
      expect(t.description.length, t.name).toBeGreaterThanOrEqual(20);
      expect(t.inputSchema.type, t.name).toBe('object');
      expect(t.inputSchema.required.length, t.name).toBeGreaterThan(0);
      for (const k of t.inputSchema.required) expect(t.inputSchema.properties[k].type, `${t.name}.${k}`).toBeDefined();
      expect(t.outputSchema.type, t.name).toBe('object');
      expect(JSON.stringify(t.outputSchema), t.name).not.toContain('$ref');
    }
    expect(new Set(tools.map((t) => t.description)).size).toBe(4);
  });

  it('adds resultType and cache hints to a modern tools/list', async () => {
    const { body } = await rpc('tools/list', {}, { modern: true });
    expect(body.result).toMatchObject({ resultType: 'complete', cacheScope: 'public' });
    expect(body.result!.ttlMs).toBeGreaterThan(0);
  });

  it('search_standard ranks the capability page first for its name and returns its id', async () => {
    const { body } = await callTool('search_standard', { query: 'mutate' });
    const r = body.result!;
    expect(r.isError).toBe(false);
    expect(r.content[0].text).toBe(JSON.stringify(r.structuredContent));
    expect(r.structuredContent.results[0]).toMatchObject({
      kind: 'capability',
      id: 'mutate',
      path: '/capabilities/mutate/',
      url: 'https://acs.synapti.ai/capabilities/mutate/',
      markdownUrl: 'https://acs.synapti.ai/capabilities/mutate/index.md',
      description: 'Change persistent state',
    });
    // "mutate" is also in the workflow's description.
    expect(r.structuredContent.total).toBe(2);
  });

  it('search_standard ranks pages with every word first, still lists pages with some, and honours limit', async () => {
    const { body } = await callTool('search_standard', { query: 'checkpoint install', limit: 5 });
    const r = body.result!.structuredContent;
    expect(r.terms).toEqual(['checkpoint', 'install']);
    expect(r.matched).toBe('all');
    // The guide has both words; the workflow has "checkpoint" only, in its description.
    expect(r.results.map((x: any) => [x.path, x.matchedTerms])).toEqual([
      ['/guides/getting-started/', 2],
      ['/workflows/debug-code-change/', 1],
    ]);
    const one = await callTool('search_standard', { query: 'checkpoint', limit: 1 });
    expect(one.body.result!.structuredContent.results).toHaveLength(1);
    expect(one.body.result!.structuredContent.total).toBe(2);
  });

  it('search_standard drops stopwords and meets word forms ("mutation" finds "mutate")', async () => {
    const { body } = await callTool('search_standard', { query: 'checkpoint before mutation' });
    expect(body.result!.structuredContent.terms).toEqual(['checkpoint', 'mutat']);
    expect(body.result!.structuredContent.matched).toBe('all');
    // The workflow's description has both words; mutate has one, in its title and id.
    expect(body.result!.structuredContent.results.map((x: any) => [x.path, x.matchedTerms])).toEqual([
      ['/capabilities/mutate/', 1],
      ['/workflows/debug-code-change/', 2],
      ['/guides/getting-started/', 1],
    ]);
  });

  it('search_standard reports "any" when no page has every word', async () => {
    const { body } = await callTool('search_standard', { query: 'install teleport' });
    expect(body.result!.structuredContent.matched).toBe('any');
    expect(body.result!.structuredContent.results.map((x: any) => x.path)).toEqual(['/guides/getting-started/']);
  });

  it('search_standard returns the workflow id the catalog uses, not the page slug', async () => {
    const { body } = await callTool('search_standard', { query: 'debug' });
    expect(body.result!.structuredContent.results[0]).toMatchObject({ kind: 'workflow', id: 'debug_code_change' });
  });

  it('read_capability returns the record inside the data API file', async () => {
    const { body } = await callTool('read_capability', { id: 'mutate' });
    expect(body.result!.structuredContent).toEqual({
      id: 'mutate',
      url: 'https://acs.synapti.ai/capabilities/mutate/',
      markdownUrl: 'https://acs.synapti.ai/capabilities/mutate/index.md',
      apiUrl: 'https://acs.synapti.ai/api/v1/capabilities/mutate.json',
      capability: MUTATE_RECORD,
    });
  });

  it('read_capability reports an unknown id as a tool error', async () => {
    const { res, body } = await callTool('read_capability', { id: 'teleport' });
    expect(res.status).toBe(200);
    expect(body.result!.isError).toBe(true);
    expect(body.result!.content[0].text).toContain('teleport');
  });

  it('read_workflow returns the workflow record and its page', async () => {
    const { body } = await callTool('read_workflow', { id: 'debug_code_change' });
    expect(body.result!.structuredContent).toEqual({
      id: 'debug_code_change',
      apiUrl: 'https://acs.synapti.ai/api/v1/workflows/debug_code_change.json',
      url: 'https://acs.synapti.ai/workflows/debug-code-change/',
      workflow: FLOW_RECORD,
    });
  });

  it('read_page returns the Markdown copy for a listed page, however its path is written', async () => {
    for (const p of ['/capabilities/mutate/', '/capabilities/mutate', 'capabilities/mutate', '/capabilities/mutate.md', 'https://acs.synapti.ai/capabilities/mutate/index.md']) {
      const { body } = await callTool('read_page', { path: p });
      expect(body.result!.structuredContent, p).toEqual({
        path: '/capabilities/mutate/',
        title: 'mutate',
        url: 'https://acs.synapti.ai/capabilities/mutate/',
        markdownUrl: 'https://acs.synapti.ai/capabilities/mutate/index.md',
        markdown: MUTATE_MD,
      });
    }
  });

  it('read_page reads only pages the index lists', async () => {
    const env = fakeEnv({ ...FILES, '/secret/index.md': { body: 'x', type: 'text/markdown' } });
    const { body } = await rpc('tools/call', { name: 'read_page', arguments: { path: '/secret/' } }, { env });
    expect(body.result!.isError).toBe(true);
    expect(env.calls).not.toContain('/secret/index.md');
    const other = await callTool('read_page', { path: 'https://example.com/capabilities/mutate/' });
    expect(other.body.error!.code).toBe(-32602);
  });

  it('answers an unknown tool and invalid arguments with -32602', async () => {
    expect((await callTool('delete_everything', {})).body.error!.code).toBe(-32602);
    expect((await callTool('search_standard', {})).body.error!.code).toBe(-32602);
    expect((await callTool('search_standard', { query: 'x', limit: 99 })).body.error!.code).toBe(-32602);
    expect((await callTool('search_standard', { query: 'x', extra: 1 })).body.error!.code).toBe(-32602);
    expect((await callTool('read_capability', { id: '../../secret' })).body.error!.code).toBe(-32602);
  });

  it('reports a missing page index as a tool error', async () => {
    const files = { ...FILES };
    delete files['/api/v1/pages.json'];
    const { body } = await rpc('tools/call', { name: 'search_standard', arguments: { query: 'mutate' } }, { env: fakeEnv(files) });
    expect(body.result!.isError).toBe(true);
  });
});

describe('MCP server: search quality', () => {
  // Hand-written pages that reproduce the review of c24b7af: a page with
  // every query word in its description and headings, and the two capability
  // pages, each with one word in its title and the other only in its body
  // text (its search_terms). A diagnostic code is only in body text.
  const page = (p: string, title: string, description: string | null, headings: string[], terms: string, section = 'background') => ({
    url: `${BASE}${p}`,
    markdown_url: `${BASE}${p}index.md`,
    title,
    description,
    section,
    headings: headings.map((text) => ({ level: 2, text })),
    search_terms: terms,
  });
  const pages = [
    page('/background/benchmarks/', 'Benchmark suite', 'Scenarios that checkpoint before a mutation.', ['Checkpoint scenarios', 'Mutation recovery'], 'benchmark scenario w602'),
    page('/capabilities/checkpoint/', 'checkpoint', 'Save state so it can be restored.', ['Safety'], 'mutat restor snapshot', 'capabilities'),
    page('/capabilities/mutate/', 'mutate', 'Change persistent state.', ['Safety'], 'checkpoint rollback', 'capabilities'),
    page('/spec/diagnostics/', 'Diagnostics', 'Every diagnostic code.', ['Warnings'], 'v102 w601 w602 warn', 'spec'),
    page('/rfcs/0004/', 'RFC-0004: Agent identity', 'Trust classes and their weights.', ['Trust classes map to weights'], 'identity trust', 'rfcs'),
    page('/domains/audio/', 'Audio Domain', 'A profile for audio.', ['Trust Weights'], 'audio trust weight', 'domains'),
  ];
  const caps = ['checkpoint', 'mutate'].map((id) => ({ id, description: '', page_url: `${BASE}/capabilities/${id}/` }));
  const files: Record<string, FakeFile> = {
    '/api/v1/pages.json': { body: JSON.stringify({ count: pages.length, pages }), type: 'application/json' },
    '/api/v1/capabilities.json': { body: JSON.stringify({ count: 2, capabilities: caps }), type: 'application/json' },
    '/api/v1/workflows.json': { body: JSON.stringify({ count: 0, workflows: [] }), type: 'application/json' },
    '/api/v1/diagnostics.json': {
      body: JSON.stringify({ count: 1, diagnostics: [{ code: 'W602', severity: 'warning', page_url: `${BASE}/spec/diagnostics/#w602` }] }),
      type: 'application/json',
    },
  };
  const search = async (query: string) =>
    (await rpc('tools/call', { name: 'search_standard', arguments: { query } }, { env: fakeEnv(files) })).body.result!.structuredContent;

  it('"checkpoint before mutation" ranks the checkpoint and mutate capabilities first', async () => {
    const r = await search('checkpoint before mutation');
    expect(r.results.slice(0, 2).map((x: any) => x.id).sort()).toEqual(['checkpoint', 'mutate']);
    expect(r.results.map((x: any) => x.path)).toContain('/background/benchmarks/');
  });

  it('finds a diagnostic code in body text and ranks the page that defines it first', async () => {
    const r = await search('W602');
    expect(r.results.map((x: any) => x.path)).toEqual(['/spec/diagnostics/', '/background/benchmarks/']);
  });

  it('ranks a page with the query as a heading above one with the words apart', async () => {
    const r = await search('trust weights');
    expect(r.results[0].path).toBe('/domains/audio/');
  });
});

describe('page search terms (built into pages.json)', () => {
  it('keeps every diagnostic code, the words that set a page apart, and no link targets', () => {
    const filler = Array.from({ length: TERMS_PER_PAGE + 10 }, (_, i) => `filler${String.fromCharCode(97 + (i % 26))}${String.fromCharCode(97 + Math.floor(i / 26))}`).join(' ');
    const [a, b] = pageSearchTerms([
      `Mutations need a checkpoint. Checkpoint the mutation first; W602 warns. See [the guide](https://example.com/teleport/). ${filler} standard standard`,
      'The standard names capabilities. Standard text.',
    ]);
    const ta = a!.split(' ');
    expect(ta).toContain('w602');
    expect(ta).toContain('checkpoint');
    expect(ta).toContain('mutat');
    expect(ta).not.toContain('teleport');
    expect(ta).not.toContain('standard'); // on every page: sets nothing apart
    expect(ta.length).toBeLessThanOrEqual(TERMS_PER_PAGE + 1);
    expect(b!.split(' ')).toContain('capabilit');
  });
});

describe('MCP server: resources', () => {
  it('lists llms.txt, the current Standard and the OpenAPI description', async () => {
    const { body } = await rpc('resources/list');
    expect(body.result!.resources.map((r: any) => [r.uri, r.mimeType])).toEqual([
      ['https://acs.synapti.ai/llms.txt', 'text/plain'],
      ['https://acs.synapti.ai/spec/1.1.0/index.md', 'text/markdown'],
      ['https://acs.synapti.ai/openapi.json', 'application/json'],
    ]);
  });

  it('reads a listed resource', async () => {
    const { body } = await rpc('resources/read', { uri: 'https://acs.synapti.ai/llms.txt' }, { modern: true });
    expect(body.result!.contents).toEqual([{ uri: 'https://acs.synapti.ai/llms.txt', mimeType: 'text/plain', text: '# Agent Capability Standard\n' }]);
    expect(body.result!.resultType).toBe('complete');
  });

  it('answers an unknown resource with -32602 (2026-07-28) or -32002 (earlier)', async () => {
    expect((await rpc('resources/read', { uri: 'https://acs.synapti.ai/nothing' }, { modern: true })).body.error!.code).toBe(-32602);
    expect((await rpc('resources/read', { uri: 'https://acs.synapti.ai/nothing' })).body.error!.code).toBe(-32002);
  });
});

describe('MCP server card', () => {
  it.each([
    ['/mcp/server-card', 'application/mcp-server-card+json'],
    ['/.well-known/mcp/server-card.json', 'application/json'],
  ])('%s describes the server without its tools', async (p, type) => {
    const res = await get(p);
    expect(res.status).toBe(200);
    expect(res.headers.get('Content-Type')).toBe(type);
    expect(res.headers.get('Access-Control-Allow-Origin')).toBe('*');
    const card = (await res.json()) as Record<string, any>;
    expect(card.$schema).toBe('https://static.modelcontextprotocol.io/schemas/v1/server-card.schema.json');
    expect(card.name).toBe('ai.synapti.acs/mcp');
    expect(card.name).toMatch(/^[a-zA-Z0-9.-]+\/[a-zA-Z0-9._-]+$/);
    expect(card.version).toBe(PLUGIN_VERSION);
    expect(card.description.length).toBeLessThanOrEqual(100);
    expect(card.title).toBe('Agent Capability Standard docs');
    expect(card.icons[0].src).toBe('https://acs.synapti.ai/favicon.svg');
    expect(card.remotes).toEqual([{ type: 'streamable-http', url: 'https://acs.synapti.ai/mcp', supportedProtocolVersions: ['2026-07-28', '2025-11-25', '2025-06-18', '2025-03-26'] }]);
    expect(card.tools).toBeUndefined();
  });
});
