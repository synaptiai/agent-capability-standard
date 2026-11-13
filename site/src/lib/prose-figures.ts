// Figures the prose templates place in rendered Markdown (visual spec 3.10.6):
// where a source block repeats a figure the site draws from data, the page
// shows the figure and keeps the block in a <details>. The match is by heading
// text, and cutAfterHeadings fails the build when the heading is gone.
import type { Ontology } from '../data/ontology';
import { foldFirst } from './inject';

/** The overview page's source. */
export const OVERVIEW_SOURCE = 'README.md';

/** The overview heading whose box drawing the periodic table replaces. */
export const PERIODIC_ANCHOR = 'The Periodic Table of Agent Capabilities';

/** The periodic table's caption, from the ontology: the total, then the largest and smallest layers. */
export function periodicCaption(o: Ontology): string {
  const sized = o.layers.map((l) => ({ id: l.id, n: l.capabilities.length }));
  const most = sized.reduce((a, b) => (b.n > a.n ? b : a));
  const least = sized.reduce((a, b) => (b.n < a.n ? b : a));
  return `${o.capabilities.length} capabilities in ${o.layers.length} layers; the largest layer, ${most.id}, has ${most.n} and the smallest, ${least.id}, has ${least.n}.`;
}

/**
 * The first box-diagram figure of `html` (rehype-prose-figures frames them as
 * figure.fig-ascii), folded into a <details> with `summary`. Throws when
 * there is none.
 */
export function foldFirstBox(html: string, summary: string, where: string): string {
  // The folded box is the text version of the figure drawn in its place,
  // which takes its number, so the box loses its "Fig n" eyebrow.
  return foldFirst(html, /<figure class="fig fig-ascii"/, 'figure', summary, 'box diagram', where, (box) =>
    box.replace(/(<p class="fig__eyebrow"[^>]*>)Fig \d+(<\/p>)/, '$1Text version$2'),
  );
}
