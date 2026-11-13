// The figures of a composed skill's page (skills/<dir>/SKILL.md for a
// directory in COMPOSED_SKILLS), drawn from data and placed under the
// skill's own H2s. SKILL.md files carry no diagrams, because agents load
// them into context; the site draws these instead (issue #125).
//
// A skill that runs a catalog workflow gets that workflow's parts, linked to
// the workflow's page:
// - Procedure: the step map (F-W1), since the procedure is the workflow's
//   steps in prose.
// - Output Contract: the data flow (F-W2); the contract's `steps` holds each
//   step's output under its `store_as`.
// - Safety Constraints: the step risks (F-W3) when the declared, computed
//   and highest step risk differ, otherwise one sentence, as on the
//   workflow page.
// - Preconditions (when the skill has that H2): every step that has a
//   condition or gates, needs a checkpoint before it or needs approval.
// - Verification: the steps whose stored output each check names, when
//   three or more checks name one.
// A skill with no catalog workflow gets figures from its own text:
// - Procedure: the field names each step uses (F-C7), when two or more
//   steps use one.
// - Examples: the capabilities each example's output matched, with their
//   confidence, when the examples' outputs list them.
// - Output Contract: the scorecard checks by checklist family, when the
//   contract has a `scorecard` whose ids are the H4s of the skill's
//   CHECKLIST.md.
import { parse } from 'yaml';
import { loadOntology } from '../data/ontology';
import { COMPOSED_SKILLS } from '../data/skills';
import { loadWorkflows, type Workflow } from '../data/workflows';
import { procedureMap, procedureMapIsFigure, type ProcedureMap } from './capability-figures';
import { headingText, parseMarkdown } from './anchors';
import { sectionBlocks, sectionFence } from './md-sections';
import { readRepoFile, TRACKED_FILES } from './repo';
import { capabilitySymbol, gateRows } from './views';
import { riskSummary } from './workflow-figures';
import type { Code, Heading } from 'mdast';
import { plural } from './words';


// ------------------------------------------------------------ example matches

export interface ExampleMatch {
  id: string;
  confidence: number;
  /** The reasoning starts "Auto-added": the skill added the step for safety, not from the task's words. */
  auto: boolean;
  domain: string | null;
}

export interface ExampleMatches {
  examples: { n: number; title: string; task: string; matches: ExampleMatch[]; gaps: number }[];
}

/** H3 headings under "## Examples" that start "Example"; none when the skill has no such H2. */
function exampleHeadings(skillText: string, where: string): string[] {
  if (!parseMarkdown(skillText).children.some((n) => n.type === 'heading' && n.depth === 2 && headingText(n).trim() === 'Examples')) return [];
  return sectionBlocks(skillText, 'Examples', where)
    .filter((n): n is Heading => n.type === 'heading' && n.depth === 3)
    .map((h) => headingText(h).trim())
    .filter((t) => t.startsWith('Example'));
}

/**
 * For each example, the task its input fence gives and the capabilities its
 * output fence lists under `capabilities:`, each with its confidence. Empty
 * when an example's output has no such list.
 */
export function exampleMatches(skillText: string, where: string): ExampleMatches {
  const o = loadOntology();
  const examples: ExampleMatches['examples'] = [];
  for (const [k, heading] of exampleHeadings(skillText, where).entries()) {
    const fences = sectionBlocks(skillText, heading, where).filter((n): n is Code => n.type === 'code' && n.lang === 'yaml');
    if (fences.length < 2) return { examples: [] };
    const input = parse(fences[0]!.value) as Record<string, unknown> | null;
    const output = parse(fences[1]!.value) as Record<string, unknown> | null;
    const caps = output?.capabilities;
    if (!Array.isArray(caps) || caps.length === 0) return { examples: [] };
    const matches = caps.map((c: Record<string, unknown>) => {
      const id = String(c.id);
      if (!o.byId.has(id)) throw new Error(`${where}: ${heading} matches ${id}, which is not a capability`);
      const confidence = Number(c.confidence);
      if (!(confidence >= 0 && confidence <= 1)) throw new Error(`${where}: ${heading} gives ${id} confidence ${String(c.confidence)}`);
      return { id, confidence, auto: /^Auto-added\b/i.test(String(c.reasoning ?? '')), domain: typeof c.domain === 'string' ? c.domain : null };
    });
    const gaps = Array.isArray(output?.gaps) ? output.gaps.length : 0;
    examples.push({ n: k + 1, title: heading.replace(/^Example \d+:\s*/, ''), task: String(input?.task_description ?? ''), matches, gaps });
  }
  return { examples };
}

