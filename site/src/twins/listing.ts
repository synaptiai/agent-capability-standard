// Markdown copies of the section overview pages: the intro line and a link to
// every other page of the section, grouped as in the sidebar, with the text
// equivalent of each figure where the page shows it.
import { loadOntology } from '../data/ontology';
import { COMPOSED_SKILLS } from '../data/skills';
import { loadWorkflows } from '../data/workflows';
import { listingFigures, SKILLS_FIG_TITLE, skillsCaption, type ListingFigure } from '../lib/index-figures';
import { LISTING_INTROS, listingGroups } from '../lib/listing';
import { ROUTES, SECTIONS, type Route } from '../lib/routes';
import { blocks, code, figure, mdLink, table } from './md';
import type { Twin } from './types';

function figureText(f: ListingFigure): string {
  if (f.kind === 'matrix') {
    const m = f.matrix;
    return figure(m.title, m.caption, table([m.rowHead, ...m.columns.map((c) => c.label)], m.rows.map((r) => [r.url ? mdLink(r.label, r.url) : r.label, ...r.counts.map(String)])));
  }
  if (f.kind === 'bars') {
    return figure(f.bars.title, f.bars.caption, table([...f.bars.head], f.bars.rows.map((r) => [r.url ? mdLink(r.label, r.url) : r.label, r.words])));
  }
  const wfs = loadWorkflows();
  const rows = Object.keys(COMPOSED_SKILLS)
    .sort()
    .map((dir) => {
      const wf = COMPOSED_SKILLS[dir] ? wfs.byId.get(COMPOSED_SKILLS[dir]!) : null;
      return { dir, wf: wf ?? null, steps: wf ? wf.steps.length : null };
    });
  return figure(
    SKILLS_FIG_TITLE,
    skillsCaption(rows),
    table(
      ['Skill', 'Workflow', 'Steps in order'],
      rows.map((r) => [
        mdLink(r.dir, `/guides/skills/${r.dir}/`),
        r.wf ? mdLink(code(r.wf.id), `/workflows/${r.wf.slug}/`) : 'none',
        r.wf ? r.wf.steps.map((s) => s.capability).join(' → ') : '',
      ]),
    ),
  );
}

export async function listingTwin(route: Route): Promise<Twin> {
  const intro = LISTING_INTROS[route.url];
  if (intro === undefined) throw new Error(`twins: no listing intro for ${route.url}`);
  const label = SECTIONS.find((s) => s.id === route.section)!.label;
  const groups = await listingGroups(route);
  const figures = listingFigures(route.section, ROUTES, loadOntology().layers);
  const markdown = blocks(
    `# ${label}`,
    intro,
    ...figures.filter((f) => f.at === 'top').map(figureText),
    ...groups.map((g) =>
      blocks(
        g.label && `## ${g.label}`,
        ...figures.filter((f) => f.at === g.label).map(figureText),
        g.items.map((i) => `- ${mdLink(i.title, i.url)}${i.description ? `: ${i.description}` : ''}`).join('\n'),
      ),
    ),
  );
  return { title: label, description: intro, markdown };
}
