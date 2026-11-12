// Data for the edge types page figures (visual spec 3.7): the all-edges
// matrix and its narrow layer-pair grid (F-E2), the example chains parsed
// from the fences of spec/EDGE_TYPES.md (F-E3), the 1.1.0 changes table
// (F-E5) and the edge properties table. Each figure's caption is written
// here, so the page and its Markdown copy use the same words.
import { EDGE_TYPES, loadOntology, type EdgeType, type EdgeTypeInfo, type Ontology } from '../data/ontology';
import { readRepoFile } from './repo';
import { sectionFence, sectionTable, tableCodes, tableRows } from './md-sections';
import { capabilitySymbol, crossLayerEdges, EDGE_LABELS, edgeTypeCount, tableOrder } from './views';

export const EDGE_TYPES_SOURCE = 'spec/EDGE_TYPES.md';

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

// ------------------------------------------------------------- F-E1 cards

/** The first edge of a type in ontology order, read as a sentence: "checkpoint must run before mutate". */
export function edgeExample(info: EdgeTypeInfo): { from: string; to: string; sentence: string } {
  const e = info.edges[0];
  if (!e) throw new Error(`edge figures: the ontology has no ${info.id} edge`);
  const [phrase, ...rest] = EDGE_LABELS[info.id].out.toLowerCase().split(', ');
  const tail = rest.length > 0 ? `, ${rest.join(', ')}` : '';
  return { from: e.from, to: e.to, sentence: `${e.from} ${phrase} ${e.to}${tail}` };
}

/** The caption of an edge type's card when it stands as its own figure (the edge types page). */
export function edgeCardCaption(info: EdgeTypeInfo): string {
  const n = edgeTypeCount(info);
  const unit = info.symmetric ? (n === 1 ? 'pair' : 'pairs') : n === 1 ? 'edge' : 'edges';
  const props = [info.transitive ? 'transitive' : 'not transitive', info.symmetric ? 'symmetric' : 'not symmetric'];
  return `The ontology has ${n} ${info.id} ${unit}, ${props.join(' and ')}; the example is the first in ontology order: ${edgeExample(info).sentence}.`;
}

/** The caption of the generated table of edge types with a bar per declared count. */
export function declaredCaption(o: Ontology = loadOntology()): string {
  const top = [...o.edgeTypes].sort((a, b) => b.edges.length - a.edges.length)[0]!;
  return `${o.edges.length} edges as the ontology declares them, a symmetric pair twice; ${top.id} is the most common type, with ${top.edges.length}.`;
}

/** The caption of the "Edge Type Summary" table drawn as a figure (F-E4), symmetric types counted by pair. */
export function summaryCaption(o: Ontology = loadOntology()): string {
  const counts = o.edgeTypes.map((t) => ({ t, n: edgeTypeCount(t) }));
  const top = [...counts].sort((a, b) => b.n - a.n)[0]!;
  const trans = o.edgeTypes.filter((t) => t.transitive).map((t) => t.id);
  return `${o.edgeTypes.length} edge types, ${trans.length} of them transitive (${trans.join(', ')}); ${top.t.id} has the most edges, ${top.n}, and each bar counts a symmetric pair once.`;
}

// -------------------------------------------------------------- F-E2 matrix

export interface MatrixCell {
  from: string;
  to: string;
  /** The cell's edge types in the order of visual spec 2.4 (the ontology's type order). */
  types: EdgeType[];
}

/** Every filled cell of the from x to matrix. A cell with more than two types fails: the layout splits a cell in two at most. */
export function matrixCells(o: Ontology = loadOntology()): MatrixCell[] {
  const byPair = new Map<string, MatrixCell>();
  for (const e of o.edges) {
    const key = `${e.from}\u0000${e.to}`;
    const cell = byPair.get(key) ?? { from: e.from, to: e.to, types: [] };
    if (!cell.types.includes(e.type)) cell.types.push(e.type);
    byPair.set(key, cell);
  }
  const cells = [...byPair.values()];
  for (const c of cells) {
    c.types.sort((a, b) => EDGE_TYPES.indexOf(a) - EDGE_TYPES.indexOf(b));
    if (c.types.length > 2) throw new Error(`edge figures: ${c.from} -> ${c.to} has ${c.types.length} edge types (${c.types.join(', ')}); the matrix splits a cell in two at most`);
  }
  return cells;
}

/** "plan precedes mutate; plan enables mutate", the cell's tooltip. */
export function cellReading(c: MatrixCell): string {
  return c.types.map((t) => `${c.from} ${t} ${c.to}`).join('; ');
}

