// What the capability page's figures show (visual spec 3.1), as plain data
// and plain-words captions. The page and its Markdown copy call the same
// functions, so the figure, its caption and the copy's figure block always
// agree. Kept apart from views.ts so the figure work of each page type stays
// in its own file.
import { EDGE_TYPES, loadOntology, type Capability, type EdgeType, type Ontology } from '../data/ontology';
import { capabilityUsage, type CapabilityUse } from '../data/workflows';
import { contractRows, tableOrder, type SchemaRow } from './views';

// ------------------------------------------------------------ F-C1 neighbours

/** `in`: the edge points at this capability; `out`: away from it; `both-ways`: a symmetric type. */
export type RelationDirection = 'in' | 'out' | 'both-ways';

export interface Relation {
  type: EdgeType;
  direction: RelationDirection;
}

/** The four rows of F-C1, grouped by direction, never by type. */
export type NeighbourGroup = 'into' | 'out' | 'both' | 'either';
export const NEIGHBOUR_GROUPS: readonly NeighbourGroup[] = ['into', 'out', 'both', 'either'];

export interface Neighbour {
  id: string;
  /** In the ontology's edge type order; a symmetric type appears once. */
  relations: Relation[];
  group: NeighbourGroup;
}

/**
 * Every capability this one has an edge with, once each, with every relation
 * it has to it. A neighbour whose directed relations all point here is
 * "into"; all away, "out"; some each way, "both"; only symmetric relations,
 * "either". A symmetric relation beside a directed one leaves the neighbour
 * in its directed group. Neighbours are in periodic-table order.
 */
export function neighbours(cap: Capability, ontology: Ontology = loadOntology()): Neighbour[] {
  const byId = new Map<string, Relation[]>();
  const add = (id: string, r: Relation) => {
    const list = byId.get(id) ?? [];
    if (!list.some((x) => x.type === r.type && x.direction === r.direction)) list.push(r);
    byId.set(id, list);
  };
  for (const type of EDGE_TYPES) {
    const symmetric = ontology.edgeTypes.find((t) => t.id === type)!.symmetric;
    for (const id of cap.edgesIn[type]) add(id, { type, direction: symmetric ? 'both-ways' : 'in' });
    for (const id of cap.edgesOut[type]) add(id, { type, direction: symmetric ? 'both-ways' : 'out' });
  }
  const order = tableOrder(ontology);
  return [...byId.entries()]
    .sort(([a], [b]) => order.indexOf(a) - order.indexOf(b))
    .map(([id, relations]) => {
      const ins = relations.some((r) => r.direction === 'in');
      const outs = relations.some((r) => r.direction === 'out');
      const group: NeighbourGroup = ins && outs ? 'both' : ins ? 'into' : outs ? 'out' : 'either';
      return { id, relations, group };
    });
}

/** The heading of a F-C1 row. */
export function neighbourGroupLabel(group: NeighbourGroup, id: string): string {
  return { into: `Edges into ${id}`, out: `Edges out of ${id}`, both: 'Both directions', either: 'Either way' }[group];
}

/**
 * The relation words of one neighbour, as its tile's accessible name ends:
 * "requires, precedes". In the "both directions" row each word says which
 * way it points: "precedes, into it; enables, out of it".
 */
