// The data behind the domain page figures (visual spec 3.5) and the domains
// index (3.6). The page and its Markdown copy both call these functions, so
// the HTML caption and the copy's "**Figure:**" block say the same thing.
import type { DomainProfile } from '../data/profiles';
import type { Workflow } from '../data/workflows';
import { resolveGlyphKey } from '../pixel/keys';
import { diagramSteps, sortedTrustWeights } from './views';

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const andList = (xs: readonly string[]) => (xs.length <= 1 ? (xs[0] ?? '') : `${xs.slice(0, -1).join(', ')} and ${xs.at(-1)}`);

/** The glyph key of a domain: the profile key with `-` read as `_` (visual spec 2.2). */
export function domainGlyph(key: string): string {
  return `domain:${key.replace(/-/g, '_')}`;
}

/** A glyph key when it has a grid, else null, so a value with no glyph prints as words only. */
export function glyphOrNull(key: string): string | null {
  return resolveGlyphKey(key) === null ? null : key;
}

// ------------------------------------------------------------- F-D2 ladder

/** The risk levels a step can carry (Standard §4.1); `critical` never applies to a step. */
export const LADDER_LEVELS = ['low', 'medium', 'high'] as const;
export type LadderLevel = (typeof LADDER_LEVELS)[number];
export type Outcome = 'auto' | 'review' | 'human' | 'gap';

/** Order of the threshold enums in profile_schema.yaml (low < medium < high < critical). */
const RANK: Readonly<Record<string, number>> = { low: 0, medium: 1, high: 2, critical: 3 };

/**
 * What happens to a step at one risk level (visual spec 3.5, F-D2), read from
 * the field descriptions in profile_schema.yaml: require_human is the minimum
 * level that needs a person to carry it out, require_review the minimum level
 * that needs review, auto_approve the maximum level approved automatically.
 * A level none of them covers is a gap.
 */
export function ladderOutcome(thresholds: Obj, level: LadderLevel): Outcome {
  const at = (field: string): number | undefined => {
    const v = thresholds[field];
    return typeof v === 'string' && v in RANK ? RANK[v] : undefined;
  };
  const l = RANK[level]!;
  const human = at('require_human');
  if (human !== undefined && human <= l) return 'human';
  const review = at('require_review');
  if (review !== undefined && review <= l) return 'review';
  const auto = at('auto_approve');
  if (auto !== undefined && l <= auto) return 'auto';
  return 'gap';
}

export const OUTCOME_WORD: Readonly<Record<Outcome, string>> = { auto: 'Auto', review: 'Review', human: 'Human', gap: 'Not covered' };
export const OUTCOME_TEXT: Readonly<Record<Outcome, string>> = {
  auto: 'approved automatically',
  review: 'a person reviews it',
  human: 'a person carries it out',
  gap: 'no threshold covers it',
};
/** The approve:* glyph of each outcome; a gap has none. */
export const OUTCOME_GLYPH: Readonly<Record<Outcome, string | null>> = {
  auto: 'approve:auto',
  review: 'approve:review',
  human: 'approve:human',
  gap: null,
};
export const LEVEL_PIPS: Readonly<Record<LadderLevel, number>> = { low: 1, medium: 2, high: 3 };

export interface Ladder {
  rows: { level: LadderLevel; outcome: Outcome }[];
  blocked: string[];
}

export function approvalLadder(profile: Obj): Ladder | null {
  const t = profile.risk_thresholds;
  if (!isObj(t)) return null;
  return {
    rows: LADDER_LEVELS.map((level) => ({ level, outcome: ladderOutcome(t, level) })),
    blocked: Array.isArray(t.block_autonomous) ? t.block_autonomous.map(String) : [],
  };
}

/** The outcomes at low, medium and high as words, e.g. "auto, review, human". */
export function ladderKey(l: Ladder): string {
  return l.rows.map((r) => OUTCOME_WORD[r.outcome].toLowerCase()).join(', ');
}

export function ladderCaption(l: Ladder): string {
  const first = l.rows[0]!.outcome;
  const levels = l.rows.every((r) => r.outcome === first)
    ? `At every risk level ${OUTCOME_TEXT[first]}`
    : l.rows.map((r, i) => `${i === 0 ? 'At' : 'at'} ${r.level} risk ${OUTCOME_TEXT[r.outcome]}`).join('; ');
  const blocked =
    l.blocked.length === 0
      ? 'no capability is blocked from running on its own'
      : `${plural(l.blocked.length, 'capability', 'capabilities')} never ${l.blocked.length === 1 ? 'runs' : 'run'} on ${l.blocked.length === 1 ? 'its' : 'their'} own: ${andList(l.blocked)}`;
  return `${levels}, and ${blocked}.`;
}

