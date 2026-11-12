// Visual aids in the SKILL.md of an atomic capability (skills/<id>/SKILL.md
// for an ontology capability; a composed skill gets only the two folds, as
// below), keyed by the
// fixed H2s every such skill has (visual spec 3.1). The prose and the heading
// ids are not changed:
// - Procedure: the top-level ordered list gets numbered pixel tiles (CSS).
// - Inputs: the parameter table's "Required" column gets a check glyph on
//   "Yes" and a cross on "No", as yes/no columns do on prose pages (visual
//   spec 3.10.10). The glyphs repeat the column's words, so the table is a
//   glyph aid and not an information figure.
// - Examples: each "### Example N" and the content up to the next H3 or H2
//   becomes a <details> whose summary holds the heading with the code glyph
//   (caution for a title that contains "Failure"). The
//   heading's hidden anchor link is dropped, so the summary holds no link.
//   The first example starts open and the others closed (visual spec 3.1), so
//   a reader sees one worked example without a click and the summaries list
//   the rest. When the open example's fence alone is taller than a screen,
//   the run it makes is exempt (category b, spec 3.12).
// - Safety Constraints: the section's content sits in a panel with the
//   caution glyph.
// - Output Contract: the section's first code block folds into a
//   <details>, and the Field Definitions table gets a column with what the
//   ontology's output contract says of each top-level field: a filled pin
//   when it requires the field, an outlined pin when the field is optional,
//   and a cross when the field is the skill's own. The skill's table does not
//   say this, so the table is an information figure (visual spec 4.2); the
//   page's sentence above it (F-C6) counts them and names any contract field
//   the skill leaves out.
// The port columns and the composition chain are Astro figures, which the
// page puts under their headings.
//
// A composed skill (skills/<dir>/SKILL.md in COMPOSED_SKILLS) gets only the
// two folds: its Output Contract fence and each example closed under a
// summary, since its contract and example output are long YAML (the longest
// run on the site was one composed skill's open example). Its other sections
// are left as written.
import type { Element, ElementContent, Root, RootContent } from 'hast';
import { loadOntology, type Capability } from '../data/ontology';
import { COMPOSED_SKILLS } from '../data/skills';
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

/** True when the hast file is the SKILL.md of a composed skill. */
export function isComposedSkill(repoPath: string): boolean {
  const m = /^skills\/([a-z0-9_-]+)\/SKILL\.md$/.exec(repoPath);
  return m !== null && m[1]! in COMPOSED_SKILLS;
}

export default function rehypeCapabilitySkill() {
  return (tree: Root, file: Parameters<typeof sourceOf>[0]): void => {
    if (!file.path || !/[\\/]skills[\\/][a-z0-9_-]+[\\/]SKILL\.md$/.test(file.path)) return;
    const repoPath = sourceOf(file, 'rehype-capability-skill').repoPath;
    const kids = tree.children;
    if (isComposedSkill(repoPath)) {
      foldOutputFence(kids);
      foldExamples(kids);
      return;
    }
    if (!isCapabilitySkill(repoPath)) return;

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
    // because the page marks its fields in the Field Definitions table and
    // counts them in the sentence above it.
    const output = sections(kids).get('output-contract');
    if (output) {
      foldOutputFence(kids);
      const cap = loadOntology().byId.get(SKILL.exec(repoPath)![1]!)!;
      const [s2, e2] = sections(kids).get('output-contract')!;
      const table = kids
        .slice(s2 + 1, e2)
        .map(tableOf)
        .find((t) => t !== undefined);
      if (table) markContract(table, cap);
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

    // Examples: one <details> per H3, the first one open.
    foldExamples(kids, true);
  };
}

const txt = (value: string): ElementContent => ({ type: 'text', value });

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
  // The glyphs repeat the column's Yes and No, so the table is a glyph aid,
  // not an information figure (issue #125 review).
  if (marked > 0) table.properties = { ...table.properties, dataEnriched: String(marked) };
  return marked;
}

/** Rows a table must mark before it counts as an information figure (visual spec 4.2). */
const CONTRACT_MIN_ROWS = 3;

