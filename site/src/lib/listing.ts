// Cards for a section's listing page: every other page of the section, in
// sidebar order, grouped by sidebar group. A card's description is the route's
// own, else the one remark-page-meta read from the source, cut to 160
// characters; a page built from data has its own in GENERATED_DESCRIPTIONS.
import { getEntry, render } from 'astro:content';
import type { PageMeta } from '../plugins/remark-page-meta';
import { shortDescription } from '../plugins/remark-page-meta';
import { GENERATED_DESCRIPTIONS } from './generated';
import { ROUTES, type Route } from './routes';

export interface ListingItem {
  title: string;
  url: string;
  description: string | null;
  route: Route;
}

export interface ListingGroup {
  label: string | null;
  items: ListingItem[];
}

export const CARD_DESCRIPTION_MAX = 160;

/** The intro line of each section's listing page, shared by the page and its Markdown copy. */
export const LISTING_INTROS: Readonly<Record<string, string>> = {
  '/start/':
    'Pages for a first look at the standard: what it is, how to install the plugin, a tutorial, common questions and the glossary.',
  '/guides/':
    'Guides to running workflows, the Claude Agent SDK, safety hooks, modality handling and writing skills.',
  '/compliance/':
    'How the standard supports compliance work under the EU AI Act, ISO/IEC 42001 and the NIST AI Risk Management Framework.',
  '/spec/':
    'The Standard itself, its conformance suite, the edge types, the diagnostic codes, the schemas, the security model and how to add a capability.',
  '/community/':
    'How to take part: contributing, governance, the code of conduct, the roadmap, the release notes, how to cite the standard and the press kit.',
  '/background/':
    'The research behind the standard: the whitepaper, the Grounded Agency paper, how the capabilities were derived, and supporting analysis.',
};


/** Title and description of a Markdown route, from the rendered source. */
export async function sourceMeta(route: Route): Promise<{ title: string; description: string | null }> {
  if (route.source === null) return { title: route.title, description: route.description ?? null };
  const entry = await getEntry('docs', route.source);
  if (!entry) throw new Error(`listing: no docs entry for ${route.source}`);
  const { remarkPluginFrontmatter } = await render(entry);
  const page = remarkPluginFrontmatter.page as PageMeta | undefined;
  return { title: page?.title ?? route.title, description: route.description ?? page?.description ?? null };
}

export async function listingGroups(
  index: Route,
  generated: Readonly<Record<string, string>> = Object.fromEntries(Object.entries(GENERATED_DESCRIPTIONS).map(([url, f]) => [url, f()])),
): Promise<ListingGroup[]> {
  const rows = ROUTES.filter((r) => r.section === index.section && r.url !== index.url).sort((a, b) => a.order - b.order);
  const groups: ListingGroup[] = [];
  for (const r of rows) {
    const meta = await sourceMeta(r);
    const raw = generated[r.url] ?? meta.description;
    const item: ListingItem = {
      title: r.title,
      url: r.url,
      description: raw === null ? null : shortDescription(raw, CARD_DESCRIPTION_MAX),
      route: r,
    };
    const label = r.group ?? null;
    let g = groups.find((x) => x.label === label);
    if (!g) {
      g = { label, items: [] };
      groups.push(g);
    }
    g.items.push(item);
  }
  return groups;
}