export function relationWords(n: Neighbour): string {
  if (n.group !== 'both') return n.relations.map((r) => r.type).join(', ');
  const way = { in: 'into it', out: 'out of it', 'both-ways': 'both ways' } as const;
  return n.relations.map((r) => `${r.type}, ${way[r.direction]}`).join('; ');
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** Counts behind F-C1's name and caption: relations by direction. */
export function neighbourCounts(list: Neighbour[]): { relations: number; capabilities: number; into: number; out: number; bothWays: number } {
  const all = list.flatMap((n) => n.relations);
  return {
    relations: all.length,
    capabilities: list.length,
    into: all.filter((r) => r.direction === 'in').length,
    out: all.filter((r) => r.direction === 'out').length,
    bothWays: all.filter((r) => r.direction === 'both-ways').length,
  };
}

/** F-C1's accessible name. */
export function neighbourhoodTitle(cap: Capability, list: Neighbour[]): string {
  const c = neighbourCounts(list);
  return `Relationships of ${cap.id}: ${plural(c.relations, 'relationship', 'relationships')} with ${plural(c.capabilities, 'capability', 'capabilities')}`;
}

/** F-C1's caption: "{id} has {r} relationships with {n} capabilities: {i} point into it, {o} point out of it, and {b} run both ways." */
export function neighbourhoodCaption(cap: Capability, list: Neighbour[]): string {
  const c = neighbourCounts(list);
  const parts = [
    ...(c.into > 0 ? [`${c.into} ${c.into === 1 ? 'points' : 'point'} into it`] : []),
    ...(c.out > 0 ? [`${c.out} ${c.out === 1 ? 'points' : 'point'} out of it`] : []),
    ...(c.bothWays > 0 ? [`${c.bothWays} ${c.bothWays === 1 ? 'runs' : 'run'} both ways`] : []),
  ];
  const joined = parts.length <= 1 ? parts.join('') : `${parts.slice(0, -1).join(', ')}${parts.length > 2 ? ',' : ''} and ${parts.at(-1)}`;
  return `${cap.id} has ${plural(c.relations, 'relationship', 'relationships')} with ${plural(c.capabilities, 'capability', 'capabilities')}: ${joined}.`;
}

// --------------------------------------------------------------- F-C2 contract

export interface ContractSummary {
  inputs: SchemaRow[];
  outputs: SchemaRow[];
  /** Top-level fields only. */
  inputCount: number;
  requiredInputs: number;
  outputCount: number;
}

export function contractSummary(cap: Capability): ContractSummary {
  const inputs = contractRows(cap.input_schema);
  const outputs = contractRows(cap.output_schema);
  const top = (rows: SchemaRow[]) => rows.filter((r) => r.depth === 0);
  return {
    inputs,
    outputs,
    inputCount: top(inputs).length,
    requiredInputs: top(inputs).filter((r) => r.required).length,
    outputCount: top(outputs).length,
  };
}

/** F-C2's accessible name: "Contract of mutate: 3 inputs (2 required), 9 outputs". */
export function contractTitle(cap: Capability, s: ContractSummary = contractSummary(cap)): string {
  return `Contract of ${cap.id}: ${plural(s.inputCount, 'input', 'inputs')} (${s.requiredInputs} required), ${plural(s.outputCount, 'output', 'outputs')}`;
}

/** F-C2's caption. */
export function contractCaption(cap: Capability, s: ContractSummary = contractSummary(cap)): string {
  const optional = s.inputCount - s.requiredInputs;
  const ins =
    s.inputCount === 0
      ? `${cap.id} takes no inputs`
      : `${cap.id} takes ${plural(s.inputCount, 'input', 'inputs')}, ${s.requiredInputs} required (filled pin) and ${optional} optional (hollow pin)`;
  return `${ins}, and returns ${plural(s.outputCount, 'output', 'outputs')}.`;
}

/** Fields that carry the grounded-claims principle (visual spec F-C2). */
export const GROUNDED_FIELDS: ReadonlySet<string> = new Set(['evidence_anchors', 'confidence']);

/** The id of a contract table row, which the ports link to. */
export function contractRowId(side: 'in' | 'out', path: string): string {
  return `ref-contract-${side}-${path.replace(/[^A-Za-z0-9_.-]+/g, '-')}`;
}

// ------------------------------------------------------------ F-C4 usage

/** F-C4's caption. Steps are counted over every workflow. */
export function usageCaption(cap: Capability, usage: CapabilityUse[] = capabilityUsage(cap.id)): string {
  if (usage.length === 0) return `No reference or domain workflow uses ${cap.id} yet.`;
  const steps = usage.reduce((n, u) => n + u.steps.length, 0);
  return `${plural(usage.length, 'workflow uses', 'workflows use')} ${cap.id}, in ${plural(steps, 'step', 'steps')} in all; its steps are the squares that carry its symbol.`;
}

/** The step list after a workflow name: "step 16", "steps 3 and 7". */
export function stepWords(steps: number[]): string {
  return steps.length === 1 ? `step ${steps[0]}` : `steps ${steps.slice(0, -1).join(', ')} and ${steps.at(-1)}`;
}

// ------------------------------------------------- SKILL.md Composition Patterns

export interface CompositionChain {
  /** Capability ids under "Commonly follows:", in order, once each. */
  follows: string[];
  /** Capability ids under "Commonly precedes:", in order, once each. */
  precedes: string[];
}

/**
 * The capabilities a skill names in its Composition Patterns section: the
 * first backticked word of each list item under "**Commonly follows:**" and
 * "**Commonly precedes:**" that is a capability id. Other words are skipped.
 */
export function compositionChain(skillText: string, ontology: Ontology = loadOntology()): CompositionChain {
  const lines = skillText.split('\n');
  const start = lines.findIndex((l) => /^## Composition Patterns\s*$/.test(l));
  const out: CompositionChain = { follows: [], precedes: [] };
  if (start === -1) return out;
  let list: keyof CompositionChain | null = null;
  for (const line of lines.slice(start + 1)) {
    if (/^#{1,2} /.test(line)) break;
    const label = /^\*\*(.+?):?\*\*:?\s*$/.exec(line.trim());
    if (label) {
      const l = label[1]!.toLowerCase();
      list = l === 'commonly follows' ? 'follows' : l === 'commonly precedes' ? 'precedes' : null;
      continue;
    }
    if (list === null) continue;
    const item = /^[-*]\s+(.*)$/.exec(line);
    if (!item) continue;
    const id = [...item[1]!.matchAll(/`([^`]+)`/g)].map((m) => m[1]!).find((w) => ontology.byId.has(w));
    if (id && !out[list].includes(id)) out[list].push(id);
  }
  return out;
}

/** The chain figure's caption. */
export function chainCaption(cap: Capability, chain: CompositionChain): string {
  const names = (ids: string[]) => (ids.length === 1 ? ids[0]! : `${ids.slice(0, -1).join(', ')} and ${ids.at(-1)}`);
  const parts = [
    ...(chain.follows.length > 0 ? [`commonly follows ${names(chain.follows)}`] : []),
    ...(chain.precedes.length > 0 ? [`commonly precedes ${names(chain.precedes)}`] : []),
  ];
  return `As this section says, ${cap.id} ${parts.join(', and ')}.`;
}

// ------------------------------------------------------------ rendered skill

/**
 * Rendered Markdown split at each H2: the text before the first H2, then one
 * part per H2 with the heading (`head`, up to its closing tag) and the rest
 * of its section (`body`). The page puts figures between a heading and its
 * body. Joining every part gives the input back.
 */
export function splitAtH2s(html: string): { lead: string; parts: { id: string; head: string; body: string }[] } {
  const starts = [...html.matchAll(/<h2\b/g)].map((m) => m.index!);
  const lead = html.slice(0, starts[0] ?? html.length);
  const parts = starts.map((s, i) => {
    const chunk = html.slice(s, starts[i + 1] ?? html.length);
    const close = chunk.indexOf('</h2>');
    if (close === -1) throw new Error('splitAtH2s: an <h2> is not closed');
    const id = /^<h2\b[^>]*\sid="([^"]*)"/.exec(chunk)?.[1] ?? '';
    return { id, head: chunk.slice(0, close + 5), body: chunk.slice(close + 5) };
  });
  return { lead, parts };
}