/**
 * Adds an "In the output contract" column to a skill's Field Definitions
 * table: for each top-level field, a filled pin and "required" or an
 * outlined pin and "optional" when the ontology's output contract declares
 * it, and a cross and "no, the skill's own" when it does not. A nested path
 * (`result.<store_as>`, `data[].key`) gets an empty cell. Returns the rows
 * marked.
 */
export function markContract(table: Element, cap: Capability): number {
  const part = (tag: string) => table.children.find((c): c is Element => isEl(c, tag));
  const rows = (sec: Element | undefined) => (sec ? sec.children.filter((c): c is Element => isEl(c, 'tr')) : []);
  const cells = (tr: Element) => tr.children.filter((c): c is Element => isEl(c, 'td') || isEl(c, 'th'));
  const head = rows(part('thead'))[0];
  if (!head || text(cells(head)[0]!).trim() !== 'Field') return 0;
  const contract = new Map(contractRows(cap.output_schema).filter((r) => r.depth === 0).map((r) => [r.name, r.required]));
  const body = rows(part('tbody'));
  // 'required' | 'optional' | 'own', or null for a nested path.
  const marks = body.map((tr) => {
    const name = text(cells(tr)[0]!).replace(/`/g, '').trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) return null;
    const req = contract.get(name);
    return req === undefined ? 'own' : req ? 'required' : 'optional';
  });
  if (marks.filter((m) => m !== null).length < CONTRACT_MIN_ROWS) return 0;
  head.children.push({ type: 'element', tagName: 'th', properties: {}, children: [txt('In the output contract')] });
  body.forEach((tr, i) => {
    const m = marks[i];
    tr.children.push({
      type: 'element',
      tagName: 'td',
      properties: { className: ['skill-contract-cell'] },
      children:
        m === null
          ? []
          : m === 'own'
            ? [glyphElement('close', { className: 'skill-contract-own' }), txt(" no, the skill's own")]
            : [{ type: 'element', tagName: 'span', properties: { className: ['skill-contract', `skill-contract--${m}`], ariaHidden: 'true' }, children: [] }, txt(` ${m}`)],
    });
  });
  const marked = marks.filter((m) => m !== null).length;
  table.properties = { ...table.properties, dataEnriched: String(marked), dataInfoFigure: 'enriched-table' };
  return marked;
}

/** Folds the first code block of the Output Contract section under a summary. */
function foldOutputFence(kids: RootContent[]): void {
  const output = sections(kids).get('output-contract');
  if (!output) return;
  const [s, e] = output;
  const at = kids.slice(s + 1, e).findIndex((c) => isEl(c, 'pre'));
  if (at === -1) return;
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

/**
 * Each "### Example" of the Examples section and its content up to the next H3
 * or H2 becomes a <details>; all closed, or the first open when `openFirst`.
 */
function foldExamples(kids: RootContent[], openFirst = false): void {
  const ex = sections(kids).get('examples');
  if (!ex) return;
  const [s, e] = ex;
  const part = kids.slice(s + 1, e);
  const before: RootContent[] = [];
  const groups: { h3: Element; body: RootContent[] }[] = [];
  for (const c of part) {
    if (isEl(c, 'h3')) groups.push({ h3: c, body: [] });
    else if (groups.length === 0) before.push(c);
    else groups.at(-1)!.body.push(c);
  }
  if (groups.length === 0) return;
  // A thematic break that ended an example in the Markdown ("---" between
  // examples) is dropped: each example is its own panel, so a rule at the
  // foot of an open one only adds height.
  for (const g of groups) {
    while (g.body.length > 0) {
      const last = g.body.at(-1)!;
      if ((last.type === 'text' && last.value.trim() === '') || isEl(last, 'hr')) g.body.pop();
      else break;
    }
  }
  const details = groups.map(({ h3, body }, n): Element => {
    h3.children = h3.children.filter((c) => !(isEl(c, 'a') && ((c.properties?.className as string[]) ?? []).includes('heading-anchor')));
    const failure = /failure/i.test(text(h3));
    return {
      type: 'element',
      tagName: 'details',
      properties: { className: ['skill-example'], ...(openFirst && n === 0 ? { open: true } : {}) },
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