// -------------------------------------------------------- F-D1 trust weights

export function trustCaption(profile: Obj): string {
  const w = sortedTrustWeights(profile);
  if (w.length === 0) return 'The profile gives no trust weights.';
  const top = w[0]!;
  const low = w.at(-1)!;
  if (w.length === 1) return `One source, ${top.source}, with weight ${top.weight.toFixed(2)}.`;
  return `${w.length} sources, from ${top.source} at ${top.weight.toFixed(2)} down to ${low.source} at ${low.weight.toFixed(2)}, on a scale from 0 to 1.`;
}

// ---------------------------------------------------- F-D3 checkpoint policy

/** The checkpoint_policy levels in schema order (profile_schema.yaml). */
export const POLICY_LEVELS = ['always', 'high_risk', 'medium_risk', 'never'] as const;
export const POLICY_WORD: Readonly<Record<string, string>> = { always: 'always', high_risk: 'high risk', medium_risk: 'medium risk', never: 'never' };

export interface CheckpointPolicy {
  triggers: { name: string; level: string }[];
  /** Levels that occur, in schema order, with how many triggers use each. */
  levels: { level: string; count: number }[];
}

export function checkpointPolicy(profile: Obj): CheckpointPolicy | null {
  const c = profile.checkpoint_policy;
  if (!isObj(c)) return null;
  const triggers = Object.entries(c).map(([name, level]) => ({ name, level: String(level) }));
  const order = [...POLICY_LEVELS, ...new Set(triggers.map((t) => t.level).filter((l) => !(POLICY_LEVELS as readonly string[]).includes(l)))];
  const levels = order
    .map((level) => ({ level, count: triggers.filter((t) => t.level === level).length }))
    .filter((l) => l.count > 0);
  return { triggers, levels };
}

export const policyWord = (level: string) => POLICY_WORD[level] ?? level.replace(/_/g, ' ');

/** "All 5 triggers: always" when one level is used (the 1.1.5 fallback), else null. */
export function checkpointHeader(p: CheckpointPolicy): string | null {
  return p.levels.length === 1 ? `All ${p.triggers.length} triggers: ${policyWord(p.levels[0]!.level)}` : null;
}

export function checkpointCaption(p: CheckpointPolicy): string {
  if (p.triggers.length === 0) return 'The profile names no checkpoint triggers.';
  if (p.levels.length === 1) {
    const level = p.levels[0]!.level;
    const all = `All ${p.triggers.length} triggers are set to ${policyWord(level)}`;
    return level === 'always' ? `${all}, so a checkpoint is made before each of them every time.` : `${all}.`;
  }
  return `${plural(p.triggers.length, 'trigger')}: ${andList(p.levels.map((l) => `${l.count} ${policyWord(l.level)}`))}.`;
}

// ----------------------------------------------------- F-D4 evidence policy

export interface EvidencePolicy {
  minimumConfidence: number | null;
  anchorTypes: string[];
  grounding: string[];
}

export function evidencePolicy(profile: Obj): EvidencePolicy | null {
  const e = profile.evidence_policy;
  if (!isObj(e)) return null;
  const n = Number(e.minimum_confidence);
  return {
    minimumConfidence: e.minimum_confidence === undefined || Number.isNaN(n) ? null : n,
    anchorTypes: Array.isArray(e.required_anchor_types) ? e.required_anchor_types.map(String) : [],
    grounding: Array.isArray(e.require_grounding) ? e.require_grounding.map(String) : [],
  };
}

export function evidenceCaption(e: EvidencePolicy): string {
  const parts = [
    e.minimumConfidence === null ? null : `a claim needs a confidence of at least ${e.minimumConfidence.toFixed(2)}`,
    e.anchorTypes.length > 0 ? `${plural(e.anchorTypes.length, 'anchor type')} ${e.anchorTypes.length === 1 ? 'is' : 'are'} expected` : null,
    e.grounding.length > 0 ? `${plural(e.grounding.length, 'capability', 'capabilities')} must cite evidence` : null,
  ].filter((x): x is string => x !== null);
  if (parts.length === 0) return 'The profile sets no evidence requirements.';
  const s = andList(parts);
  return `${s[0]!.toUpperCase()}${s.slice(1)}.`;
}

// ------------------------------------------------------ F-D5 domain sources

export interface DomainSource {
  name: string;
  type: string;
  trust: number;
}

/** domain_sources ranked by default_trust, highest first; ties keep file order. */
export function rankedSources(profile: Obj): DomainSource[] {
  const s = profile.domain_sources;
  if (!Array.isArray(s)) return [];
  return s
    .filter(isObj)
    .map((x) => ({ name: String(x.name ?? ''), type: String(x.type ?? ''), trust: Number(x.default_trust) }))
    .sort((a, b) => b.trust - a.trust);
}

