// Visual aids in the SKILL.md of an atomic capability (skills/<id>/SKILL.md
// for an ontology capability; composed skills are left alone), keyed by the
// fixed H2s every such skill has (visual spec 3.1). The prose and the heading
// ids are not changed:
// - Procedure: the top-level ordered list gets numbered pixel tiles (CSS).
// - Inputs: the parameter table's "Required" column gets a check glyph on
//   "Yes" and a cross on "No", as yes/no columns do on prose pages (visual
//   spec 3.10.10); with three or more rows the table is an enriched table
//   and counts as an information figure (visual spec 4.2).
// - Examples: each "### Example N" and the content up to the next H3 or H2
//   becomes a <details> whose summary holds the heading with the code glyph
//   (caution for a title that contains "Failure"). The
//   heading's hidden anchor link is dropped, so the summary holds no link.
//   Every example starts closed: an open first example was the longest run
//   without a figure on most capability pages (its fences alone are often
//   taller than a screen), and the summaries list every example.
// - Safety Constraints: the section's content sits in a panel with the
//   caution glyph.
// - Output Contract: the section's first code block folds into a
//   <details>, under the page's figure of the same fields. The "Field
//   Definitions" table gets a column that says, per field, whether the
//   ontology's output contract declares it, with the contract's type and
//   whether it is required (a check glyph), or that it is the skill's own (the
//   open-type glyph). Every row carries a glyph, so the table is an enriched
//   table and counts as an information figure (visual spec 4.2).
// The port columns and the composition chain are Astro figures, which the
// page puts under their headings.
import type { Element, ElementContent, Root, RootContent } from 'hast';
import { loadOntology, type Capability } from '../data/ontology';
import { contractRows } from '../lib/views';
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

/** A table, or the table a wrapper div holds (rehype-tables wraps each table in a div). */
function tableOf(n: RootContent): Element | undefined {
  if (!isEl(n)) return undefined;
  if (n.tagName === 'table') return n;
  return n.tagName === 'div' ? n.children.find((c): c is Element => isEl(c, 'table')) : undefined;
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

    // Output Contract: the section's first code block folds under a summary,
    // because the page draws its fields as a figure (F-C6) above it.
    const output = sections(kids).get('output-contract');
    if (output) {
      const [s, e] = output;
      const at = kids.slice(s + 1, e).findIndex((c) => isEl(c, 'pre'));
      if (at !== -1) {
        const i = s + 1 + at;
        const fold: Element = {
          type: 'element',
          tagName: 'details',
          properties: { className: ['fig-details', 'skill-fence'] },
          children: [
            { type: 'element', tagName: 'summary', properties: {}, children: [{ type: 'text', value: 'The output as the skill writes it, in YAML' }] },
            kids[i] as ElementContent,
          ],
        };
        kids.splice(i, 1, fold);
      }
    }

    // Inputs: check and cross glyphs on the Required column.
    const inputs = sections(kids).get('inputs');
    if (inputs) {
      const [s, e] = inputs;
      const table = kids
        .slice(s + 1, e)
        .map(tableOf)
        .find((t) => t !== undefined);
      if (table) markRequired(table);
    }

    // Output Contract: the Field Definitions table against the contract.
    const out2 = sections(kids).get('output-contract');
    const cap = loadOntology().byId.get(SKILL.exec(sourceOf(file, 'rehype-capability-skill').repoPath)![1]!)!;
    if (out2) {
      const [s, e] = out2;
      const h3 = kids.slice(s + 1, e).findIndex((c) => isEl(c, 'h3') && c.properties?.id === 'field-definitions');
      if (h3 !== -1) {
        const block = kids.slice(s + 1 + h3 + 1, e).find((c) => isEl(c) && (c.tagName === 'table' || c.tagName === 'div'));
        const table = block ? tableOf(block) : undefined;
        if (table) markFieldDefinitions(table, cap);
      }
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
        const details = groups.map(({ h3, body }): Element => {
          h3.children = h3.children.filter((c) => !(isEl(c, 'a') && ((c.properties?.className as string[]) ?? []).includes('heading-anchor')));
          const failure = /failure/i.test(text(h3));
          return {
            type: 'element',
            tagName: 'details',
            properties: { className: ['skill-example'] },
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

const el = (tagName: string, properties: Element['properties'], children: ElementContent[]): Element => ({ type: 'element', tagName, properties, children });
const txt = (value: string): ElementContent => ({ type: 'text', value });

/** Adds the "In the contract" column to a skill's Field Definitions table. */
export function markFieldDefinitions(table: Element, cap: Capability): number {
  const contract = new Map(contractRows(cap.output_schema).map((r) => [r.path, r]));
  const part = (tag: string) => table.children.find((c): c is Element => isEl(c, tag));
  const rows = (sec: Element | undefined) => (sec ? sec.children.filter((c): c is Element => isEl(c, 'tr')) : []);
  const head = rows(part('thead'))[0];
  if (!head) return 0;
  head.children.push(el('th', {}, [txt('In the contract')]));
  let marked = 0;
  for (const tr of rows(part('tbody'))) {
    const first = tr.children.find((c): c is Element => isEl(c, 'td'));
    const name = first ? text(first).replace(/`/g, '').trim() : '';
    const row = contract.get(name);
    const cell = row
      ? [
          glyphElement('check', { className: 'skill-fd__glyph' }),
          txt(' Yes: '),
          el('code', {}, [txt(row.type)]),
          txt(row.required ? ', required' : ', optional'),
        ]
      : [glyphElement('type:open', { className: 'skill-fd__glyph' }), txt(' '), txt("No, the skill's own")];
    tr.children.push(el('td', { className: ['skill-fd__contract'], dataInContract: row ? 'yes' : 'no' }, cell));
    marked += 1;
  }
  table.properties = { ...table.properties, dataEnriched: String(marked), ...(marked >= 3 ? { dataInfoFigure: 'enriched-table' } : {}) };
  return marked;
}

/** Marks the "Required" column of a skill's Inputs table with check (Yes) and cross (No) glyphs. */
export function markRequired(table: Element): number {
  const part = (tag: string) => table.children.find((c): c is Element => isEl(c, tag));
  const rows = (sec: Element | undefined) => (sec ? sec.children.filter((c): c is Element => isEl(c, 'tr')) : []);
  const cells = (tr: Element) => tr.children.filter((c): c is Element => isEl(c, 'td') || isEl(c, 'th'));
  const head = rows(part('thead'))[0];
  const at = head ? cells(head).findIndex((c) => text(c).trim() === 'Required') : -1;
  if (at === -1) return 0;
  let marked = 0;
  for (const tr of rows(part('tbody'))) {
    const c = cells(tr)[at];
    const v = c ? text(c).trim().toLowerCase() : '';
    if (!c || (v !== 'yes' && v !== 'no')) continue;
    c.children.unshift(glyphElement(v === 'yes' ? 'check' : 'close', { className: `skill-req skill-req--${v}` }), txt(' '));
    marked += 1;
  }
  if (marked > 0) table.properties = { ...table.properties, dataEnriched: String(marked), ...(marked >= 3 ? { dataInfoFigure: 'enriched-table' } : {}) };
  return marked;
}