export function matrixCaption(o: Ontology = loadOntology()): string {
  const cells = matrixCells(o);
  const two = cells.filter((c) => c.types.length === 2).length;
  const n = tableOrder(o).length;
  return `On a ${n} by ${n} grid, the ${plural(o.edges.length, 'edge', 'edges')} fill ${cells.length} of the ${n * n} cells; ${plural(two, 'cell is', 'cells are')} split between a pair of edge types.`;
}

/** The figure's caption, true of both its wide and its narrow drawing. */
export function edgeMatrixCaption(o: Ontology = loadOntology()): string {
  const two = matrixCells(o).filter((c) => c.types.length === 2).length;
  const { layers, counts } = layerPairCounts(o);
  const total = counts.flat().reduce((a, b) => a + b, 0);
  const within = layers.reduce((a, _, i) => a + counts[i]![i]!, 0);
  return `The ontology declares ${plural(o.edges.length, 'edge', 'edges')}; ${plural(two, 'pair of capabilities carries', 'pairs of capabilities carry')} a second edge type, and ${within} of the ${total} relationships (a symmetric pair once) stay within a layer.`;
}

/**
 * Edges between each pair of layers, rows by the `from` layer and columns by
 * the `to` layer, in ontology layer order. Off the diagonal the counts come
 * from crossLayerEdges() (a symmetric pair once, as first declared); on the
 * diagonal they are the same-layer edges, a symmetric pair counted once.
 */
export function layerPairCounts(o: Ontology = loadOntology()): { layers: string[]; counts: number[][] } {
  const layers = o.layers.map((l) => l.id);
  const at = new Map(layers.map((l, i) => [l, i]));
  const counts = layers.map(() => layers.map(() => 0));
  layers.forEach((layer, i) => {
    for (const g of crossLayerEdges(layer, o)) {
      for (const e of g.edges) if (e.direction === 'out') counts[i]![at.get(e.otherLayer)!]! += 1;
    }
  });
  const layerOf = (id: string) => o.byId.get(id)!.layer;
  const symmetric = new Set(o.edgeTypes.filter((t) => t.symmetric).map((t) => t.id));
  const seen = new Set<string>();
  for (const e of o.edges) {
    if (layerOf(e.from) !== layerOf(e.to)) continue;
    if (symmetric.has(e.type)) {
      const key = `${e.type}|${[e.from, e.to].sort().join('|')}`;
      if (seen.has(key)) continue;
      seen.add(key);
    }
    const i = at.get(layerOf(e.from))!;
    counts[i]![i]! += 1;
  }
  return { layers, counts };
}

/** The fill token and count-text token of heat steps 1 to 4 (visual spec 1.2; tokens.css says which text each step takes). */
export const HEAT_TOKENS: readonly { fill: string; text: string }[] = [
  { fill: '--heat-1', text: '--on-heat-1' },
  { fill: '--heat-2', text: '--on-heat-2' },
  { fill: '--heat-3', text: '--on-heat-3' },
  { fill: '--heat-4', text: '--on-heat-4' },
];

/** The heat step (1 to 4) of a count on a scale up to `max`; 0 for an empty cell. */
export function heatStep(count: number, max: number): number {
  if (count <= 0) return 0;
  return Math.min(4, Math.max(1, Math.ceil((4 * count) / max)));
}

/** The counts each heat step covers, for the legend: [{ step, from, to }]; a step no count reaches is left out. */
export function heatRanges(max: number): { step: number; from: number; to: number }[] {
  const out: { step: number; from: number; to: number }[] = [];
  for (let s = 1; s <= 4; s++) {
    const counts = Array.from({ length: max }, (_, i) => i + 1).filter((c) => heatStep(c, max) === s);
    if (counts.length > 0) out.push({ step: s, from: counts[0]!, to: counts.at(-1)! });
  }
  return out;
}

export function layerPairCaption(o: Ontology = loadOntology()): string {
  const { layers, counts } = layerPairCounts(o);
  const total = counts.flat().reduce((a, b) => a + b, 0);
  const within = layers.reduce((a, _, i) => a + counts[i]![i]!, 0);
  let best = { n: -1, from: '', to: '' };
  counts.forEach((row, i) => row.forEach((n, j) => { if (n > best.n) best = { n, from: layers[i]!, to: layers[j]! }; }));
  return `${plural(total, 'edge', 'edges')}, a symmetric pair counted once: ${within} stay within a layer, and the busiest pair is ${best.from} to ${best.to} with ${best.n}.`;
}

// -------------------------------------------------------------- F-E3 chains

export interface ChainEdge {
  type: EdgeType;
  /** As drawn: the left (or upper) node and the right (or lower) node. */
  a: string;
  b: string;
  /** The ontology edge it stands for. */
  from: string;
  to: string;
}

export interface Chain {
  /** horizontal: left to right; tree: top to bottom, the parent on top. */
  form: 'horizontal' | 'tree';
  nodes: string[];
  edges: ChainEdge[];
}

