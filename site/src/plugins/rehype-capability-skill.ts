// Visual aids in the SKILL.md of an atomic capability (skills/<id>/SKILL.md
// for an ontology capability; composed skills are left alone), keyed by the
// fixed H2s every such skill has (visual spec 3.1). The prose and the heading
// ids are not changed:
// - Procedure: the top-level ordered list gets numbered pixel tiles (CSS).
// - Examples: each "### Example N" and the content up to the next H3 or H2
//   becomes a <details> whose summary holds the heading with the code glyph
//   (caution for a title that contains "Failure"). The first is open. The
//   heading's hidden anchor link is dropped, so the summary holds no link.
// - Safety Constraints: the section's content sits in a panel with the
//   caution glyph.
// The port columns and the composition chain are Astro figures, which the
// page puts under their headings.
import type { Element, ElementContent, Root, RootContent } from 'hast';
import { loadOntology } from '../data/ontology';
import { glyphElement } from '../pixel/hast';
import { sourceOf } from './source';

const SKILL = /^skills\/([a-z_]+)\/SKILL\.md$/;

const isEl = (n: RootContent | ElementContent | undefined, tag?: string): n is Element =>
  n?.type === 'element' && (tag === undefined || n.tagName === tag);

function text(n: RootContent | ElementContent): string {
  if (n.type === 'text') return n.value;
  return n.type === 'element' ? n.children.map(text).join('') : '';
}

/** Index ranges [start, end) of each H2 section of the root, keyed by the H2's id. */
function sections(children: RootContent[]): Map<string, [number, number]> {
  const out = new Map<string, [number, number]>();
  const starts = children.flatMap((c, i) => (isEl(c, 'h2') ? [i] : []));
  starts.forEach((s, k) => {
    const id = String((children[s] as Element).properties?.id ?? '');
    out.set(id, [s, starts[k + 1] ?? children.length]);
  });
  return out;
}

/** True when the hast file is the SKILL.md of an ontology capability. */
export function isCapabilitySkill(repoPath: string): boolean {
  const m = SKILL.exec(repoPath);
  return m !== null && loadOntology().byId.has(m[1]!);
}

export default function rehypeCapabilitySkill() {
  return (tree: Root, file: Parameters<typeof sourceOf>[0]): void => {
    if (!file.path || !/[\\/]skills[\\/][a-z_]+[\\/]SKILL\.md$/.test(file.path)) return;
    if (!isCapabilitySkill(sourceOf(file, 'rehype-capability-skill').repoPath)) return;
    const kids = tree.children;

    // Procedure: number tiles on the first top-level ordered list.
    const proc = sections(kids).get('procedure');
    if (proc) {
      const ol = kids.slice(proc[0], proc[1]).find((c) => isEl(c, 'ol'));
      if (isEl(ol)) ol.properties = { ...ol.properties, className: [...((ol.properties?.className as string[]) ?? []), 'skill-steps'] };
    }

    // Safety Constraints: wrap the section body in a panel. Done before the
    // examples change the indices of later sections.
    const safety = sections(kids).get('safety-constraints');
    if (safety) {
      const [s, e] = safety;
      const body = kids.slice(s + 1, e).filter((c) => !(c.type === 'text' && c.value.trim() === '')) as ElementContent[];
      const panel: Element = {
        type: 'element',
        tagName: 'div',
        properties: { className: ['skill-safety'] },
        children: [glyphElement('caution', { scale: 3, className: 'skill-safety__glyph' }), { type: 'element', tagName: 'div', properties: { className: ['skill-safety__body'] }, children: body }],
      };
      kids.splice(s + 1, e - s - 1, panel);
    }

    // Examples: one <details> per H3.
    const ex = sections(kids).get('examples');
    if (ex) {
      const [s, e] = ex;
      const part = kids.slice(s + 1, e);
      const before: RootContent[] = [];
      const groups: { h3: Element; body: RootContent[] }[] = [];
      for (const c of part) {
        if (isEl(c, 'h3')) groups.push({ h3: c, body: [] });
        else if (groups.length === 0) before.push(c);
        else groups.at(-1)!.body.push(c);
      }
      if (groups.length > 0) {
        const details = groups.map(({ h3, body }, i): Element => {
          h3.children = h3.children.filter((c) => !(isEl(c, 'a') && ((c.properties?.className as string[]) ?? []).includes('heading-anchor')));
          const failure = /failure/i.test(text(h3));
          return {
            type: 'element',
            tagName: 'details',
            properties: { className: ['skill-example'], open: i === 0 ? true : undefined },
            children: [
              {
                type: 'element',
                tagName: 'summary',
                properties: { className: ['skill-example__summary'] },
                children: [glyphElement(failure ? 'caution' : 'code', { className: 'skill-example__glyph' }), h3],
              },
              { type: 'element', tagName: 'div', properties: { className: ['skill-example__body'] }, children: body as ElementContent[] },
            ],
          };
        });
        kids.splice(s + 1, e - s - 1, ...before, ...details);
      }
    }
  };
}