export function sourcesCaption(s: DomainSource[]): string {
  if (s.length === 0) return 'The profile names no sources.';
  const types = new Set(s.map((x) => x.type)).size;
  const top = s.filter((x) => x.trust === s[0]!.trust).map((x) => x.name);
  return `${plural(s.length, 'source')} of ${plural(types, 'type')}; ${andList(top)} ${top.length === 1 ? 'has' : 'have'} the highest default trust, ${s[0]!.trust.toFixed(2)}.`;
}

// --------------------------------------------------------- F-D7 compliance

/** The status glyph of each compliance value (visual spec 3.5, F-D7). */
export const COMPLIANCE_GLYPH: Readonly<Record<string, string>> = { required: 'stamp', advisory_only: 'note', recommended: 'check' };
export const COMPLIANCE_WORD: Readonly<Record<string, string>> = { required: 'required', advisory_only: 'advisory only', recommended: 'recommended' };
const DAYS_PER_YEAR = 365;

export interface ComplianceRow {
  key: string;
  value: string;
  glyph: string | null;
  /** For a `*_days` number: the value in years to one decimal. */
  years?: number;
}

export function complianceRows(profile: Obj): ComplianceRow[] | null {
  const c = profile.compliance;
  if (!isObj(c)) return null;
  return Object.entries(c).map(([key, v]) => {
    if (typeof v === 'number' && key.endsWith('_days')) {
      return { key, value: `${v} days`, glyph: null, years: Math.round((v / DAYS_PER_YEAR) * 10) / 10 };
    }
    const value = String(v);
    return { key, value: COMPLIANCE_WORD[value] ?? value.replace(/_/g, ' '), glyph: COMPLIANCE_GLYPH[value] ?? null };
  });
}

export function complianceCaption(rows: ComplianceRow[]): string {
  const marks = rows.filter((r) => r.years === undefined);
  const counts = Object.entries(
    marks.reduce<Record<string, number>>((m, r) => ({ ...m, [r.value]: (m[r.value] ?? 0) + 1 }), {}),
  ).map(([v, n]) => `${n} ${v}`);
  const kept = rows
    .filter((r) => r.years !== undefined)
    .map((r) => `${r.key.replace(/_days$/, '').replace(/_/g, ' ')} lasts ${r.value}, about ${r.years!.toFixed(1)} years`);
  const parts = [marks.length > 0 ? `${plural(marks.length, 'standard')}: ${andList(counts)}` : null, ...kept].filter(Boolean) as string[];
  return parts.length === 0 ? 'The profile lists no compliance markers.' : `${parts.join('; ')}.`;
}

// --------------------------------------------------- F-D6 workflow placement

/** The reading of a workflow card: steps, risk, and where its checkpoints are. */
export function workflowCardCaption(wf: Workflow): string {
  const steps = diagramSteps(wf);
  const cps = steps.filter((d) => d.role === 'checkpoint').map((d) => d.step.index);
  const gated = steps.filter((d) => (d.step.gates?.length ?? 0) > 0).length;
  const parts = [
    `${plural(steps.length, 'step')} at ${wf.risk} risk`,
    cps.length === 0 ? 'no checkpoint step' : `a checkpoint at ${cps.length === 1 ? 'step' : 'steps'} ${andList(cps.map(String))}`,
    gated === 0 ? null : `${plural(gated, 'step')} with gates`,
  ].filter(Boolean) as string[];
  const s = andList(parts);
  return `${s[0]!.toUpperCase()}${s.slice(1)}.`;
}

/** A README H3 title as a workflow id: the "N." prefix removed, lower case, runs of other characters as `_`. */
export function headingWorkflowId(title: string): string {
  return title
    .replace(/^\s*\d+\.\s*/, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '');
}

export interface ReadmeParts {
  /** README sections before "Domain Profile" (all of them when it is absent). */
  before: string;
  /** The "Domain Profile" H2 element as rendered, or null when the README has none. */
  profileHeading: string | null;
  /** The rest of that section, its H3s turned into H4s, for the <details> under the figures. */
  profileBody: string | null;
  /** The README after that section, cut after each matched workflow H3. */
  segments: { html: string; after: string | null }[];
  /** Workflow ids with no matching H3 after the profile section, in profile order. */
  unplaced: string[];
}

const h2At = (html: string, from = 0) => {
  const i = html.slice(from).search(/<h2[\s>]/);
  return i === -1 ? -1 : i + from;
};

