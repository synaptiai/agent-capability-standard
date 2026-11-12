// What the capability page's figures show (visual spec 3.1), as plain data
// and plain-words captions. The page and its Markdown copy call the same
// functions, so the figure, its caption and the copy's figure block always
// agree. Kept apart from views.ts so the figure work of each page type stays
// in its own file.
import { EDGE_TYPES, loadOntology, type Capability, type EdgeType, type Ontology } from '../data/ontology';
import { capabilityUsage, type CapabilityUse } from '../data/workflows';
import { sectionFence, sectionOrderedItems, sectionTableByHeader, tableRows } from './md-sections';
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

/**
 * F-C1's caption. It counts capabilities per row, as the row headings do, so
 * the two never disagree: "{id} has {r} relationships with {n} capabilities:
 * {i} with edges into it and {o} with edges out of it". A symmetric edge drawn
 * in a directed row (its tile sits there for its directed edge) is named after
 * a semicolon: "its conflicts_with edge with rollback runs both ways".
 */
export function neighbourhoodCaption(cap: Capability, list: Neighbour[]): string {
  const c = neighbourCounts(list);
  const words: Record<NeighbourGroup, string> = {
    into: 'with edges into it',
    out: 'with edges out of it',
    both: 'with edges both into it and out of it',
    either: 'joined to it only by edges that run both ways',
  };
  const parts = NEIGHBOUR_GROUPS.map((g) => ({ g, n: list.filter((x) => x.group === g).length })).filter((x) => x.n > 0).map((x) => `${x.n} ${words[x.g]}`);
  const joined = parts.length <= 1 ? parts.join('') : `${parts.slice(0, -1).join(', ')}${parts.length > 2 ? ',' : ''} and ${parts.at(-1)}`;
  const tucked = list
    .filter((x) => x.group !== 'either')
    .flatMap((x) => x.relations.filter((r) => r.direction === 'both-ways').map((r) => `${r.type} edge with ${x.id}`));
  const tail = tucked.length === 0 ? '' : `; its ${tucked.length === 1 ? tucked[0] : `${tucked.slice(0, -1).join(', ')} and ${tucked.at(-1)}`} ${tucked.length === 1 ? 'runs' : 'run'} both ways`;
  return `${cap.id} has ${plural(c.relations, 'relationship', 'relationships')} with ${plural(c.capabilities, 'capability', 'capabilities')}: ${joined}${tail}.`;
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

// ------------------------------------------------- F-C5 ordering and safety

/** The edge types that place one step before another (Standard §4.3). */
export const ORDERING_TYPES = ['requires', 'soft_requires', 'precedes'] as const;
export type OrderingType = (typeof ORDERING_TYPES)[number];

export interface EdgeRule {
  /** The word in the §4.3 "Enforcement" column: MUST, SHOULD. */
  level: string;
  /** The first diagnostic code in the §4.3 "Diagnostic" column, e.g. V102. */
  code: string;
}

/**
 * The enforcement level and diagnostic of each ordering edge type and of
 * conflicts_with, read from the two tables of the Standard's §4.3. Throws
 * when a type has no row, so a renamed table cannot leave the figure blank.
 */
export function edgeRules(standardText: string, where: string): Record<OrderingType | 'conflicts_with', EdgeRule> {
  const levels = new Map<string, string>();
  for (const row of tableRows(sectionTableByHeader(standardText, '4.3 ', 'Edge Type', where)).slice(1)) {
    levels.set(row[0]!.replace(/`/g, ''), row[1]!.trim());
  }
  const codes = new Map<string, string>();
  for (const row of tableRows(sectionTableByHeader(standardText, '4.3 ', 'Edge', where)).slice(1)) {
    const code = /\b[A-Z]\d{3}\b/.exec(row[2] ?? '')?.[0];
    for (const t of row[0]!.replace(/`/g, '').split(/,\s*/)) if (code) codes.set(t.trim(), code);
  }
  const out = {} as Record<OrderingType | 'conflicts_with', EdgeRule>;
  for (const t of [...ORDERING_TYPES, 'conflicts_with'] as const) {
    const level = levels.get(t);
    const code = codes.get(t);
    if (!level || !code) throw new Error(`${where}: §4.3 gives no enforcement level or diagnostic for ${t}`);
    out[t] = { level, code };
  }
  return out;
}

export interface OrderedNeighbour {
  id: string;
  /** In ORDERING_TYPES order. */
  types: OrderingType[];
}

export interface SafetySequence {
  /** Capabilities with an ordering edge into this one: they run before it. */
  before: OrderedNeighbour[];
  /** Capabilities this one has an ordering edge to: they run after it. */
  after: OrderedNeighbour[];
  approval: boolean;
  /** The ontology flag, as against a checkpoint that comes only from a requires edge. */
  checkpointFlag: boolean;
  /** Capabilities joined by conflicts_with: never in the same parallel_group. */
  apart: string[];
}

/**
 * Where a capability may sit in a workflow's step list, from its ordering
 * edges (requires, soft_requires, precedes) and its approval and checkpoint
 * flags. Neighbours are in periodic-table order.
 */
export function safetySequence(cap: Capability, ontology: Ontology = loadOntology()): SafetySequence {
  const order = tableOrder(ontology);
  const side = (edges: Capability['edgesIn']): OrderedNeighbour[] => {
    const ids = [...new Set(ORDERING_TYPES.flatMap((t) => edges[t]))].sort((a, b) => order.indexOf(a) - order.indexOf(b));
    return ids.map((id) => ({ id, types: ORDERING_TYPES.filter((t) => edges[t].includes(id)) }));
  };
  const apart = [...new Set([...cap.edgesOut.conflicts_with, ...cap.edgesIn.conflicts_with])].sort((a, b) => order.indexOf(a) - order.indexOf(b));
  return {
    before: side(cap.edgesIn),
    after: side(cap.edgesOut),
    approval: cap.requires_approval,
    checkpointFlag: cap.requires_checkpoint,
    apart,
  };
}

/** How many ordering rules the sequence draws: one per (neighbour, type). */
export function sequenceRuleCount(s: SafetySequence): number {
  return [...s.before, ...s.after].reduce((k, n) => k + n.types.length, 0) + s.apart.length;
}

/** True when the sequence is worth a figure; otherwise the page prints sequenceSentence(). */
export function sequenceIsFigure(s: SafetySequence): boolean {
  return s.approval || s.checkpointFlag || sequenceRuleCount(s) >= 2;
}

/** F-C5's title. */
export function sequenceTitle(cap: Capability): string {
  return `Ordering rules for ${cap.id} in a workflow`;
}

/**
 * F-C5's caption, or the sentence printed in its place: what must, should
 * or may come before and after the capability, in plain words.
 */
export function sequenceCaption(cap: Capability, s: SafetySequence, rules: Record<OrderingType | 'conflicts_with', EdgeRule>): string {
  const names = (ids: string[]) => (ids.length === 1 ? ids[0]! : `${ids.slice(0, -1).join(', ')} and ${ids.at(-1)}`);
  const withType = (side: OrderedNeighbour[], t: OrderingType) => side.filter((n) => n.types.includes(t)).map((n) => n.id);
  const parts: string[] = [];
  const must = withType(s.before, 'requires');
  if (must.length > 0) parts.push(`${names(must)} must run before it (${rules.requires.code})`);
  const should = withType(s.before, 'soft_requires');
  if (should.length > 0) parts.push(`${should.length === 1 ? should[0] : `one of ${names(should)}`} should run before it (${rules.soft_requires.code})`);
  const first = withType(s.before, 'precedes').filter((id) => !must.includes(id));
  if (first.length > 0) parts.push(`${names(first)}, where the workflow has ${first.length === 1 ? 'it' : 'them'}, must come first (${rules.precedes.code})`);
  const needs = withType(s.after, 'requires');
  if (needs.length > 0) parts.push(`it must run before ${names(needs)} (${rules.requires.code})`);
  const helps = withType(s.after, 'soft_requires');
  if (helps.length > 0) parts.push(`it is a recommended step before ${names(helps)}`);
  const then = withType(s.after, 'precedes');
  if (then.length > 0) parts.push(`where the workflow has ${names(then)}, ${cap.id} must come before ${then.length === 1 ? 'it' : 'them'} (${rules.precedes.code})`);
  if (s.approval) parts.push('each use needs approval');
  if (s.checkpointFlag && !must.includes('checkpoint')) parts.push('a checkpoint must run before it');
  if (s.apart.length > 0) parts.push(`it never shares a parallel group with ${names(s.apart)} (${rules.conflicts_with.code})`);
  if (parts.length === 0) return `No ordering edge and no approval or checkpoint flag constrains where ${cap.id} runs in a step list, and no conflicts_with edge keeps it out of a parallel group.`;
  const text = parts.length === 1 ? parts[0]! : `${parts.slice(0, -1).join('; ')}; and ${parts.at(-1)}`;
  return `In a workflow, ${text}.`;
}

// ---------------------------------------------------- F-C6 skill output fields

export interface OutputFields {
  /** Top-level fields of the skill's Output Contract fence, in its order. */
  skill: { name: string; inContract: boolean; required: boolean }[];
  /** Top-level contract outputs the skill's fence does not name. */
  missing: string[];
}

/** Top-level keys of the first YAML fence under the skill's "Output Contract" heading. */
export function skillOutputKeys(skillText: string, where: string): string[] {
  const fence = sectionFence(skillText, 'Output Contract', 0, where);
  return [...new Set(fence.value.split('\n').flatMap((l) => /^([A-Za-z_][A-Za-z0-9_]*)\s*:/.exec(l)?.[1] ?? []))];
}

/** The skill's output fields against the capability's output contract. */
export function outputFields(cap: Capability, skillText: string, where: string): OutputFields {
  const contract = contractRows(cap.output_schema).filter((r) => r.depth === 0);
  const keys = skillOutputKeys(skillText, where);
  return {
    skill: keys.map((name) => {
      const row = contract.find((r) => r.name === name);
      return { name, inContract: row !== undefined, required: row?.required ?? false };
    }),
    missing: contract.filter((r) => !keys.includes(r.name)).map((r) => r.name),
  };
}

/** True when the comparison is worth a figure: the skill adds fields or leaves some out. */
export function outputFieldsIsFigure(f: OutputFields): boolean {
  return f.missing.length > 0 || f.skill.some((x) => !x.inContract);
}

/** F-C6's title. */
export function outputFieldsTitle(cap: Capability, f: OutputFields): string {
  const inC = f.skill.filter((x) => x.inContract).length;
  return `Fields of the ${cap.id} skill's output: ${inC} of ${f.skill.length} in the contract`;
}

/** F-C6's caption, or the sentence printed in its place. */
export function outputFieldsCaption(cap: Capability, f: OutputFields): string {
  const inC = f.skill.filter((x) => x.inContract);
  const req = inC.filter((x) => x.required).length;
  const added = f.skill.length - inC.length;
  if (!outputFieldsIsFigure(f)) return `Every field of the skill's output is a field of ${cap.id}'s output contract, and the skill names all of them.`;
  const missing = f.missing.length === 0 ? '' : `; it leaves out ${plural(f.missing.length, 'contract field', 'contract fields')} (${f.missing.join(', ')})`;
  return `The skill returns ${plural(f.skill.length, 'field', 'fields')}: ${inC.length} ${inC.length === 1 ? 'is' : 'are'} in ${cap.id}'s output contract (${req} required) and ${added} ${added === 1 ? 'is' : 'are'} the skill's own, outside the contract${missing}.`;
}


// ------------------------------------------------------------ F-C7 procedure map

export interface ProcedureStep {
  /** 1-based position in the procedure. */
  n: number;
  /** The step's bold title, or its first words when it has none. */
  title: string;
  /** The skill's inputs the step's text names, in the Inputs table's order. */
  reads: string[];
  /** The skill's output fields the step's text names, in the Output Contract fence's order. */
  writes: string[];
}

export interface ProcedureMap {
  steps: ProcedureStep[];
  inputs: string[];
  outputs: string[];
}

/** The parameter names of the skill's Inputs table (its first column, without backticks). */
export function skillInputNames(skillText: string, where: string): string[] {
  const rows = tableRows(sectionTableByHeader(skillText, 'Inputs', 'Parameter', where)).slice(1);
  return rows.map((r) => r[0]!.replace(/`/g, '').trim()).filter((x) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(x));
}

/**
 * True when `text` uses `field` as a whole word (not part of a longer name).
 * This is a word match, not a reading of what the step does: a field named
 * with an English word ("data", "options") is marked wherever the step uses
 * that word, and the caption says so.
 */
function names(text: string, field: string): boolean {
  return new RegExp(`(?<![A-Za-z0-9_])${field}(?![A-Za-z0-9_])`).test(text);
}

/**
 * F-C7: for each step of the skill's Procedure, the skill's inputs and output
 * fields its text names, matched as whole words in the step and its sub-items.
 */
export function procedureMap(skillText: string, where: string): ProcedureMap {
  const inputs = skillInputNames(skillText, where);
  const outputs = skillOutputKeys(skillText, where);
  const steps = sectionOrderedItems(skillText, 'Procedure', where).map((item, i) => ({
    n: i + 1,
    title: item.title ?? item.text.split(/\s+/).slice(0, 6).join(' '),
    reads: inputs.filter((f) => names(item.text, f)),
    writes: outputs.filter((f) => names(item.text, f)),
  }));
  return { steps, inputs, outputs };
}

/** Steps that name at least one field. */
const naming = (m: ProcedureMap) => m.steps.filter((s) => s.reads.length + s.writes.length > 0);

/** A figure only when two or more steps name a field; otherwise one sentence says so. */
export function procedureMapIsFigure(m: ProcedureMap): boolean {
  return naming(m).length >= 2;
}

/** F-C7's title. */
export function procedureMapTitle(cap: Capability): string {
  return `The field names each step of the ${cap.id} procedure uses`;
}

/** F-C7's caption, or the sentence printed in its place. */
export function procedureMapCaption(cap: Capability, m: ProcedureMap): string {
  const k = naming(m).length;
  const named = new Set(m.steps.flatMap((s) => s.writes));
  const silent = m.outputs.filter((f) => !named.has(f));
  const lead = `${k} of the procedure's ${plural(m.steps.length, 'step', 'steps')} ${k === 1 ? 'uses' : 'use'} the name of an input or output field of the ${cap.id} skill as a word`;
  if (!procedureMapIsFigure(m)) return `${lead}.`;
  const tail =
    silent.length === 0
      ? '; every output field is used by at least one step.'
      : silent.length === m.outputs.length
        ? '; no step uses an output field.'
        : `; ${plural(silent.length, 'output field', 'output fields')} of ${m.outputs.length} ${silent.length === 1 ? 'is' : 'are'} used by no step (${silent.join(', ')}).`;
  return lead + tail;
}
