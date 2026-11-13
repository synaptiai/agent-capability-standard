// The docs MCP server at /mcp: Streamable HTTP, JSON responses, no sessions,
// read-only.
//
// It answers both eras of the protocol on one endpoint, as the 2026-07-28
// revision allows ("dual-era", basic/versioning):
// - modern (2026-07-28): every request carries its protocol version and
//   client capabilities in params._meta and the MCP-Protocol-Version,
//   Mcp-Method and Mcp-Name headers; there is no initialize; server/discover
//   describes the server; every result has resultType;
// - legacy (2025-11-25, 2025-06-18, 2025-03-26): initialize, then requests.
//   No session id is ever issued, so each request stands alone in this era too.
// A request is modern when its _meta names a protocol version, or when its
// MCP-Protocol-Version header names one that is not a legacy version;
// initialize is always legacy.
//
// Origin: the server is public, needs no credentials and returns only
// published documentation, so every web origin may call it (CORS "*"). The
// DNS-rebinding risk the Origin check guards against is a private server on
// a local network, which this is not. An Origin header that is not an origin
// at all is refused with 403.

import { accepts } from './accept';
import { SiteData } from './data';
import type { Env, WorkerConfig } from './env';
import { instructions, LEGACY_VERSIONS, MODERN_VERSIONS, serverInfo, SUPPORTED_VERSIONS } from './identity';
import { callTool, InvalidParams, isToolName, TOOLS } from './tools';

type Json = Record<string, unknown>;
type Id = string | number;

const META_VERSION = 'io.modelcontextprotocol/protocolVersion';
const META_CAPS = 'io.modelcontextprotocol/clientCapabilities';
const META_SERVER = 'io.modelcontextprotocol/serverInfo';

/** How long clients and shared caches may keep a list or a read (the content changes only on deploy). */
const TTL_MS = 3_600_000;
const MAX_BODY = 64 * 1024;

const CAPABILITIES = { tools: { listChanged: false }, resources: { listChanged: false, subscribe: false } };

export const CORS_HEADERS: Record<string, string> = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
  'Access-Control-Allow-Headers': '*',
  'Access-Control-Max-Age': '86400',
};

class RpcError extends Error {
  constructor(
    readonly code: number,
    message: string,
    readonly status = 200,
    readonly data?: unknown,
  ) {
    super(message);
  }
}

function json(body: unknown, status = 200, extra: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', ...CORS_HEADERS, ...extra },
  });
}

function rpcError(id: Id | null, e: RpcError): Response {
  return json({ jsonrpc: '2.0', id, error: { code: e.code, message: e.message, ...(e.data === undefined ? {} : { data: e.data }) } }, e.status);
}

/** A valid serialized origin ("https://example.com"), or "null". */
function validOrigin(value: string): boolean {
  if (value === 'null') return true;
  try {
    const u = new URL(value);
    return (u.protocol === 'https:' || u.protocol === 'http:') && u.origin === value;
  } catch {
    return false;
  }
}

/** Decode the "=?base64?...?=" form an Mcp-Name header may use. */
export function decodeHeaderValue(v: string): string {
  const m = /^=\?base64\?([A-Za-z0-9+/=]*)\?=$/.exec(v);
  if (!m) return v;
  try {
    const bin = atob(m[1]!);
    return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
  } catch {
    return v;
  }
}

function resources(cfg: WorkerConfig) {
  return [
    {
      uri: `${cfg.origin}/llms.txt`,
      name: 'llms-txt',
      title: 'Site index for language models (llms.txt)',
      description: 'Every page of the documentation site, with a one-line summary and a link to its Markdown copy.',
      mimeType: 'text/plain',
      path: '/llms.txt',
    },
    {
      uri: `${cfg.origin}/spec/${cfg.standardVersion}/index.md`,
      name: 'standard',
      title: `Agent Capability Standard ${cfg.standardVersion} (Markdown)`,
      description: 'The full text of the current version of the Standard.',
      mimeType: 'text/markdown',
      path: `/spec/${cfg.standardVersion}/index.md`,
    },
    {
      uri: `${cfg.origin}/openapi.json`,
      name: 'openapi',
      title: 'OpenAPI description of the data API',
      description: 'The read-only JSON data API under /api/v1/: capabilities, layers, edges, workflows, profiles, diagnostics and pages.',
      mimeType: 'application/json',
      path: '/openapi.json',
    },
  ];
}

interface Ctx {
  modern: boolean;
  data: SiteData;
  cfg: WorkerConfig;
}

function paramsOf(msg: Json): Json {
  const p = msg.params;
  if (p === undefined) return {};
  if (p === null || typeof p !== 'object' || Array.isArray(p)) throw new RpcError(-32602, 'params must be an object', 400);
  return p as Json;
}

