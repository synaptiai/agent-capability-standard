// /api/v1/pages.json: every page of the site, for agents that search before
// they read (the MCP server's search_standard tool uses it). Titles,
// descriptions and headings come from each page's Markdown copy, so they are
// the words an agent will find when it reads it.
// The search terms (search_terms) are stems of the copy's body text, made with
// the worker's own word functions so a query meets them as written.
import { pageSearchTerms } from '../worker/terms';
import { computeAnchors } from './anchors';
import { API_BASE, envelope, type JsonObject } from './api';
import { SITE_ORIGIN } from './origin';
import { ROUTES, SECTIONS } from './routes';
import { twinFor } from '../twins';

export const PAGES_PATH = `${API_BASE}/pages.json`;

/** The H2 and H3 headings of a Markdown text, in order, with code fences skipped. */
export function pageHeadings(markdown: string): { level: number; text: string }[] {
  return computeAnchors(markdown)
    .entries.filter((h) => h.depth === 2 || h.depth === 3)
    .map((h) => ({ level: h.depth, text: h.text }));
}

export async function pageResources(): Promise<JsonObject[]> {
  const routes = [...ROUTES].sort((a, b) => SECTIONS.findIndex((s) => s.id === a.section) - SECTIONS.findIndex((s) => s.id === b.section) || a.order - b.order);
  const twins: Awaited<ReturnType<typeof twinFor>>[] = [];
  for (const r of routes) twins.push(await twinFor(r));
  const terms = pageSearchTerms(twins.map((t) => t.markdown));
  return routes.map((r, i) => {
    const t = twins[i]!;
    return {
      url: `${SITE_ORIGIN}${r.url}`,
      markdown_url: `${SITE_ORIGIN}${r.url}index.md`,
      title: t.title,
      description: t.description ? t.description.replace(/\s+/g, ' ').trim() : null,
      section: r.section,
      section_label: SECTIONS.find((s) => s.id === r.section)!.label,
      group: r.group ?? null,
      source: r.source,
      headings: pageHeadings(t.markdown),
      search_terms: terms[i]!,
    };
  });
}

export async function pagesFile(): Promise<JsonObject> {
  const pages = await pageResources();
  const sources = ['site/src/lib/routes.ts', ...new Set(ROUTES.flatMap((r) => [r.source, r.data]).filter((s): s is string => typeof s === 'string'))];
  return { ...envelope(sources), count: pages.length, pages };
}
