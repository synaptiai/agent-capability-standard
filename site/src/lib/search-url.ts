// Shared by the search dialog and the pages that open it. Runs in the browser too.
import { SITE_ORIGIN } from './origin';

/** The event that opens the search dialog: detail is { query?: string }. */
export const SEARCH_EVENT = 'acs:search';

const HOST = new URL(SITE_ORIGIN).host;

/** A web search limited to this site, used where JavaScript does not run. */
export function siteSearchUrl(query = ''): string {
  return `https://duckduckgo.com/?q=${encodeURIComponent(`site:${HOST}${query ? ` ${query}` : ''}`)}`;
}