async function dispatch(method: string, params: Json, ctx: Ctx): Promise<Json> {
  const { cfg, modern } = ctx;
  switch (method) {
    case 'initialize': {
      const asked = params.protocolVersion;
      const version = typeof asked === 'string' && (LEGACY_VERSIONS as readonly string[]).includes(asked) ? asked : LEGACY_VERSIONS[0];
      return { protocolVersion: version, capabilities: CAPABILITIES, serverInfo: serverInfo(cfg), instructions: instructions(cfg) };
    }
    case 'server/discover':
      return {
        supportedVersions: [...SUPPORTED_VERSIONS],
        capabilities: CAPABILITIES,
        instructions: instructions(cfg),
        ttlMs: TTL_MS,
        cacheScope: 'public',
      };
    case 'ping':
      if (modern) break;
      return {};
    case 'tools/list':
      return { tools: TOOLS, ...(modern ? { ttlMs: TTL_MS, cacheScope: 'public' } : {}) };
    case 'tools/call': {
      const name = params.name;
      if (typeof name !== 'string') throw new RpcError(-32602, 'tools/call needs params.name, the tool name');
      if (!isToolName(name)) throw new RpcError(-32602, `Unknown tool "${name}". The tools are ${TOOLS.map((t) => t.name).join(', ')}.`);
      try {
        return { ...(await callTool(name, params.arguments, ctx.data, cfg)) };
      } catch (e) {
        if (e instanceof InvalidParams) throw new RpcError(-32602, `Invalid arguments: ${e.message}`);
        throw e;
      }
    }
    case 'resources/list':
      return { resources: resources(cfg).map(({ path: _p, ...r }) => r), ...(modern ? { ttlMs: TTL_MS, cacheScope: 'public' } : {}) };
    case 'resources/templates/list':
      return { resourceTemplates: [], ...(modern ? { ttlMs: TTL_MS, cacheScope: 'public' } : {}) };
    case 'resources/read': {
      const uri = params.uri;
      if (typeof uri !== 'string') throw new RpcError(-32602, 'resources/read needs params.uri');
      const r = resources(cfg).find((x) => x.uri === uri);
      // 2026-07-28 reports a missing resource as -32602; earlier revisions used -32002.
      const notFound = (why: string) => new RpcError(modern ? -32602 : -32002, why, 200, { uri });
      if (!r) throw notFound(`Resource not found: ${uri}. resources/list names the resources.`);
      const text = await ctx.data.text(r.path);
      if (text === null) throw notFound(`Resource ${uri} could not be read.`);
      return { contents: [{ uri, mimeType: r.mimeType, text }], ...(modern ? { ttlMs: TTL_MS, cacheScope: 'public' } : {}) };
    }
  }
  // A modern server answers an unknown method with HTTP 404 (transports/streamable-http).
  throw new RpcError(-32601, `Method not found: ${method}`, modern ? 404 : 200);
}

/** Check the modern request headers against the body. Throws the error to return. */
function checkModern(request: Request, msg: Json, params: Json, metaVersion: unknown): void {
  const header = request.headers.get('MCP-Protocol-Version');
  const meta = (params._meta ?? {}) as Json;
  if (typeof metaVersion !== 'string') throw new RpcError(-32602, `params._meta["${META_VERSION}"] is required`, 400);
  if (header === null) throw new RpcError(-32020, 'Header mismatch: the MCP-Protocol-Version header is missing', 400);
  if (header !== metaVersion) {
    throw new RpcError(-32020, `Header mismatch: MCP-Protocol-Version header value '${header}' does not match body value '${metaVersion}'`, 400);
  }
  if (!(MODERN_VERSIONS as readonly string[]).includes(metaVersion)) {
    throw new RpcError(-32022, 'Unsupported protocol version', 400, { supported: [...SUPPORTED_VERSIONS], requested: metaVersion });
  }
  const caps = meta[META_CAPS];
  if (caps === null || typeof caps !== 'object' || Array.isArray(caps)) throw new RpcError(-32602, `params._meta["${META_CAPS}"] is required`, 400);
  const method = request.headers.get('Mcp-Method');
  if (method === null) throw new RpcError(-32020, 'Header mismatch: the Mcp-Method header is missing', 400);
  if (method !== msg.method) throw new RpcError(-32020, `Header mismatch: Mcp-Method header value '${method}' does not match body value '${String(msg.method)}'`, 400);
  if (msg.method === 'tools/call' || msg.method === 'resources/read' || msg.method === 'prompts/get') {
    const want = msg.method === 'resources/read' ? params.uri : params.name;
    const raw = request.headers.get('Mcp-Name');
    if (raw === null) throw new RpcError(-32020, 'Header mismatch: the Mcp-Name header is missing', 400);
    const name = decodeHeaderValue(raw);
    if (name !== want) throw new RpcError(-32020, `Header mismatch: Mcp-Name header value '${name}' does not match body value '${String(want)}'`, 400);
  }
}

