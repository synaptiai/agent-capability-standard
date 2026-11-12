// Figures drawn into prose pages, RFCs and skill pages from what the Markdown
// already holds (visual spec 3.10). Nothing here changes the source text: each
// mark sits beside the words it is drawn from, and the words stay.
//
// - Box diagrams (3.10.4): a plain or `text` fence with at least two lines of
//   box-drawing characters or tree connectors is framed as a figure with the
//   eyebrow "Diagram" and the name "Diagram: {heading}". The text is its own
//   text equivalent.
// - Pattern fences (3.10.9): a YAML fence with a `capabilities:` list gets a
//   chain of capability tiles above it, in the order of its `flow:` lines
//   (`N. cap(args) → out`) when it has them, each arrow named by the output it
//   passes on. A fence that a mermaid figure already draws (the next block) is
//   left alone, and a fence naming an id the ontology lacks is skipped and
//   reported on the console, not failed.
// - Enriched tables (3.10.11): a number column gets a pixel bar per row on one
//   scale; a yes/no or ✓/— column gets check and cross glyphs; a Risk column
//   gets pips; a capability column (an id, or an id and its parameters in
//   parentheses) gets a 24px tile; a coverage grid whose
//   cells list `domain:` values gets a count badge per cell. The cell text
//   stays; the marks are aria-hidden or carry their own words.
// - Workflow cells (3.10.10): a cell holding only a backticked workflow id gets
//   a 10px step strip after it.
// - Capability chains (3.10.8): a cell made only of capability ids joined by →
//   becomes a row of tiles, the text kept as visually hidden words.
// - RFC pages (3.10.12): the "Goals" and "Non-goals" H2s start with a check
//   and a cross glyph, aria-hidden, so the headings and their ids read as before.
// - F-O1 (3.10.14): on the OASF safety proposal, under "4.1", the OASF
//   categories and the capabilities each maps to, from the mapping file.
// - The release notes (CHANGELOG.md): see release-figures-hast.ts.
// - Figures are numbered "Fig n" in page order, mermaid figures included.
//
// It runs on prose, RFC and skill pages only; the Standard and the generated
// pages draw their own figures.
import type { Element, ElementContent, Root, RootContent } from 'hast';
import type { VFile } from 'vfile';
import { loadOasfMapping, OASF_MAPPING_TYPES, type OasfMappingType } from '../data/oasf';
import { loadOntology } from '../data/ontology';
import { loadWorkflows } from '../data/workflows';
import { workflowHref } from '../lib/generated';
import { routeForSource } from '../lib/routes';
import { diagramSteps } from '../lib/views';
import { glyphElement, miniTileElement, pixelBarElement } from '../pixel/hast';
import { readRepoFile } from '../lib/repo';
import { drawReleaseFigures, RELEASE_NOTES_SOURCE } from './release-figures-hast';
import { sourceOf } from './source';

const PLUGIN = 'rehype-prose-figures';

/** Templates whose Markdown this plugin draws into. */
export const PROSE_TEMPLATES: ReadonlySet<string> = new Set(['prose', 'rfc', 'skill']);

/** The source whose section "4.1" gets figure F-O1. */
export const OASF_PROPOSAL = 'docs/proposals/OASF_SAFETY_EXTENSIONS.md';
/** The heading F-O1 is placed under, by the start of its text. */
export const OASF_ANCHOR = '4.1 ';

// ---------- small hast helpers ----------

const el = (tagName: string, properties: Element['properties'], children: ElementContent[] = []): Element => ({
  type: 'element',
  tagName,
  properties,
  children,
});
const text = (value: string): ElementContent => ({ type: 'text', value });

const isEl = (n: unknown, tag?: string): n is Element =>
  typeof n === 'object' && n !== null && (n as Element).type === 'element' && (tag === undefined || (n as Element).tagName === tag);

const classes = (e: Element): string[] => {
  const c = e.properties?.className;
  return Array.isArray(c) ? c.map(String) : [];
};

/** All text of a node, aria-hidden parts included. */
export function textOf(n: ElementContent | Root | RootContent): string {
  if (n.type === 'text') return n.value;
  if (n.type !== 'element' && n.type !== 'root') return '';
  return (n.children as ElementContent[]).map(textOf).join('');
}

const HEADING = /^h[1-6]$/;

// ---------- box diagrams ----------

const BOX = /[─-╿]/;
const TREE = /^\s*(├──|└──|│)/;