/** The start and end of the H2 section whose heading has this id; null when absent. */
export function h2Section(html: string, id: string): { start: number; end: number } | null {
  const m = new RegExp(`<h2[^>]*\\sid="${id}"[^>]*>`).exec(html);
  if (!m) return null;
  const next = h2At(html, m.index + m[0].length);
  return { start: m.index, end: next === -1 ? html.length : next };
}

/** Anchors of the domain READMEs the page reads (visual spec 3.10.6). */
export const DOMAIN_README_ANCHORS = { profile: 'domain-profile', workflows: 'available-workflows' } as const;

/**
 * Splits the README sections (everything after the lead) for the domain page
 * (visual spec 3.5 and 3.10.6). The figures go under the README's own
 * "Domain Profile" H2, where the README states the same values, so headings
 * keep the source's order; the section's text moves into a <details> under
 * the figures, with its H3s as H4s so the table of contents lists only the
 * figure headings. Each workflow card goes under its H3 in "Available
 * Workflows". Heading ids are kept.
 */
export function splitReadme(rest: string, workflowIds: readonly string[]): ReadmeParts {
  let before = '';
  let html = rest;
  let profileHeading: string | null = null;
  let profileBody: string | null = null;
  const p = h2Section(rest, DOMAIN_README_ANCHORS.profile);
  if (p) {
    before = rest.slice(0, p.start);
    const section = rest.slice(p.start, p.end);
    const close = section.indexOf('</h2>') + '</h2>'.length;
    profileHeading = section.slice(0, close);
    profileBody = section.slice(close).replace(/<(\/?)h3\b/g, '<$1h4');
    html = rest.slice(p.end);
  }
  const segments: ReadmeParts['segments'] = [];
  const placed = new Set<string>();
  const w = h2Section(html, DOMAIN_README_ANCHORS.workflows);
  let cursor = 0;
  if (w) {
    const body = html.slice(w.start, w.end);
    for (const m of body.matchAll(/<h3[^>]*>([\s\S]*?)<\/h3>/g)) {
      const id = headingWorkflowId(m[1]!.replace(/<[^>]*>/g, ''));
      if (!workflowIds.includes(id) || placed.has(id)) continue;
      const end = w.start + m.index! + m[0].length;
      segments.push({ html: html.slice(cursor, end), after: id });
      placed.add(id);
      cursor = end;
    }
  }
  segments.push({ html: html.slice(cursor), after: null });
  return { before, profileHeading, profileBody, segments, unplaced: workflowIds.filter((id) => !placed.has(id)) };
}

// ------------------------------------------- domains index (visual spec 3.6)

/** Floor and ceiling, to 0.05, of every trust weight of every profile: the shared axis of the dot strips. */
export function trustAxis(profiles: readonly DomainProfile[]): { min: number; max: number } {
  const all = profiles.flatMap((p) => sortedTrustWeights(p.profile).map((w) => w.weight));
  if (all.length === 0) return { min: 0, max: 1 };
  const step = 20; // 1 / 0.05
  const min = Math.floor(Math.min(...all) * step + 1e-9) / step;
  const max = Math.ceil(Math.max(...all) * step - 1e-9) / step;
  return { min, max: max > min ? max : min + 1 / step };
}

/**
 * One sentence that groups the profiles by their outcomes at low, medium and
 * high risk (visual spec 3.6), e.g. "From low to high risk, N profiles go
 * auto, review, human; healthcare is human at every level."
 */
export function thresholdsSentence(profiles: readonly DomainProfile[]): string {
  const groups = new Map<string, string[]>();
  for (const p of profiles) {
    const l = approvalLadder(p.profile);
    if (!l) continue;
    const first = l.rows[0]!.outcome;
    const key = l.rows.every((r) => r.outcome === first) ? `${OUTCOME_WORD[first].toLowerCase()} at every level` : ladderKey(l);
    groups.set(key, [...(groups.get(key) ?? []), p.key]);
  }
  if (groups.size === 0) return 'No profile sets risk thresholds.';
  const parts = [...groups.entries()]
    .sort((a, b) => b[1].length - a[1].length)
    .map(([key, keys]) => {
      const verb = key.endsWith('every level') ? 'is' : 'goes';
      return keys.length === 1 ? `${keys[0]} ${verb} ${key}` : `${keys.length} profiles ${verb === 'is' ? 'are' : 'go'} ${key}`;
    });
  return `From low to high risk, ${parts.join('; ')}.`;
}

export function profilesCaption(profiles: readonly DomainProfile[]): string {
  const { min, max } = trustAxis(profiles);
  const counts = profiles.map((p) => sortedTrustWeights(p.profile).length);
  return `${plural(profiles.length, 'profile')}, each with ${Math.min(...counts)} to ${Math.max(...counts)} trust weights, drawn on one scale from ${min.toFixed(2)} to ${max.toFixed(2)}.`;
}