const ARROW = /^\s*([a-z_]+)((?:\s+--[a-z_]+--?>?\s+[a-z_]+)+)\s*$/;
const STEP = /--([a-z_]+)--(>?)\s+([a-z_]+)/g;
const TREE_CHILD = /^(\s*)\+--([a-z_]+)--\s+([a-z_]+)\s*$/;

/**
 * The chains of an example fence of spec/EDGE_TYPES.md. A line such as
 * `a --precedes--> b --precedes--> c` is one horizontal chain; `a --type-- b`
 * is a symmetric edge. The tree form puts a node on a line and each child
 * on a `+--type-- child` line indented under it; the child is the edge's
 * `from` (detect specializes observe). Every pair must be an ontology edge of
 * that type (either direction for a symmetric type), or this throws.
 */
export function parseChains(fence: string, o: Ontology = loadOntology(), where = EDGE_TYPES_SOURCE): Chain[] {
  const lines = fence.split('\n').filter((l) => l.trim() !== '' && l.trim() !== '|');
  const chains: Chain[] = [];
  const problems: string[] = [];
  const symmetric = new Set(o.edgeTypes.filter((t) => t.symmetric).map((t) => t.id as string));
  const isType = (t: string): t is EdgeType => (EDGE_TYPES as readonly string[]).includes(t);
  const check = (type: string, from: string, to: string, directed: boolean): ChainEdge | null => {
    if (!isType(type)) {
      problems.push(`"${type}" is not an edge type`);
      return null;
    }
    const has = (f: string, t: string) => o.edges.some((e) => e.type === type && e.from === f && e.to === t);
    if (has(from, to)) return { type, a: from, b: to, from, to };
    if (!directed && symmetric.has(type) && has(to, from)) return { type, a: from, b: to, from: to, to: from };
    problems.push(`${from} --${type}--${directed ? '>' : ''} ${to} is not an edge of the ontology`);
    return null;
  };
  if (lines.some((l) => TREE_CHILD.test(l))) {
    // One tree: the first line is the root; each child hangs under the node above it.
    const nodes = [lines[0]!.trim()];
    const edges: ChainEdge[] = [];
    for (const l of lines.slice(1)) {
      const m = TREE_CHILD.exec(l);
      if (!m) {
        problems.push(`tree line "${l.trim()}" is not "+--type-- child"`);
        continue;
      }
      const parent = nodes.at(-1)!;
      const e = check(m[2]!, m[3]!, parent, true);
      if (e) edges.push({ ...e, a: parent, b: m[3]! });
      nodes.push(m[3]!);
    }
    chains.push({ form: 'tree', nodes, edges });
  } else {
    for (const l of lines) {
      const m = ARROW.exec(l);
      if (!m) {
        problems.push(`line "${l.trim()}" is not a chain`);
        continue;
      }
      const nodes = [m[1]!];
      const edges: ChainEdge[] = [];
      for (const s of m[2]!.matchAll(STEP)) {
        const e = check(s[1]!, nodes.at(-1)!, s[3]!, s[2] === '>');
        if (e) edges.push(e);
        nodes.push(s[3]!);
      }
      chains.push({ form: 'horizontal', nodes, edges });
    }
  }
  if (problems.length > 0) throw new Error(`${where}: example fence: ${problems.join('; ')}`);
  return chains;
}

/** The three example sections of "Examples in the Ontology", by heading. */
export const CHAIN_SECTIONS = ['Safety-Critical Precedes Chain', 'Specialization Hierarchy', 'Conflict Resolution'] as const;

export function exampleChains(heading: string, text = readRepoFile(EDGE_TYPES_SOURCE)): Chain[] {
  return parseChains(sectionFence(text, heading, 0, EDGE_TYPES_SOURCE).value);
}

/** Each capability of the chains once, with its periodic-table symbol, in drawing order. */
export function chainKey(chains: Chain[]): { id: string; symbol: string }[] {
  return [...new Set(chains.flatMap((c) => c.nodes))].map((id) => ({ id, symbol: capabilitySymbol(id) }));
}

export function chainCaption(chains: Chain[]): string {
  const edges = chains.flatMap((c) => c.edges);
  const caps = new Set(chains.flatMap((c) => c.nodes));
  const types = [...new Set(edges.map((e) => e.type))];
  return `${plural(edges.length, 'edge', 'edges')} of type ${types.join(' and ')} among ${plural(caps.size, 'capability', 'capabilities')}, each one an edge of the ontology; the fence in this section is the same example as text.`;
}

// ------------------------------------------------------------- F-E5 changes