export function exampleMatchesIsFigure(m: ExampleMatches): boolean {
  return m.examples.length > 0 && m.examples.reduce((k, e) => k + e.matches.length, 0) >= 3;
}

export function exampleMatchesTitle(dir: string): string {
  return `The capabilities each ${dir} example matched, with their confidence`;
}

export function exampleMatchesCaption(m: ExampleMatches): string {
  const all = m.examples.flatMap((e) => e.matches);
  const auto = all.filter((x) => x.auto);
  const low = [...all].sort((a, b) => a.confidence - b.confidence)[0]!;
  const gaps = m.examples.reduce((k, e) => k + e.gaps, 0);
  return (
    `The ${plural(m.examples.length, 'example', 'examples')} match ${plural(all.length, 'capability', 'capabilities')} in all, at confidence ${low.confidence} to ${Math.max(...all.map((x) => x.confidence))}; ` +
    (auto.length === 0
      ? 'none was added for safety'
      : `${plural(auto.length, 'was', 'were')} added for safety rather than matched from the task (${[...new Set(auto.map((x) => x.id))].join(', ')})`) +
    `, and ${gaps === 0 ? 'no example reports a gap' : plural(gaps, 'gap is', 'gaps are') + ' reported'}.`
  );
}

// ------------------------------------------------------------ scorecard families

export interface ScoreFamily {
  /** The checklist's letter for the family (A, B, ...). */
  letter: string;
  name: string;
  /** The id prefix the checklist gives in parentheses, e.g. "ORG/GOV". */
  code: string;
  checks: { id: string; title: string }[];
}

export interface Scorecard {
  checklist: string;
  families: ScoreFamily[];
  ratings: string[];
}

/**
 * The checks the Output Contract's `scorecard` rates, grouped by the
 * checklist family they sit under in the skill's CHECKLIST.md ("### A) Name
 * (CODE)" over "#### ID — Title"), and the ratings the contract allows. Null
 * when the contract has no scorecard or the skill has no checklist. Throws
 * when the two disagree on the ids or the ratings differ between checks.
 */
export function scorecard(dir: string, skillText: string, where: string): Scorecard | null {
  const checklist = `skills/${dir}/CHECKLIST.md`;
  if (!TRACKED_FILES.has(checklist)) return null;
  let contract: Record<string, unknown> | null;
  try {
    contract = parse(sectionFence(skillText, 'Output Contract', 0, where).value) as Record<string, unknown> | null;
  } catch {
    return null;
  }
  const card = contract?.scorecard;
  if (typeof card !== 'object' || card === null || Array.isArray(card)) return null;
  const ids = Object.keys(card);
  const ratingSets = Object.values(card).map((v) => String(v).split('|').map((s) => s.trim()));
  const ratings = ratingSets[0]!;
  if (ratingSets.some((r) => r.join('|') !== ratings.join('|'))) throw new Error(`${where}: the scorecard's checks allow different ratings`);
  const families: ScoreFamily[] = [];
  for (const node of parseMarkdown(readRepoFile(checklist)).children) {
    if (node.type !== 'heading') continue;
    const t = headingText(node).trim();
    const fam = node.depth === 3 ? /^([A-Z])\)\s+(.+?)\s+\(([^)]+)\)$/.exec(t) : null;
    if (fam) {
      families.push({ letter: fam[1]!, name: fam[2]!, code: fam[3]!, checks: [] });
      continue;
    }
    const check = node.depth === 4 ? /^([A-Z]+-\d+)\s+—\s+(.+)$/.exec(t) : null;
    if (check && families.length > 0) families.at(-1)!.checks.push({ id: check[1]!, title: check[2]! });
  }
  const listed = families.flatMap((f) => f.checks.map((c) => c.id));
  const missing = ids.filter((id) => !listed.includes(id));
  const extra = listed.filter((id) => !ids.includes(id));
  if (missing.length > 0 || extra.length > 0) {
    throw new Error(`${where}: the scorecard and ${checklist} disagree (only in the scorecard: ${missing.join(', ') || 'none'}; only in the checklist: ${extra.join(', ') || 'none'})`);
  }
  return { checklist, families: families.filter((f) => f.checks.length > 0), ratings };
}

