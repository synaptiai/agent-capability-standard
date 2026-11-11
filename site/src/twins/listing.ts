// Markdown copies of the section overview pages: the intro line and a link to
// every other page of the section, grouped as in the sidebar.
import { LISTING_INTROS, listingGroups } from '../lib/listing';
import { SECTIONS, type Route } from '../lib/routes';
import { blocks, mdLink } from './md';
import type { Twin } from './types';

export async function listingTwin(route: Route): Promise<Twin> {
  const intro = LISTING_INTROS[route.url];
  if (intro === undefined) throw new Error(`twins: no listing intro for ${route.url}`);
  const label = SECTIONS.find((s) => s.id === route.section)!.label;
  const groups = await listingGroups(route);
  const markdown = blocks(
    `# ${label}`,
    intro,
    ...groups.map((g) =>
      blocks(
        g.label && `## ${g.label}`,
        g.items.map((i) => `- ${mdLink(i.title, i.url)}${i.description ? `: ${i.description}` : ''}`).join('\n'),
      ),
    ),
  );
  return { title: label, description: intro, markdown };
}
