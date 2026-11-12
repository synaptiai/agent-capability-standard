// Figures the prose templates place in rendered Markdown (visual spec 3.10.6):
// where a source block repeats a figure the site draws from data, the page
// shows the figure and keeps the block in a <details>. The match is by heading
// text, and cutAfterHeadings fails the build when the heading is gone.
import type { Ontology } from '../data/ontology';

/** The overview page's source. */
export const OVERVIEW_SOURCE = 'README.md';

/** The overview heading whose box drawing the periodic table replaces. */
export const PERIODIC_ANCHOR = 'The Periodic Table of Agent Capabilities';

/** The periodic table's caption, from the ontology. */
export function periodicCaption(o: Ontology): string {
  const sizes = o.layers.map((l) => l.capabilities.length);
  return `${o.capabilities.length} capabilities in ${o.layers.length} layers, one column per layer, from ${o.layers[0]!.id} with ${sizes[0]} to ${o.layers.at(-1)!.id} with ${sizes.at(-1)}.`;
}

/**
 * The first box-diagram figure of `html` (rehype-prose-figures frames them as
 * figure.fig-ascii), folded into a <details> with `summary`. html with no box
 * diagram is returned unchanged.
 */
export function foldFirstBox(html: string, summary: string): string {
  const m = /<figure class="fig fig-ascii"[\s\S]*?<\/figure>/.exec(html);
  if (!m) return html;
  const esc = summary.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  return `${html.slice(0, m.index)}<details class="fig-details"><summary>${esc}</summary>${m[0]}</details>${html.slice(m.index + m[0].length)}`;
}