export interface EdgeChange {
  from: string;
  to: string;
  /** The 1.0.0 type, or null for "—" (the edge is new). */
  before: EdgeType | null;
  /** The 1.1.0 type, or null when the edge was removed. */
  after: EdgeType | null;
  why: string;
}

/**
 * The rows of "Changes to the ontology's edges in 1.1.0", one per target
 * ("constrain → execute, mutate, send" is three). A 1.1.0 type that is not an
 * edge of that pair now, or a removed edge that still exists, throws.
 */
export function edgeChanges(text = readRepoFile(EDGE_TYPES_SOURCE), o: Ontology = loadOntology()): EdgeChange[] {
  const t = sectionTable(text, "Changes to the ontology's edges in 1.1.0", 0, EDGE_TYPES_SOURCE);
  const [head, ...rows] = tableRows(t);
  const col = (name: string) => {
    const i = head!.indexOf(name);
    if (i === -1) throw new Error(`${EDGE_TYPES_SOURCE}: the 1.1.0 changes table has no "${name}" column`);
    return i;
  };
  const [cEdge, cBefore, cAfter, cWhy] = [col('Edge'), col('1.0.0'), col('1.1.0'), col('Why')];
  const isType = (v: string): v is EdgeType => (EDGE_TYPES as readonly string[]).includes(v);
  const problems: string[] = [];
  const out: EdgeChange[] = [];
  for (const r of rows) {
    const m = /^([a-z_]+)\s*→\s*(.+)$/.exec(r[cEdge]!);
    if (!m) {
      problems.push(`edge "${r[cEdge]}" is not "from → to"`);
      continue;
    }
    const before = r[cBefore]!.trim();
    const after = r[cAfter]!.trim();
    for (const to of m[2]!.split(',').map((s) => s.trim())) {
      const row: EdgeChange = {
        from: m[1]!,
        to,
        before: isType(before) ? before : null,
        after: isType(after) ? after : null,
        why: r[cWhy]!,
      };
      if (!o.byId.has(row.from) || !o.byId.has(to)) problems.push(`${row.from} → ${to} names a capability the ontology does not have`);
      if (before !== '—' && !row.before) problems.push(`${row.from} → ${to}: 1.0.0 type "${before}" is not an edge type`);
      if (after === 'removed') {
        if (row.before && o.edges.some((e) => e.from === row.from && e.to === to && e.type === row.before)) {
          problems.push(`${row.from} → ${to}: the removed ${row.before} edge still exists`);
        }
      } else if (!row.after) {
        problems.push(`${row.from} → ${to}: 1.1.0 type "${after}" is not an edge type`);
      } else if (!o.edges.some((e) => e.from === row.from && e.to === to && e.type === row.after)) {
        problems.push(`${row.from} → ${to}: the ontology has no ${row.after} edge`);
      }
      out.push(row);
    }
  }
  if (problems.length > 0) throw new Error(`${EDGE_TYPES_SOURCE}: 1.1.0 changes table: ${problems.join('; ')}`);
  return out;
}

export function changesCaption(rows: EdgeChange[]): string {
  const retyped = rows.filter((r) => r.before && r.after).length;
  const added = rows.filter((r) => !r.before && r.after).length;
  const removed = rows.filter((r) => !r.after).length;
  return `In 1.1.0, ${plural(retyped, 'edge changed', 'edges changed')} type, ${plural(added, 'edge was', 'edges were')} added and ${plural(removed, 'edge was', 'edges were')} removed; each 1.1.0 type is checked against the ontology.`;
}

// --------------------------------------------------------- edge properties

export interface PropertyRow {
  name: string;
  type: string;
  required: boolean;
  description: string;
}

/** A field table (Field or Property, Type, Required, Description) of a section, as port rows. */
export function fieldTable(text: string, heading: string, where: string): PropertyRow[] {
  const t = sectionTable(text, heading, 0, where);
  const [head, ...rows] = tableRows(t);
  const codes = tableCodes(t).slice(1);
  const col = (re: RegExp) => {
    const i = head!.findIndex((h) => re.test(h));
    if (i === -1) throw new Error(`${where}: the table under "${heading}" has no ${re} column`);
    return i;
  };
  const [cName, cType, cReq, cDesc] = [col(/^(Field|Property)$/), col(/^Type$/), col(/^Required$/), col(/^Description$/)];
  return rows.map((r, i) => ({
    name: codes[i]![cName]![0] ?? r[cName]!,
    type: r[cType]!,
    required: /^Yes\b/.test(r[cReq]!),
    description: r[cDesc]!,
  }));
}

export function fieldsCaption(rows: PropertyRow[], what: string): string {
  const req = rows.filter((r) => r.required).length;
  return `${what} ${plural(rows.length, 'field', 'fields')}: ${req} required (filled pin) and ${rows.length - req} optional (outlined pin).`;
}

export { edgeTypeCount };
