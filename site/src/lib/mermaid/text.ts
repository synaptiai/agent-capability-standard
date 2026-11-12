// The words for a flowchart: its title, a one-sentence caption, and a text
// version that lists every group, box and link. The HTML figure and the
// page's Markdown copy both use these, so they say the same thing.
import type { Diagram, MermaidEdge } from './parse';

export interface TextVersion {
  title: string;
  caption: string;
  items: string[];
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

function edgeWords(d: Diagram, e: MermaidEdge): string {
  const label = (id: string) => d.nodes.find((n) => n.id === id)!.label;
  const join = e.arrow ? '→' : '—';
  const kind = [e.style === 'dotted' ? 'dotted line' : e.style === 'thick' ? 'thick line' : null, e.arrow ? null : 'no arrowhead']
    .filter(Boolean)
    .join(', ');
  return `${label(e.from)} ${join} ${label(e.to)}${e.label ? `: ${e.label}` : ''}${kind ? ` (${kind})` : ''}`;
}

/**
 * The title is the diagram's own (frontmatter `title:` or `accTitle:`), else
 * "Diagram: {nearest heading}". The caption is the diagram's `accDescr:` when
 * it has one, else a count of what it draws.
 */
export function describeDiagram(d: Diagram, heading: string): TextVersion {
  const title = d.title ?? `Diagram: ${heading}`;
  const caption =
    d.description ??
    `${plural(d.nodes.length, 'box', 'boxes')} joined by ${plural(d.edges.length, 'link', 'links')}${
      d.groups.length > 0 ? `, in ${plural(d.groups.length, 'group', 'groups')}` : ''
    }.`;
  const items: string[] = [];
  for (const g of d.groups) {
    const members = d.nodes.filter((n) => n.group === g.id).map((n) => n.label);
    const inner = d.groups.filter((c) => c.parent === g.id).map((c) => c.label);
    items.push(`Group "${g.label}": ${[...members, ...inner].join(', ')}`);
  }
  for (const e of d.edges) items.push(edgeWords(d, e));
  const linked = new Set(d.edges.flatMap((e) => [e.from, e.to]));
  for (const n of d.nodes) if (!linked.has(n.id)) items.push(`${n.label} (not linked)`);
  return { title, caption, items };
}

/** Labels are plain text; these characters would start Markdown or HTML. */
function md(text: string): string {
  return text.replace(/[\\`*[\]<]/g, (c) => `\\${c}`);
}

/** The Markdown that follows the fence in the page's Markdown copy. */
export function twinBlock(d: Diagram, heading: string): string {
  const tv = describeDiagram(d, heading);
  return [`**Figure: ${md(tv.title)}.** ${md(tv.caption)}`, '', ...tv.items.map((i) => `- ${md(i)}`)].join('\n');
}
