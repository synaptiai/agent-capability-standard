// The figures of a workflow page (visual spec 3.3) and the strips of the
// workflows index (3.4), as data: the step spine (F-W1), the data-flow grid
// (F-W2), the risk summary (F-W3) and the inputs caption (F-W4). The page and
// its Markdown copy both call these functions, so the two always say the same
// thing. Nothing here is typed by hand: every count, name and sentence is
// computed from the loaded workflow.
import type { Risk } from '../data/ontology';
import type { Workflow } from '../data/workflows';
import { capabilitySymbol, diagramRuns, diagramSteps, failureRows, gateRows, producerSteps, schemaRows, type StepRole } from './views';

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);

const RISK_LEVEL: Record<Risk, number> = { low: 1, medium: 2, high: 3 };

/** "step 3", "steps 3 and 9", "steps 2, 5 and 9". */
export function stepList(ns: readonly number[]): string {
  if (ns.length === 0) return 'no steps';
  if (ns.length === 1) return `step ${ns[0]}`;
  return `steps ${ns.slice(0, -1).join(', ')} and ${ns.at(-1)}`;
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

// --------------------------------------------------------------- the spine

/** What a gate action does, in plain words (Standard §5.6). */
export const GATE_WORDS: Readonly<Record<string, string>> = {
  stop: 'gate stops the run',
  skip: 'gate skips the step',
  rollback: 'gate rolls back to the checkpoint',
  warn: 'gate records a warning',
  end: 'gate ends the run as a success',
};

/** What a failure-mode action does, in plain words (Standard §5.7). */
export const FAILURE_WORDS: Readonly<Record<string, string>> = {
  stop: 'on failure, stop',
  rollback: 'on failure, roll back',
  request_more_context: 'on failure, ask for more context',
  pause_and_checkpoint: 'on failure, pause and checkpoint',
  escalate: 'on failure, escalate',
};

/** The role glyph of a step tile; plain steps have none on purpose (visual spec 2.3). */
export const ROLE_GLYPH: Readonly<Record<StepRole, string | null>> = {
  checkpoint: 'role:checkpoint',
  verify: 'role:verify',
  rollback: 'role:rollback',
  mutating: 'role:mutating',
  plain: null,
};

// Checkpoint and rollback steps change state too (their mutation flag is
// true, and the page header counts them), so the mutating role is worded as
// the step that makes the workflow's change, not as the only one that writes.
const ROLE_WORDS: Readonly<Record<Exclude<StepRole, 'plain'>, string>> = {
  checkpoint: 'saves a checkpoint',
  verify: 'checks a result',
  rollback: 'rolls back',
  mutating: 'makes the change',
};

export interface SpineStep {
  index: number;
  capability: string;
  layer: string;
  symbol: string;
  purpose: string;
  role: StepRole;
  /** The step's `condition`, when it has one. */
  condition: string | null;
  /** Gate actions in file order. */
  gates: string[];
  /** Failure-mode actions in file order. */
  failures: string[];
  risk: Risk;
  /** The workflow the step runs, if any. */
  workflowId: string | null;
  /** Earlier steps whose stored output this step reads, ascending, once each. */
  reads: number[];
  /** The checkpoint a changing or rollback step relies on. */
  checkpointStep: number | null;
}

/**
 * One row of the spine, top to bottom. A parallel group is a fork bar, one row
 * with its steps side by side, and a join bar.
 */
export type SpineRow =
  | { kind: 'step'; step: SpineStep }
  | { kind: 'fork'; group: string; size: number }
  | { kind: 'parallel'; group: string; steps: SpineStep[] }
  | { kind: 'join'; group: string; join: string | null };

/** A bracket in a lane, from one row to another (0-based rows). */
export interface SpineSpan {
  from: number;
  to: number;
  /** The step the bracket starts at, and the one it ends at. */
  fromStep: number;
  toStep: number;
}

export interface LegendItem {
  /** A glyph key, or 'pips' for the risk pips. */
  glyph: string;
  label: string;
}

export interface Spine {
  workflowId: string;
  rows: SpineRow[];
  steps: SpineStep[];
  /** The row each step is drawn in. */
  rowOf: ReadonlyMap<number, number>;
  checkpointSpans: SpineSpan[];
  rollbackSpans: SpineSpan[];
  /** Which optional lanes are drawn: a lane is drawn only when a row uses it. */
  lanes: { checkpoint: boolean; rollback: boolean; gate: boolean; failure: boolean; reads: boolean };
  /** The most gate glyphs one step has. */
  maxGates: number;
  /** The most failure glyphs one step has. */
  maxFailures: number;
  legend: LegendItem[];
  /** The figure's accessible name (visual spec 3.3, F-W1). */
  title: string;
  /** A one-sentence reading of the figure. */
  caption: string;
}

function joinText(join: unknown): string | null {
  if (join === undefined || join === null) return null;
  return typeof join === 'string' ? join : JSON.stringify(join);
}

/** The spine of a workflow (visual spec 3.3, F-W1). */
export function workflowSpine(wf: Workflow): Spine {
  const diagram = diagramSteps(wf);
  const steps: SpineStep[] = diagram.map((d) => ({
    index: d.step.index,
    capability: d.step.capability,
    layer: d.step.layer,
    symbol: capabilitySymbol(d.step.capability),
    purpose: d.step.purpose,
    role: d.role,
    condition: d.step.condition === undefined || d.step.condition === null ? null : String(d.step.condition),
    gates: gateRows(d.step).map((g) => g.action),
    failures: failureRows(d.step).map((f) => f.action),
    risk: d.step.effective.risk,
    workflowId: d.step.workflow_id ?? null,
    reads: [...new Set(producerSteps(wf, d.step).map((p) => p.index))].sort((a, b) => a - b),
    checkpointStep: d.checkpointStep,
  }));
  const byIndex = new Map(steps.map((s) => [s.index, s]));

  const rows: SpineRow[] = [];
  const rowOf = new Map<number, number>();
  for (const run of diagramRuns(diagram)) {
    const runSteps = run.steps.map((d) => byIndex.get(d.step.index)!);
    if (run.group === null) {
      for (const s of runSteps) {
        rowOf.set(s.index, rows.length);
        rows.push({ kind: 'step', step: s });
      }
      continue;
    }
    rows.push({ kind: 'fork', group: run.group, size: runSteps.length });
    for (const s of runSteps) rowOf.set(s.index, rows.length);
    rows.push({ kind: 'parallel', group: run.group, steps: runSteps });
    rows.push({ kind: 'join', group: run.group, join: joinText(run.join) });
  }

  const row = (n: number) => rowOf.get(n)!;
  const checkpointSpans: SpineSpan[] = steps
    .filter((s) => s.role === 'checkpoint')
    .flatMap((c) => {
      const relying = steps.filter((s) => s.role === 'mutating' && s.checkpointStep === c.index);
      if (relying.length === 0) return [];
      const last = relying.reduce((a, b) => (row(b.index) > row(a.index) ? b : a));
      return row(last.index) > row(c.index) ? [{ from: row(c.index), to: row(last.index), fromStep: c.index, toStep: last.index }] : [];
    });
  const rollbackSpans: SpineSpan[] = steps
    .filter((s) => s.role === 'rollback' && s.checkpointStep !== null)
    .filter((s) => row(s.index) > row(s.checkpointStep!))
    .map((s) => ({ from: row(s.checkpointStep!), to: row(s.index), fromStep: s.checkpointStep!, toStep: s.index }));

  const maxGates = Math.max(0, ...steps.map((s) => s.gates.length));
  const maxFailures = Math.max(0, ...steps.map((s) => s.failures.length));
  const lanes = {
    checkpoint: checkpointSpans.length > 0,
    rollback: rollbackSpans.length > 0,
    gate: steps.some((s) => s.gates.length > 0 || s.condition !== null),
    failure: maxFailures > 0,
    reads: steps.some((s) => s.reads.length > 0),
  };

  const has = (role: StepRole) => steps.some((s) => s.role === role);
  // Steps whose effective mutation flag is true but that are not drawn as
  // making the change (checkpoint, rollback, audit, persist): the page header
  // counts them as changing state, so the legend names them too.
  const writers = diagram.filter((d) => d.step.effective.mutation && d.role !== 'mutating').map((d) => d.step.index);
  const alsoChange = writers.length > 0 ? ` (${stepList(writers)} also ${writers.length === 1 ? 'changes' : 'change'} state)` : '';
  const legend: LegendItem[] = [];
  for (const role of ['checkpoint', 'mutating', 'verify', 'rollback'] as const) {
    if (has(role)) legend.push({ glyph: ROLE_GLYPH[role]!, label: role === 'mutating' ? `step ${ROLE_WORDS[role]}${alsoChange}` : `step ${ROLE_WORDS[role]}` });
  }
  if (steps.some((s) => s.condition !== null)) legend.push({ glyph: 'flow:condition', label: 'runs only when its condition holds (dashed tile)' });
  if (steps.some((s) => s.gates.length > 0)) legend.push({ glyph: 'diamond', label: 'step has gates' });
  const gateActions = [...new Set(steps.flatMap((s) => s.gates))];
  for (const a of gateActions) legend.push({ glyph: `gate:${a}`, label: GATE_WORDS[a] ?? `gate action ${a}` });
  const failActions = [...new Set(steps.flatMap((s) => s.failures))];
  for (const a of failActions) legend.push({ glyph: `fail:${a}`, label: FAILURE_WORDS[a] ?? `on failure, ${a}` });
  if (steps.some((s) => s.workflowId !== null)) legend.push({ glyph: 'flow:invoke', label: 'runs another workflow' });
  if (rows.some((r) => r.kind === 'fork')) {
    legend.push({ glyph: 'fork', label: 'parallel group starts' }, { glyph: 'flow:join', label: 'parallel group joins' });
  }
  legend.push({ glyph: 'pips', label: 'risk: 1 pip low, 2 medium, 3 high' });
  if (lanes.reads) legend.push({ glyph: 'flow:read', label: 'point at a step to see which steps it reads' });

  const cps = steps.filter((s) => s.role === 'checkpoint').map((s) => s.index);
  const rbs = steps.filter((s) => s.role === 'rollback').map((s) => s.index);
  const title = [
    `Steps of ${wf.id}: ${plural(steps.length, 'step', 'steps')}`,
    ...(cps.length > 0 ? [`checkpoint at ${stepList(cps)}`] : []),
    ...(rbs.length > 0 ? [`rollback at ${stepList(rbs)}`] : []),
  ].join(', ');

  const gated = steps.filter((s) => s.gates.length > 0).map((s) => s.index);
  const failing = steps.filter((s) => s.failures.length > 0).map((s) => s.index);
  const changing = steps.filter((s) => s.role === 'mutating').map((s) => s.index);
  const top = Math.max(...steps.map((s) => RISK_LEVEL[s.risk]));
  const topSteps = steps.filter((s) => RISK_LEVEL[s.risk] === top).map((s) => s.index);
  const clauses = [
    changing.length > 0
      ? `${stepList(changing)} ${changing.length === 1 ? 'makes the change' : 'make the changes'}` +
        (checkpointSpans.length > 0 ? ` after the checkpoint at ${stepList(checkpointSpans.map((c) => c.fromStep))}` : '')
      : writers.length > 0
        ? `only ${stepList(writers)} (${[...new Set(diagram.filter((d) => writers.includes(d.step.index)).map((d) => d.step.capability))].join(', ')}) ${writers.length === 1 ? 'changes' : 'change'} state`
        : 'no step changes state',
    ...(gated.length > 0 ? [`${stepList(gated)} ${gated.length === 1 ? 'has' : 'have'} gates`] : []),
    ...(failing.length > 0 ? [`${stepList(failing)} ${failing.length === 1 ? 'says' : 'say'} what to do on failure`] : []),
    `the highest step risk is ${steps.find((s) => RISK_LEVEL[s.risk] === top)!.risk}, at ${stepList(topSteps)}`,
  ];
  const caption = `Read top to bottom: ${clauses.slice(0, -1).join('; ')}; and ${clauses.at(-1)}.`;

  return { workflowId: wf.id, rows, steps, rowOf, checkpointSpans, rollbackSpans, lanes, maxGates, maxFailures, legend, title, caption };
}

/** What a screen reader hears for one spine row, after the step number and capability. */
export function spineStepWords(s: SpineStep): string {
  const parts = [`${s.layer} layer`];
  if (s.role !== 'plain') parts.push(ROLE_WORDS[s.role]);
  if (s.condition !== null) parts.push(`runs only if ${s.condition}`);
  if (s.gates.length > 0) parts.push(`${plural(s.gates.length, 'gate', 'gates')}: ${s.gates.join(', ')}`);
  if (s.failures.length > 0) parts.push(`on failure: ${s.failures.join(', ')}`);
  if (s.workflowId !== null) parts.push(`runs workflow ${s.workflowId}`);
  parts.push(`risk ${s.risk}`);
  if (s.reads.length > 0) parts.push(`reads ${stepList(s.reads)}`);
  return parts.join('; ');
}

/** The step map table of the Markdown copy (visual spec 3.3, F-W1 text equivalent). */
export function spineTable(spine: Spine): { headers: string[]; rows: string[][] } {
  return {
    headers: ['#', 'Capability', 'Layer', 'Role', 'Gates', 'On failure', 'Reads from', 'Risk'],
    rows: spine.steps.map((s) => [
      String(s.index),
      s.capability,
      s.layer,
      s.role === 'plain' ? '' : s.role,
      s.gates.join(', '),
      s.failures.join(', '),
      s.reads.join(', '),
      s.risk,
    ]),
  };
}

// ------------------------------------------------------- the data-flow grid

export interface DataFlowGrid {
  /** Steps that store an output, in step order: the grid's columns. */
  columns: { index: number; name: string }[];
  rows: { index: number; capability: string; cells: ('store' | 'read' | null)[] }[];
  /** How many (step, earlier step) reads there are. */
  reads: number;
  title: string;
  caption: string;
}

/** Which step reads which stored output (visual spec 3.3, F-W2). */
export function dataFlowGrid(wf: Workflow, spine: Spine = workflowSpine(wf)): DataFlowGrid {
  const columns = wf.steps.filter((s) => s.store_as).map((s) => ({ index: s.index, name: s.store_as! }));
  const rows = spine.steps.map((s) => ({
    index: s.index,
    capability: s.capability,
    cells: columns.map((c) => (c.index === s.index ? 'store' : s.reads.includes(c.index) ? 'read' : null)) as ('store' | 'read' | null)[],
  }));
  const reads = spine.steps.reduce((n, s) => n + s.reads.length, 0);
  const readers = spine.steps.filter((s) => s.reads.length > 0);
  const most = readers.reduce<(typeof readers)[number] | null>((a, b) => (a === null || b.reads.length > a.reads.length ? b : a), null);
  const caption =
    readers.length === 0
      ? `No step of ${wf.id} reads an earlier step's output.`
      : `${plural(readers.length, 'step reads', 'steps read')} the output of earlier steps, ${plural(reads, 'read', 'reads')} in all; step ${most!.index} (${most!.capability}) reads the most, from ${plural(most!.reads.length, 'step', 'steps')}.`;
  return { columns, rows, reads, title: 'Which step reads which stored output', caption };
}

/** "Step n reads from steps a, b", one line per reading step, for the Markdown copy. */
export function readsList(spine: Spine): string[] {
  return spine.steps.filter((s) => s.reads.length > 0).map((s) => `Step ${s.index} reads from ${stepList(s.reads)}.`);
}

// ---------------------------------------------------------------- the risk

export interface RiskSummary {
  steps: { index: number; capability: string; risk: Risk }[];
  highest: Risk;
  /** Steps at the highest risk. */
  highestSteps: number[];
  declared: Risk;
  computed: Risk | null;
  /** Declared, computed (when present) and highest step risk are equal. */
  agree: boolean;
  title: string;
  caption: string;
  /** Printed in place of the figure when declared, computed and step risk agree. */
  sentence: string;
}

function asRisk(v: unknown): Risk | null {
  return v === 'low' || v === 'medium' || v === 'high' ? v : null;
}

/** Declared and step risk (visual spec 3.3, F-W3). */
export function riskSummary(wf: Workflow): RiskSummary {
  const steps = wf.steps.map((s) => ({ index: s.index, capability: s.capability, risk: s.effective.risk }));
  const top = Math.max(...steps.map((s) => RISK_LEVEL[s.risk]));
  const highestSteps = steps.filter((s) => RISK_LEVEL[s.risk] === top).map((s) => s.index);
  const first = steps.find((s) => s.index === highestSteps[0])!;
  const highest = first.risk;
  const computed = isObj(wf.risk_propagation) ? asRisk(wf.risk_propagation.computed_risk) : null;
  const declared = wf.risk;
  const agree = declared === highest && (computed === null || computed === highest);
  const title = `Risk of ${wf.id}: declared ${declared}; highest step risk ${highest}, at step ${first.index} (${first.capability})`;
  const caption = agree
    ? computed !== null
      ? `Declared, computed and highest step risk are all ${highest}.`
      : `Declared and highest step risk are both ${highest}; the catalog gives no computed risk.`
    : `The catalog declares ${declared}; the highest step risk is ${highest}${computed !== null ? `; the computed risk is ${computed}` : ''}.`;
  // When the three agree, the per-step risk is already the risk column of
  // the step map (F-W1) and each step card, so the section is one sentence
  // (visual spec 1.1 rule 5; issue #125 review: three figures showed it).
  const sentence = `${caption.replace(/\.$/, '')}; the highest-risk step is step ${first.index} (${first.capability})${highestSteps.length > 1 ? `, with ${plural(highestSteps.length - 1, 'other', 'others')} at the same level` : ''}. The step map above gives each step's risk.`;
  return { steps, highest, highestSteps, declared, computed, agree, title, caption, sentence };
}

// --------------------------------------------------------------- the inputs

/** The caption of the inputs figure (visual spec 3.3, F-W4). */
export function inputsCaption(wf: Workflow): string {
  const rows = schemaRows(wf.inputs);
  const top = rows.filter((r) => r.depth === 0);
  const required = top.filter((r) => r.required).length;
  const nested = rows.length - top.length;
  return (
    `${plural(top.length, 'input', 'inputs')}, ${required} required (filled pin) and ${top.length - required} optional (outlined pin)` +
    (nested > 0 ? `, with ${plural(nested, 'named field', 'named fields')} inside them.` : '.')
  );
}

// ---------------------------------------------------------- the index strip

/** Distinct layers a workflow uses, in first-use order. */
export function layersUsed(wf: Workflow): string[] {
  return [...new Set(wf.steps.map((s) => s.layer))];
}

/** The accessible name of a workflow's strip on the index (visual spec 3.4, F-WI1). */
export function indexStripLabel(wf: Workflow): string {
  const cps = diagramSteps(wf)
    .filter((d) => d.role === 'checkpoint')
    .map((d) => d.step.index);
  return [
    plural(wf.steps.length, 'step', 'steps'),
    ...(cps.length > 0 ? [`checkpoint at ${stepList(cps)}`] : []),
    `uses layers ${layersUsed(wf).join(', ')}`,
  ].join('; ');
}
