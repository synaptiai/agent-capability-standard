// public/_redirects for Cloudflare Pages, written into the build output when
// the build finishes, because the target comes from the data: /spec/ goes to
// the current Standard with a 302, so the target can move to a new version.
import { loadVersions } from '../data/versions';

export const REDIRECTS_FILE = '_redirects';

export function redirectsFile(): string {
  const v = loadVersions().standard.current.version;
  return `/spec /spec/${v}/ 302\n/spec/ /spec/${v}/ 302\n`;
}