export function scorecardTitle(sc: Scorecard): string {
  const n = sc.families.reduce((k, f) => k + f.checks.length, 0);
  return `The ${n} checks of the scorecard, by checklist family`;
}

export function scorecardCaption(sc: Scorecard): string {
  const n = sc.families.reduce((k, f) => k + f.checks.length, 0);
  const most = Math.max(...sc.families.map((f) => f.checks.length));
  const top = sc.families.filter((f) => f.checks.length === most).map((f) => f.name);
  const ratings = sc.ratings.length > 1 ? `${sc.ratings.slice(0, -1).join(', ')} or ${sc.ratings.at(-1)}` : sc.ratings[0];
  return `The scorecard rates each of ${n} checks as ${ratings}; the checklist sorts them into ${sc.families.length} families, and ${top.join(' and ')} ${top.length === 1 ? 'has' : 'have'} the most (${most}).`;
}

// ------------------------------------------------------------ guarded steps

export interface GuardedStep {
  index: number;
  capability: string;
  layer: string;
  symbol: string;
  /** The step's `condition`, as written, or null. */
  condition: string | null;
  gates: { when: string; action: string }[];
  checkpoint: boolean;
  approval: boolean;
}

/** The steps of a workflow that have a condition or gates, or need a checkpoint before them or approval. */
export function guardedSteps(wf: Workflow): GuardedStep[] {
  return wf.steps
    .map((s) => ({
      index: s.index,
      capability: s.capability,
      layer: s.layer,
      symbol: capabilitySymbol(s.capability),
      condition: typeof s.condition === 'string' && s.condition.trim() !== '' ? s.condition.trim() : null,
      gates: gateRows(s).map((g) => ({ when: g.when, action: g.action })),
      checkpoint: s.effective.checkpoint.needed,
      approval: s.effective.requires_approval,
    }))
    .filter((g) => g.condition !== null || g.gates.length > 0 || g.checkpoint || g.approval);
}

export function guardedStepsTitle(wf: Workflow): string {
  return `The guarded steps of ${wf.id}: conditions, gates, checkpoint and approval`;
}

const stepWords = (xs: number[]) => (xs.length === 1 ? `step ${xs[0]}` : `steps ${xs.slice(0, -1).join(', ')} and ${xs.at(-1)}`);

export function guardedStepsCaption(wf: Workflow, g: GuardedStep[]): string {
  const parts: string[] = [];
  const cond = g.filter((s) => s.condition !== null).map((s) => s.index);
  const gated = g.filter((s) => s.gates.length > 0).map((s) => s.index);
  const cp = g.filter((s) => s.checkpoint).map((s) => s.index);
  const ap = g.filter((s) => s.approval).map((s) => s.index);
  if (cond.length > 0) parts.push(`${stepWords(cond)} ${cond.length === 1 ? 'runs' : 'run'} only when a condition holds`);
  if (gated.length > 0) parts.push(`${stepWords(gated)} ${gated.length === 1 ? 'has' : 'have'} gates`);
  if (cp.length > 0) parts.push(`${stepWords(cp)} ${cp.length === 1 ? 'needs' : 'need'} a checkpoint before ${cp.length === 1 ? 'it' : 'them'}`);
  if (ap.length > 0) parts.push(`${stepWords(ap)} ${ap.length === 1 ? 'needs' : 'need'} approval`);
  return `${plural(g.length, 'step', 'steps')} of ${wf.steps.length} ${g.length === 1 ? 'is' : 'are'} guarded in the catalog: ${parts.slice(0, -1).join('; ')}${parts.length > 1 ? '; and ' : ''}${parts.at(-1)}.`;
}

// ------------------------------------------------------------ checks against steps

export interface CheckSteps {
  checks: { n: number; title: string; steps: number[] }[];
}

/**
 * Each checkbox item of the skill's Verification section, with the steps of
 * the workflow whose `store_as` name it uses as a word (`classify_out`).
 * A word match, which the caption states, not a reading of the check.
 */