/** A fence is a box diagram when two or more of its lines draw boxes or tree branches (3.10.4). */
export function isBoxDiagram(code: string): boolean {
  return code.split('\n').filter((l) => BOX.test(l) || TREE.test(l)).length >= 2;
}

function preLanguage(pre: Element): string | null {
  const lang = pre.properties?.dataLanguage;
  return typeof lang === 'string' ? lang : null;
}

function boxFigure(pre: Element, heading: string): Element {
  const name = heading ? `Diagram: ${heading}` : 'Diagram';
  return el('figure', { className: ['fig', 'fig-ascii'], ariaLabel: name, dataFigKind: 'ascii' }, [
    el('p', { className: ['fig__eyebrow'], ariaHidden: 'true' }, [text('Diagram')]),
    pre,
  ]);
}

// ---------- directory trees (3.10.5) ----------

export interface DirNode {
  name: string;
  comment: string | null;
  children: DirNode[];
}

/**
 * A fence whose lines after an optional root line are all tree branches
 * ("├── name  # comment", indented by "│   " or four spaces per level) and
 * which names at least one directory (a name ending "/") is a directory
 * tree. A decision tree (a branch with "→") is not one. Returns the root, or
 * null when the fence is not a directory tree.
 */
export function directoryTree(code: string): DirNode | null {
  const lines = code.split('\n').filter((l) => l.trim() !== '');
  if (lines.length < 3 || lines.some((l) => l.includes('→'))) return null;
  const split = (s: string): { name: string; comment: string | null } => {
    const m = /^(.*?)\s+#\s*(.*)$/.exec(s);
    return m ? { name: m[1]!.trim(), comment: m[2]!.trim() || null } : { name: s.trim(), comment: null };
  };
  const BRANCH = /^((?:│   |│\u00a0\u00a0 |    )*)(?:├── |└── )(.+)$/;
  const first = BRANCH.test(lines[0]!) ? null : split(lines[0]!);
  const root: DirNode = { name: first?.name ?? '', comment: first?.comment ?? null, children: [] };
  const stack: { depth: number; node: DirNode }[] = [{ depth: 0, node: root }];
  for (const l of lines.slice(first ? 1 : 0)) {
    const m = BRANCH.exec(l);
    if (!m) return null;
    const depth = m[1]!.length / 4 + 1;
    const node: DirNode = { ...split(m[2]!), children: [] };
    while (stack.length > 1 && stack.at(-1)!.depth >= depth) stack.pop();
    if (stack.at(-1)!.depth !== depth - 1) return null;
    stack.at(-1)!.node.children.push(node);
    stack.push({ depth, node });
  }
  const dirs = (n: DirNode): number => (n.name.endsWith('/') ? 1 : 0) + n.children.reduce((a, c) => a + dirs(c), 0);
  return dirs(root) > 0 ? root : null;
}

function treeItems(nodes: DirNode[]): Element {
  return el(
    'ul',
    { className: ['dir-tree'] },
    nodes.map((n) =>
      el('li', { className: ['dir-tree__item'] }, [
        el('span', { className: ['dir-tree__row'] }, [
          ...(n.name.endsWith('/') ? [glyphElement('folder', { className: 'dir-tree__glyph' })] : []),
          el('code', { className: ['dir-tree__name'] }, [text(n.name)]),
          ...(n.comment ? [el('span', { className: ['dir-tree__note'] }, [text(n.comment)])] : []),
        ]),
        ...(n.children.length > 0 ? [treeItems(n.children)] : []),
      ]),
    ),
  );
}

/** The directory tree's caption: what it holds, counted from the parse. */
export function directoryCaption(root: DirNode): string {
  const all: DirNode[] = [];
  const walk = (n: DirNode) => n.children.forEach((c) => (all.push(c), walk(c)));
  walk(root);
  const dirs = all.filter((n) => n.name.endsWith('/')).length;
  const top = root.children.length;
  return `${top} top-level entries${root.name ? ` in ${root.name}` : ''} and ${dirs} directories in all, each marked with the folder glyph; the text after a name is the source's comment on it.`;
}