/**
 * The request body as text, read a chunk at a time; null as soon as it passes
 * `max` bytes, without reading the rest (a chunked body has no
 * Content-Length to check first).
 */
async function readBody(request: Request, max: number): Promise<string | null> {
  if (request.body === null) return '';
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > max) {
      await reader.cancel().catch(() => undefined);
      return null;
    }
    chunks.push(value);
  }
  const all = new Uint8Array(size);
  let at = 0;
  for (const c of chunks) {
    all.set(c, at);
    at += c.byteLength;
  }
  return new TextDecoder().decode(all);
}

/** The answer when handling a request to the MCP endpoint throws: a JSON-RPC internal error. */
export function mcpInternalError(): Response {
  return rpcError(null, new RpcError(-32603, 'Internal error', 500));
}

/** Handle a request to the MCP endpoint. */
export async function handleMcp(request: Request, env: Env, cfg: WorkerConfig): Promise<Response> {
  const origin = request.headers.get('Origin');
  if (origin !== null && !validOrigin(origin)) return rpcError(null, new RpcError(-32600, `Forbidden: "${origin}" is not a valid origin`, 403));
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS_HEADERS });
  if (request.method !== 'POST') {
    // No server-initiated stream (GET) and no session to end (DELETE).
    return new Response(`This is the Model Context Protocol endpoint of ${cfg.origin}. Send JSON-RPC requests with POST. The server card is at ${cfg.origin}/mcp/server-card.\n`, {
      status: 405,
      headers: { Allow: 'POST, OPTIONS', 'Content-Type': 'text/plain; charset=utf-8', ...CORS_HEADERS },
    });
  }
  const accept = request.headers.get('Accept');
  if (!accepts(accept, 'application/json')) {
    return rpcError(null, new RpcError(-32600, 'Not Acceptable: this server answers with application/json; send Accept: application/json, text/event-stream', 406));
  }
  const tooLarge = () => rpcError(null, new RpcError(-32600, `Request body larger than ${MAX_BODY} bytes`, 413));
  const length = Number(request.headers.get('Content-Length') ?? '0');
  if (length > MAX_BODY) return tooLarge();
  const text = await readBody(request, MAX_BODY);
  if (text === null) return tooLarge();

  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    return rpcError(null, new RpcError(-32700, 'Parse error: the body is not JSON', 400));
  }
  if (Array.isArray(body)) return rpcError(null, new RpcError(-32600, 'Invalid Request: send one JSON-RPC message per POST, not a batch', 400));
  if (body === null || typeof body !== 'object') return rpcError(null, new RpcError(-32600, 'Invalid Request: the body must be a JSON-RPC object', 400));
  const msg = body as Json;
  const rawId = msg.id;
  const id: Id | null = typeof rawId === 'string' || (typeof rawId === 'number' && Number.isFinite(rawId)) ? rawId : null;
  if (msg.jsonrpc !== '2.0' || typeof msg.method !== 'string') {
    // A JSON-RPC response (result or error) from the client is not accepted either.
    return rpcError(id, new RpcError(-32600, 'Invalid Request: expected {"jsonrpc": "2.0", "method": ...}', 400));
  }
  if (!('id' in msg)) {
    // A notification, such as notifications/initialized: accepted, no body.
    return new Response(null, { status: 202, headers: CORS_HEADERS });
  }
  if (id === null) return rpcError(null, new RpcError(-32600, 'Invalid Request: id must be a string or a number', 400));

  let params: Json;
  try {
    params = paramsOf(msg);
  } catch (e) {
    return rpcError(id, e as RpcError);
  }
  const method = msg.method;
  const header = request.headers.get('MCP-Protocol-Version');
  const metaVersion = ((params._meta ?? {}) as Json)[META_VERSION];
  const modern = method !== 'initialize' && (metaVersion !== undefined || (header !== null && !(LEGACY_VERSIONS as readonly string[]).includes(header)));
  // server/discover is the probe a client sends before it knows the era; answer it either way.
  const strict = modern && !(method === 'server/discover' && metaVersion === undefined && header === null);

  try {
    if (strict) checkModern(request, msg, params, metaVersion);
    const result = await dispatch(method, params, { modern, data: new SiteData(env.ASSETS, request.url, cfg.origin), cfg });
    const out =
      modern || method === 'server/discover'
        ? { ...result, resultType: 'complete', _meta: { [META_SERVER]: serverInfo(cfg) } }
        : result;
    return json({ jsonrpc: '2.0', id, result: out });
  } catch (e) {
    if (e instanceof RpcError) return rpcError(id, e);
    return rpcError(id, new RpcError(-32603, 'Internal error', 500));
  }
}
