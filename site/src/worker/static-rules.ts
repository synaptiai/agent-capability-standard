// The static-file rules of public/_headers and public/_redirects, applied by
// the worker as well.
//
// Cloudflare's documentation says _headers and _redirects are not applied to
// responses a Pages worker returns. Under `wrangler pages dev` the responses
// the worker passes through from env.ASSETS do carry them, but that has not
// been confirmed on the production project. So the worker applies the same
// rules itself to every file it passes through: where Pages has already
// applied them, nothing changes. test/worker.test.ts checks that HEADER_RULES
// equals the path rules in public/_headers.

export interface HeaderRule {
  /** A path pattern in _headers syntax: an exact path, "/prefix/*" or "/*.ext". */
  pattern: string;
  headers: Readonly<Record<string, string>>;
}

const JSON_OPEN = { 'Content-Type': 'application/json; charset=utf-8', 'Access-Control-Allow-Origin': '*' };

export const HEADER_RULES: readonly HeaderRule[] = [
  { pattern: '/*.md', headers: { 'Content-Type': 'text/markdown; charset=utf-8' } },
  { pattern: '/llms.txt', headers: { 'Content-Type': 'text/plain; charset=utf-8' } },
  { pattern: '/llms-full.txt', headers: { 'Content-Type': 'text/plain; charset=utf-8' } },
  { pattern: '/api/*', headers: JSON_OPEN },
  { pattern: '/openapi.json', headers: JSON_OPEN },
  {
    pattern: '/.well-known/api-catalog',
    headers: {
      'Content-Type': 'application/linkset+json; profile="https://www.rfc-editor.org/info/rfc9727"',
      'Access-Control-Allow-Origin': '*',
    },
  },
];

export function matchesPattern(pattern: string, path: string): boolean {
  if (pattern.startsWith('/*')) return path.endsWith(pattern.slice(2));
  if (pattern.endsWith('*')) return path.startsWith(pattern.slice(0, -1));
  return path === pattern;
}

/** Whether the host is a pages.dev copy of the site, which stays out of search engines. */
export function isPagesDevHost(hostname: string): boolean {
  return hostname.endsWith('.pages.dev');
}

/**
 * A static file's response with the _headers rules for its path applied:
 * the Content-Type of a matching rule replaces the file's own on a 200 or
 * 304, any other rule header is added where the response lacks it, and a
 * pages.dev host gets X-Robots-Tag: noindex.
 */
export function withStaticRules(url: URL, res: Response): Response {
  const set: [string, string][] = [];
  const ok = res.status === 200 || res.status === 304;
  for (const rule of HEADER_RULES) {
    if (!matchesPattern(rule.pattern, url.pathname)) continue;
    for (const [name, value] of Object.entries(rule.headers)) {
      if (name === 'Content-Type' ? ok && res.headers.get(name) !== value : !res.headers.has(name)) set.push([name, value]);
    }
  }
  if (isPagesDevHost(url.hostname) && !res.headers.has('X-Robots-Tag')) set.push(['X-Robots-Tag', 'noindex']);
  if (set.length === 0) return res;
  const out = new Response(res.body, res);
  for (const [name, value] of set) out.headers.set(name, value);
  return out;
}

/** The _redirects target for a path, or null. */
export function redirectTarget(redirects: Readonly<Record<string, string>>, path: string): string | null {
  return Object.prototype.hasOwnProperty.call(redirects, path) ? redirects[path]! : null;
}
