// The YAML front matter that opens each served Markdown copy: the page's
// title, description, canonical URL and the date of the last commit to the
// files it is built from. Only the served file at <route>index.md has it;
// llms-full.txt and the tests' source comparisons read the copy without it.
// Values are written as JSON strings, which YAML reads as the same strings,
// so a title with a colon or a quote needs no other escaping.
import { SITE_ORIGIN } from './origin';
import { pageLastModified } from './page-dates';
import type { Route } from './routes';
import type { Twin } from '../twins/types';

export function frontmatter(route: Route, twin: Pick<Twin, 'title' | 'description'>, lastUpdated: string | null = pageLastModified(route)): string {
  const fields: [string, string | null][] = [
    ['title', twin.title],
    ['description', twin.description === null ? null : twin.description.replace(/\s+/g, ' ').trim()],
    ['canonical', `${SITE_ORIGIN}${route.url}`],
    ['last_updated', lastUpdated],
  ];
  const lines = fields.filter((f): f is [string, string] => f[1] !== null).map(([k, v]) => `${k}: ${JSON.stringify(v)}`);
  return `---\n${lines.join('\n')}\n---\n\n`;
}

/** A served Markdown copy: front matter, then the copy. */
export function servedCopy(route: Route, twin: Twin): string {
  return `${frontmatter(route, twin)}${twin.markdown}`;
}
