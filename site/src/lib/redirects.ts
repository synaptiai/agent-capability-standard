// public/_redirects for Cloudflare Pages, written into the build output when
// the build finishes, because the target comes from the data: /spec/ goes to
// the current Standard with a 302, so the target can move to a new version.
// The data API's base URL, which the api-catalog names, goes to its index file.
import { loadVersions } from '../data/versions';
import { API_BASE } from './api-paths';

export const REDIRECTS_FILE = '_redirects';

export function redirectsFile(): string {
  const v = loadVersions().standard.current.version;
  const api = `${API_BASE} ${API_BASE}/index.json 302\n${API_BASE}/ ${API_BASE}/index.json 302\n`;
  return `/spec /spec/${v}/ 302\n/spec/ /spec/${v}/ 302\n${api}`;
}