function treeFigure(pre: Element, root: DirNode, heading: string, id: string): Element {
  const f = figureFrame(id, heading ? `Directory tree: ${heading}` : 'Directory tree', directoryCaption(root), 'directory-tree', [
    ...(root.name ? [el('p', { className: ['dir-tree__root'] }, [glyphElement('folder', { className: 'dir-tree__glyph' }), el('code', {}, [text(root.name)])])] : []),
    treeItems(root.children),
  ]);
  f.children.push(el('details', { className: ['fig-details'] }, [el('summary', {}, [text('Text version')]), pre]));
  return f;
}

// ---------- pattern fences ----------

export interface PatternChain {
  name: string;
  /** Capability ids in drawing order. */
  ids: string[];
  /** Output name after each id (from the flow lines), or null. */
  outputs: (string | null)[];
  /**
   * The arguments of each flow line that no earlier line outputs: what the
   * step takes from outside the chain. Empty lists when not from flow lines.
   */
  inputs: string[][];
  fromFlow: boolean;
}

/**
 * Read a pattern fence: its first key is the pattern's name, its
 * `capabilities:` list the ids, and its `flow:` lines the order and outputs.
 * Returns null when the fence has no capabilities list.
 */
export function patternChain(code: string): PatternChain | null {
  const lines = code.split('\n');
  const name = /^([A-Za-z_][\w-]*):\s*$/.exec(lines.find((l) => l.trim() !== '' && !l.trim().startsWith('#')) ?? '')?.[1] ?? null;
  const at = lines.findIndex((l) => /^\s*capabilities:\s*(\[.*\])?\s*(#.*)?$/.test(l));
  if (at === -1 || name === null) return null;
  let ids: string[] = [];
  const inline = /^\s*capabilities:\s*\[(.*)\]/.exec(lines[at]!);
  if (inline) ids = inline[1]!.split(',').map((s) => s.trim()).filter(Boolean);
  else {
    for (const l of lines.slice(at + 1)) {
      const m = /^\s+-\s+([A-Za-z_][\w-]*)\s*(#.*)?$/.exec(l);
      if (!m) break;
      ids.push(m[1]!);
    }
  }
  if (ids.length < 2) return null;
  const flow = lines
    .map((l) => /^\s*\d+\.\s+([A-Za-z_][\w-]*)\((.*)\)\s*→\s*(\S+)\s*$/.exec(l))
    .filter((m): m is RegExpExecArray => m !== null)
    .map((m) => ({ id: m[1]!, args: argNames(m[2]!), out: m[3]!.replace(/\[\]$/, '') }));
  const listed = new Set(ids);
  if (flow.length > 0 && flow.every((f) => listed.has(f.id))) {
    const seen = new Set<string>();
    const inputs = flow.map((f) => {
      const outside = f.args.filter((a) => !seen.has(a));
      seen.add(f.out);
      return outside;
    });
    return { name, ids: flow.map((f) => f.id), outputs: flow.map((f) => f.out), inputs, fromFlow: true };
  }
  return { name, ids, outputs: ids.map(() => null), inputs: ids.map(() => []), fromFlow: false };
}

/**
 * The plain names among a flow line's arguments (`detect(current_state,
 * anomaly_patterns)`), with a trailing `[]` dropped; quoted or nested
 * arguments are left out.
 */
function argNames(args: string): string[] {
  return args
    .split(',')
    .map((a) => a.trim().replace(/\[\]$/, ''))
    .filter((a) => /^[A-Za-z_][\w.]*$/.test(a));
}

const WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve'];
const count = (n: number) => WORDS[n] ?? String(n);
const cap1 = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function chainCaption(c: PatternChain): string {
  const ends = `from ${c.ids[0]} to ${c.ids.at(-1)}`;
  return c.fromFlow
    ? `${cap1(count(c.ids.length))} steps in flow order, ${ends}; each arrow names the output passed on${
        c.inputs.some((i) => i.length > 0) ? ', and "in:" under a step names the inputs it takes from outside the chain' : ''
      }.`
    : `${cap1(count(c.ids.length))} capabilities in the order the pattern lists them, ${ends}.`;
}

function chainFigure(c: PatternChain, id: string): Element {
  const items: ElementContent[] = c.ids.map((cap, i) => {
    const kids: ElementContent[] = [];
    if (i > 0) {
      const out = c.outputs[i - 1];
      kids.push(
        el('span', { className: ['prose-chain__arrow'] }, [
          glyphElement('chevron-right', { className: 'prose-chain__chevron' }),
          ...(out ? [el('span', { className: ['prose-chain__out'] }, [text(out)])] : []),
        ]),
      );
    }
    kids.push(
      el('span', { className: ['prose-chain__node'] }, [
        miniTileElement(cap, { size: 32 }),
        el('code', { className: ['prose-chain__id'], ariaHidden: 'true' }, [text(cap)]),
        ...(c.inputs[i]!.length > 0
          ? [el('span', { className: ['prose-chain__in'] }, [el('span', { className: ['visually-hidden'] }, [text(`${cap} also takes `)]), el('span', { ariaHidden: 'true' }, [text('in: ')]), text(c.inputs[i]!.join(', '))])]
          : []),
      ]),
    );
    return el('li', { className: ['prose-chain__item'] }, kids);
  });
  const last = c.outputs.at(-1);
  if (last) {
    items.push(
      el('li', { className: ['prose-chain__item', 'prose-chain__item--end'] }, [
        el('span', { className: ['prose-chain__arrow'] }, [
          glyphElement('chevron-right', { className: 'prose-chain__chevron' }),
          el('span', { className: ['prose-chain__out'] }, [text(last)]),
        ]),
      ]),
    );
  }
  return figureFrame(id, `The ${c.name} pattern as a chain`, chainCaption(c), 'pattern-chain', [
    el('ol', { className: ['prose-chain'], ariaLabel: `${c.name}: ${c.ids.join(', ')}` }, items),
  ]);
}

function figureFrame(id: string, title: string, caption: string, kind: string, drawing: ElementContent[]): Element {
  return el('figure', { className: ['fig', 'fig-prose'], id, ariaLabelledBy: [`${id}-title`], dataFigKind: kind }, [
    el('p', { className: ['fig__eyebrow'], ariaHidden: 'true' }, [text('Fig')]),
    el('p', { className: ['fig__title'], id: `${id}-title` }, [text(title)]),
    el('div', { className: ['fig__drawing'] }, drawing),
    el('figcaption', { className: ['fig__caption'] }, [text(caption)]),
  ]);
}

// ---------- tables ----------

function rowsOf(table: Element, part: 'thead' | 'tbody'): Element[] {
  const sec = table.children.find((c): c is Element => isEl(c, part));
  return sec ? sec.children.filter((c): c is Element => isEl(c, 'tr')) : [];
}

function cellsOf(tr: Element): Element[] {
  return tr.children.filter((c): c is Element => isEl(c, 'td') || isEl(c, 'th'));
}

const clean = (s: string) => s.replace(/\*\*/g, '').replace(/\s+/g, ' ').trim();

/** Header words that name an identifier or an order rather than a quantity. */
const NOT_A_QUANTITY = /^(id|#|no\.?|step|version|v|clause|article|annex|level|phase|priority|year|code|codes|section|tier|order|rank|category|layer|port|line|lines|page|rfc|date)$/i;

/** True when every cell is a count; values come back as numbers. */
export function numberColumn(header: string, cells: string[]): { values: number[]; fraction: boolean } | null {
  if (NOT_A_QUANTITY.test(clean(header))) return null;
  const vals = cells.map((c) => clean(c));
  if (vals.length < 3) return null;
  if (vals.every((v) => /^(0(\.\d+)?|1(\.0+)?)$/.test(v)) && vals.some((v) => v.includes('.'))) {
    const values = vals.map(Number);
    return new Set(values).size > 1 ? { values, fraction: true } : null;
  }
  if (vals.every((v) => /^\d{1,4}$/.test(v))) {
    const values = vals.map(Number);
    return new Set(values).size > 1 && Math.max(...values) > 0 ? { values, fraction: false } : null;
  }
  return null;
}

export type YesNo = 'yes' | 'no' | 'partial';

export function yesNo(v: string): YesNo | null {
  const t = clean(v);
  if (/^(✓|✔|✅|yes\b)/i.test(t)) return 'yes';
  if (/^(—|–|-|✗|✘|❌)$/.test(t) || /^no\b/i.test(t)) return 'no';
  if (/^partial\b/i.test(t)) return 'partial';
  return null;
}

/** A yes/no column: every cell reads yes, no or partial, with at least one yes and one no. */
export function yesNoColumn(cells: string[]): YesNo[] | null {
  if (cells.length < 2) return null;
  const v = cells.map(yesNo);
  if (v.some((x) => x === null)) return null;
  return v.includes('yes') && v.includes('no') ? (v as YesNo[]) : null;
}

const RISK_LEVEL = /^`?(low|medium|high)`?$/i;

export function riskColumn(header: string, cells: string[]): ('low' | 'medium' | 'high' | null)[] | null {
  if (!/risk/i.test(clean(header))) return null;
  const v = cells.map((c) => {
    const t = clean(c);
    const m = RISK_LEVEL.exec(t);
    return m ? (m[1]!.toLowerCase() as 'low' | 'medium' | 'high') : /^(varies|—|-|n\/a)$/i.test(t) ? null : undefined;
  });
  if (v.some((x) => x === undefined)) return null;
  return v.filter((x) => x !== null).length >= 2 ? (v as ('low' | 'medium' | 'high' | null)[]) : null;
}

/** The capability id a cell holds alone (in code or bold or plain), or null. */
/**
 * The capability a cell names: a capability id alone, or an id followed by
 * its parameters in parentheses (`attribute` (domain: dependencies),
 * `invoke` (workflow_id: x), as a step table writes them).
 */
function capabilityCell(cell: Element): string | null {
  const m = /^`?([a-z_]+)`?(?:\s*\([^()]*\))?$/.exec(clean(textOf(cell)));
  return m && loadOntology().byId.has(m[1]!) ? m[1]! : null;
}

/** The capability ids of a cell made only of ids joined by → (3.10.8), or null. */
export function capabilityChain(t: string): string[] | null {
  const parts = clean(t).split(/\s*→\s*/);
  if (parts.length < 2) return null;
  const ids = parts.map((p) => p.replace(/^`|`$/g, ''));
  return ids.every((id) => loadOntology().byId.has(id)) ? ids : null;
}

function riskPips(level: 'low' | 'medium' | 'high'): Element {
  const n = { low: 1, medium: 2, high: 3 }[level];
  return el(
    'span',
    { className: ['risk-pips', 'prose-risk'], dataLevel: n, dataRisk: level, ariaHidden: 'true' },
    Array.from({ length: n }, () => el('span', { className: ['risk-pips__pip'] })),
  );
}

/** Domain values a coverage-grid cell lists. */
export function domainValues(t: string): number {
  return [...t.matchAll(/\bdomain:\s*[\w.*-]+/g)].length;
}

function heatBadge(n: number, label: string): Element {
  const step = Math.min(4, n);
  return el('span', { className: ['heat-badge', `heat-badge--${step}`], dataCount: n }, [
    el('span', { ariaHidden: 'true' }, [text(String(n))]),
    el('span', { className: ['visually-hidden'] }, [text(label)]),
  ]);
}

function stepStripElement(id: string): Element | null {
  const wf = loadWorkflows().byId.get(id);
  if (!wf) return null;
  const steps = diagramSteps(wf);
  return el(
    'a',
    {
      className: ['step-strip', 'step-strip--10', 'prose-strip'],
      href: workflowHref(id),
      ariaLabel: `${id}: ${steps.length} ${steps.length === 1 ? 'step' : 'steps'}`,
      dataWorkflow: id,
      dataSteps: steps.length,
    },
    steps.map((d) => {
      const gated = (d.step.gates?.length ?? 0) > 0;
      return el(
        'span',
        {
          className: ['step-strip__step', d.role === 'plain' ? 'step-strip__step--plain' : 'step-strip__step--role', ...(gated ? ['step-strip__step--gate'] : [])],
          ariaHidden: 'true',
          dataRole: d.role,
        },
        d.role === 'plain' ? [] : [glyphElement(`role:${d.role}`, { scale: 1 })],
      );
    }),
  );
}

/** Marks added to one table; the number of rows that carry a mark. */
function enrichTable(table: Element): number {
  const head = rowsOf(table, 'thead')[0];
  const body = rowsOf(table, 'tbody');
  if (!head || body.length === 0) return 0;
  const headers = cellsOf(head).map((c) => clean(textOf(c)));
  const marked = new Set<number>();
  const col = (i: number) => body.map((tr) => cellsOf(tr)[i]);

  // A "Total" row is a sum, not a row of the scale.
  const isTotal = (tr: Element) => /^total\b/i.test(clean(textOf(cellsOf(tr)[0] ?? el('td', {}))));
  const scaleRows = body.filter((tr) => !isTotal(tr));

  // Coverage grid: half or more of the data cells list domain: values.
  const data = body.flatMap((tr) => cellsOf(tr).slice(1));
  const withDomains = data.filter((c) => domainValues(textOf(c)) > 0);
  const coverage = headers.length >= 4 && data.length > 0 && withDomains.length * 2 >= data.length;
  if (coverage) {
    const firstCaps = body.map((tr) => capabilityCell(cellsOf(tr)[0]!));
    if (firstCaps.every((c) => c !== null)) {
      body.forEach((tr, r) => {
        const c = cellsOf(tr)[0]!;
        c.children.unshift(miniTileElement(firstCaps[r]!, { size: 24, link: !c.children.some((k) => isEl(k, 'a')) }));
        c.properties = { ...c.properties, className: [...classes(c), 'prose-cap-cell'] };
      });
    }
    body.forEach((tr, r) => {
      const cells = cellsOf(tr);
      const rowName = clean(textOf(cells[0]!));
      cells.slice(1).forEach((cell, j) => {
        const n = domainValues(textOf(cell));
        if (n === 0) return;
        cell.children.unshift(heatBadge(n, `${n} ${n === 1 ? 'domain' : 'domains'} for ${rowName}, ${headers[j + 1]}:`));
        marked.add(r);
      });
    });
    table.properties = { ...table.properties, dataEnriched: 'coverage', ...infoFigure(marked.size) };
    return marked.size;
  }

  // The first column names the row: it gets tiles, chains and strips, never bars, pips or checks.
  headers.forEach((h, i) => {
    const cells = col(i);
    if (cells.some((c) => c === undefined)) return;
    const texts = cells.map((c) => textOf(c!));

    // Capability column: every cell holds a capability id alone.
    const caps = cells.map((c) => capabilityCell(c!));
    if (caps.every((c, r) => c !== null || isTotal(body[r]!)) && caps.some((c) => c !== null)) {
      cells.forEach((c, r) => {
        if (caps[r] === null) return;
        const linked = c!.children.some((k) => isEl(k, 'a'));
        c!.children.unshift(miniTileElement(caps[r]!, { size: 24, link: !linked }));
        c!.properties = { ...c!.properties, className: [...classes(c!), 'prose-cap-cell'] };
        marked.add(r);
      });
      return;
    }
    // Capability chains: cells made only of ids joined by →.
    const chains = texts.map(capabilityChain);
    if (chains.filter(Boolean).length >= 2) {
      cells.forEach((c, r) => {
        const ids = chains[r];
        if (!ids) return;
        const words = textOf(c!);
        const row: ElementContent[] = [];
        ids.forEach((id, k) => {
          if (k > 0) row.push(glyphElement('chevron-right', { className: 'prose-chain__chevron' }));
          row.push(miniTileElement(id, { size: 24, link: false }));
        });
        c!.children = [
          el('span', { className: ['prose-cell-chain'], ariaHidden: 'true' }, row),
          el('span', { className: ['visually-hidden'] }, [text(words)]),
        ];
        marked.add(r);
      });
      return;
    }
    // Workflow ids: a backticked id the catalog knows.
    const wfs = cells.map((c) => {
      const kids = c!.children.filter((k) => !(k.type === 'text' && k.value.trim() === ''));
      return kids.length === 1 && isEl(kids[0], 'code') && loadWorkflows().byId.has(textOf(kids[0]!)) ? textOf(kids[0]!) : null;
    });
    if (wfs.filter(Boolean).length >= 2) {
      cells.forEach((c, r) => {
        const strip = wfs[r] ? stepStripElement(wfs[r]!) : null;
        if (!strip) return;
        c!.children.push(strip);
        c!.properties = { ...c!.properties, className: [...classes(c!), 'prose-wf-cell'] };
        marked.add(r);
      });
      return;
    }
    if (i === 0) return;
    // Risk column.
    const risks = riskColumn(h, texts);
    if (risks) {
      cells.forEach((c, r) => {
        const lv = risks[r];
        if (!lv) return;
        c!.children.unshift(riskPips(lv), text(' '));
        c!.properties = { ...c!.properties, className: [...classes(c!), 'prose-risk-cell'] };
        marked.add(r);
      });
      return;
    }
    // Yes/no column; a Total row keeps its text only.
    const yn = yesNoColumn(cells.flatMap((c, r) => (isTotal(body[r]!) ? [] : [textOf(c!)])));
    if (yn) {
      let k = 0;
      cells.forEach((c, r) => {
        if (isTotal(body[r]!)) return;
        const v = yn[k++]!;
        if (v === 'partial') return;
        c!.children.unshift(glyphElement(v === 'yes' ? 'check' : 'close', { className: `prose-yn prose-yn--${v}` }), text(' '));
        marked.add(r);
      });
      return;
    }
    // Number column, on one scale; a Total row keeps its text only.
    const scaleCells = scaleRows.map((tr) => cellsOf(tr)[i]);
    if (scaleCells.some((c) => c === undefined)) return;
    const nums = numberColumn(h, scaleCells.map((c) => textOf(c!)));
    if (nums) {
      const max = nums.fraction ? 1 : Math.max(...nums.values);
      scaleRows.forEach((tr, k) => {
        const c = cellsOf(tr)[i]!;
        c.children = [pixelBarElement(nums.values[k]!, max, { label: clean(textOf(c)) })];
        c.properties = { ...c.properties, className: [...classes(c), 'prose-bar-cell'] };
        marked.add(body.indexOf(tr));
      });
    }
  });
  if (marked.size > 0) table.properties = { ...table.properties, dataEnriched: String(marked.size), ...infoFigure(marked.size) };
  return marked.size;
}

/**
 * Visual spec 4.2: an enriched table is an information figure when at least
 * three of its rows carry bars, pips, check glyphs, tiles or heat badges. The
 * figure-gap check (src/lib/runs.ts) counts elements with data-info-figure.
 */
export const ENRICHED_TABLE_MIN_ROWS = 3;
function infoFigure(rows: number): { dataInfoFigure?: string } {
  return rows >= ENRICHED_TABLE_MIN_ROWS ? { dataInfoFigure: 'enriched-table' } : {};
}

// ---------- F-O1 ----------

const MAPPING_GLYPH: Record<OasfMappingType, string> = {
  direct: 'map:direct',
  domain: 'map:domain',
  composition: 'map:composition',
  workflow: 'map:workflow',
  ga_extension: 'map:ga_extension',
};

export const MAPPING_WORDS: Record<OasfMappingType, string> = {
  direct: 'direct',
  domain: 'domain',
  composition: 'composition',
  workflow: 'workflow',
  ga_extension: 'GA extension',
};

export function oasfCaption(): string {
  const m = loadOasfMapping();
  const by = OASF_MAPPING_TYPES.map((t) => [t, m.rows.filter((r) => r.mappingType === t).length] as const).filter(([, n]) => n > 0);
  const parts = by.map(([t, n]) => `${n} ${MAPPING_WORDS[t]}`);
  return `${m.rows.length} rows: ${m.categories} OASF categories and ${m.rows.length - m.categories} GA extensions; by mapping type, ${parts.slice(0, -1).join(', ')} and ${parts.at(-1)}.`;
}

function oasfFigure(id: string): Element {
  const m = loadOasfMapping();
  const rows = m.rows.map((r) =>
    el('tr', { dataMapping: r.mappingType }, [
      el('th', { scope: 'row' }, [el('span', { className: ['oasf-map__code'] }, [text(r.code)]), text(' '), text(r.name)]),
      el('td', { className: ['oasf-map__type'] }, [glyphElement(MAPPING_GLYPH[r.mappingType]), text(` ${MAPPING_WORDS[r.mappingType]}`)]),
      el('td', {}, [
        el('span', { className: ['oasf-map__tiles'] }, r.capabilities.map((c) => miniTileElement(c, { size: 24 }))),
      ]),
    ]),
  );
  const table = el('table', { className: ['oasf-map'] }, [
    el('thead', {}, [el('tr', {}, [el('th', { scope: 'col' }, [text('OASF category')]), el('th', { scope: 'col' }, [text('Mapping')]), el('th', { scope: 'col' }, [text('Capabilities')])])]),
    el('tbody', {}, rows),
  ]);
  return figureFrame(id, 'OASF categories mapped to capabilities', oasfCaption(), 'oasf-map', [
    el('div', { className: ['table-wrap'], role: 'region', tabIndex: 0, ariaLabel: 'Table: OASF categories mapped to capabilities' }, [table]),
  ]);
}

// ---------- numbering ----------

/** Number every figure of the page "Fig n" in document order; returns the count. */
export function numberFigures(tree: Root): number {
  let n = 0;
  const walk = (node: Root | Element) => {
    for (const c of node.children) {
      if (!isEl(c)) continue;
      if (c.tagName === 'figure' && classes(c).includes('fig')) {
        n += 1;
        const eyebrow = c.children.find((k): k is Element => isEl(k, 'p') && classes(k).some((x) => x === 'fig__eyebrow' || x === 'fig-mermaid__eyebrow'));
        if (eyebrow) eyebrow.children = [text(`Fig ${n}`)];
        continue;
      }
      walk(c);
    }
  };
  walk(tree);
  return n;
}

// ---------- the plugin ----------

export interface ProseFigureReport {
  ascii: number;
  chains: number;
  tables: number;
  skipped: string[];
}

/** RFC H2s that get a glyph before their text (3.10.12). */
export const RFC_HEADING_GLYPHS: Readonly<Record<string, string>> = { Goals: 'check', 'Non-goals': 'close' };

export function drawProseFigures(tree: Root, repoPath: string, template = 'prose'): ProseFigureReport {
  const report: ProseFigureReport = { ascii: 0, chains: 0, tables: 0, skipped: [] };
  const ids = new Set<string>();
  const uid = (base: string) => {
    let id = base;
    for (let k = 2; ids.has(id); k++) id = `${base}-${k}`;
    ids.add(id);
    return id;
  };
  let heading = '';
  const kids = tree.children;
  for (let i = 0; i < kids.length; i++) {
    const node = kids[i]!;
    if (!isEl(node)) continue;
    if (HEADING.test(node.tagName)) {
      heading = textOf(node).replace(/\s+/g, ' ').trim();
      const g = template === 'rfc' && node.tagName === 'h2' ? RFC_HEADING_GLYPHS[heading] : undefined;
      if (g) node.children.unshift(glyphElement(g, { scale: 3, className: 'rfc-heading-glyph' }));
      if (repoPath === OASF_PROPOSAL && node.tagName === 'h3' && heading.startsWith(OASF_ANCHOR)) {
        kids.splice(i + 1, 0, oasfFigure(uid('ref-fig-oasf-map')));
        i += 1;
      }
      continue;
    }
    if (node.tagName === 'pre') {
      const lang = preLanguage(node);
      const code = textOf(node);
      if ((lang === 'plaintext' || lang === 'text') && isBoxDiagram(code)) {
        const dir = directoryTree(code);
        if (dir) {
          kids[i] = treeFigure(node, dir, heading, uid(`ref-fig-tree-${heading.replace(/[^a-z0-9]+/gi, '-').toLowerCase() || 'tree'}`));
          report.ascii += 1;
          continue;
        }
        kids[i] = boxFigure(node, heading);
        report.ascii += 1;
        continue;
      }
      if (lang === 'yaml') {
        const chain = patternChain(code);
        if (!chain) continue;
        const next = kids.slice(i + 1).find((k) => isEl(k));
        if (isEl(next, 'figure') && classes(next).includes('fig-mermaid')) continue;
        const unknown = chain.ids.filter((c) => !loadOntology().byId.has(c));
        if (unknown.length > 0) {
          report.skipped.push(`${repoPath}: the ${chain.name} pattern fence names ${unknown.join(', ')}, not in the ontology; no chain drawn`);
          continue;
        }
        kids.splice(i, 0, chainFigure(chain, uid(`ref-fig-pattern-${chain.name.replace(/[^a-z0-9-]/gi, '-').toLowerCase()}`)));
        i += 1;
        report.chains += 1;
      }
      continue;
    }
  }
  // Tables anywhere in the tree (callouts and lists can hold them).
  const walk = (node: Root | Element) => {
    for (const c of node.children) {
      if (!isEl(c)) continue;
      if (c.tagName === 'table' && !classes(c).includes('oasf-map')) {
        if (enrichTable(c) > 0) report.tables += 1;
        continue;
      }
      walk(c);
    }
  };
  walk(tree);
  // The release notes (issue #125): a timeline, and figures and folds under long sections.
  if (repoPath === RELEASE_NOTES_SOURCE) drawReleaseFigures(tree, readRepoFile(RELEASE_NOTES_SOURCE), uid);
  numberFigures(tree);
  return report;
}

export default function rehypeProseFigures() {
  return (tree: Root, file: VFile): void => {
    const { repoPath } = sourceOf(file, PLUGIN);
    const route = routeForSource(repoPath);
    if (!route || !PROSE_TEMPLATES.has(route.template)) return;
    const report = drawProseFigures(tree, repoPath, route.template);
    for (const s of report.skipped) console.warn(`${PLUGIN}: ${s}`);
  };
}