export function checkSteps(wf: Workflow, skillText: string): CheckSteps {
  const lines = skillText.split('\n');
  const start = lines.findIndex((l) => /^## Verification\s*$/.test(l));
  if (start === -1) return { checks: [] };
  const end = lines.findIndex((l, i) => i > start && /^## /.test(l));
  const items = lines.slice(start + 1, end === -1 ? undefined : end).flatMap((l) => /^\s*[-*] \[[ xX]\]\s+(.*)$/.exec(l)?.[1] ?? []);
  const word = (name: string) => new RegExp(`(?<![A-Za-z0-9_])${name}(?![A-Za-z0-9_])`);
  return {
    checks: items.map((raw, i) => {
      const bold = /^\*\*(.+?)\*\*/.exec(raw)?.[1];
      const text = raw.replace(/\*\*/g, '').replace(/`/g, '');
      return { n: i + 1, title: (bold ?? text.split(/\s+/).slice(0, 6).join(' ')).replace(/:$/, ''), steps: wf.steps.filter((s) => s.store_as && word(s.store_as).test(raw)).map((s) => s.index) };
    }),
  };
}

export function checkStepsIsFigure(c: CheckSteps): boolean {
  return c.checks.filter((k) => k.steps.length > 0).length >= 3;
}

export function checkStepsTitle(wf: Workflow): string {
  return `The steps of ${wf.id} whose output each verification check names`;
}

export function checkStepsCaption(wf: Workflow, c: CheckSteps): string {
  const naming = c.checks.filter((k) => k.steps.length > 0);
  const named = new Set(naming.flatMap((k) => k.steps));
  const stored = wf.steps.filter((s) => s.store_as).length;
  return `${naming.length} of the ${plural(c.checks.length, 'check', 'checks')} name a step's stored output as a word; together they name ${named.size} of the ${stored} outputs the steps store (a match on the output's name, not a reading of the check).`;
}

// ------------------------------------------------------------ placement

export type SkillFigure =
  | { kind: 'spine'; wf: Workflow }
  | { kind: 'flow'; wf: Workflow }
  | { kind: 'risk'; wf: Workflow }
  | { kind: 'sentence'; text: string }
  | { kind: 'procedure'; map: ProcedureMap }
  | { kind: 'examples'; matches: ExampleMatches }
  | { kind: 'scorecard'; card: Scorecard }
  | { kind: 'guards'; wf: Workflow; steps: GuardedStep[] }
  | { kind: 'checks'; wf: Workflow; checks: CheckSteps };

/** The workflow a composed skill runs, or undefined. */
export function skillWorkflow(dir: string): Workflow | undefined {
  const id = COMPOSED_SKILLS[dir];
  return id ? loadWorkflows().byId.get(id) : undefined;
}

/**
 * The figures of a composed skill's page, keyed by the GitHub id of the H2
 * they go under, in page order within each key.
 */
export function composedSkillFigures(dir: string, skillText: string, where: string): Record<string, SkillFigure[]> {
  const out: Record<string, SkillFigure[]> = {};
  const add = (key: string, f: SkillFigure) => (out[key] ??= []).push(f);
  const wf = skillWorkflow(dir);
  if (wf) {
    const guarded = guardedSteps(wf);
    if (/^## Preconditions \(hard gates\)\s*$/m.test(skillText) && guarded.length > 0) add('preconditions-hard-gates', { kind: 'guards', wf, steps: guarded });
    add('procedure', { kind: 'spine', wf });
    add('output-contract', { kind: 'flow', wf });
    const checks = checkSteps(wf, skillText);
    if (checkStepsIsFigure(checks)) add('verification', { kind: 'checks', wf, checks });
    const r = riskSummary(wf);
    add('safety-constraints', r.agree ? { kind: 'sentence', text: r.sentence } : { kind: 'risk', wf });
    return out;
  }
  const map = procedureMap(skillText, where);
  if (procedureMapIsFigure(map)) add('procedure', { kind: 'procedure', map });
  const card = scorecard(dir, skillText, where);
  if (card) add('output-contract', { kind: 'scorecard', card });
  const matches = exampleMatches(skillText, where);
  if (exampleMatchesIsFigure(matches)) add('examples', { kind: 'examples', matches });
  return out;
}

/** The figures in page order, with the H2 text each goes under, for the Markdown copy. */
export const SKILL_HEADINGS: Readonly<Record<string, string>> = {
  'preconditions-hard-gates': 'Preconditions (hard gates)',
  procedure: 'Procedure',
  verification: 'Verification',
  'output-contract': 'Output Contract',
  'safety-constraints': 'Safety Constraints',
  examples: 'Examples',
};
