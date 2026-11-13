// public/_redirects for Cloudflare Pages, written into the build output when
// the build finishes, because the target comes from the data: /spec/ goes to
// the current Standard with a 302, so the target can move to a new version.
// The data API's base URL, which the api-catalog names, goes to its index file.
import { loadVersions } from '../data/versions';
import { API_BASE } from './api-paths';

export const REDIRECTS_FILE = '_redirects';

/** Every redirect, from path to target, all 302. The worker applies the same table (src/worker/static-rules.ts). */
export function redirectRules(): Record<string, string> {
  const v = loadVersions().standard.current.version;
  return {
    '/spec': `/spec/${v}/`,
    '/spec/': `/spec/${v}/`,
    [API_BASE]: `${API_BASE}/index.json`,
    [`${API_BASE}/`]: `${API_BASE}/index.json`,
  };
}

export function redirectsFile(): string {
  return Object.entries(redirectRules())
    .map(([from, to]) => `${from} ${to} 302\n`)
    .join('');
}
