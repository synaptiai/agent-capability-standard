// Figures a domain page draws from its README's own blocks (visual spec 1.1
// rule 3 and 3.10): the "Capability Usage" examples, each read from the YAML
// fence under its H3 and set against the profile's evidence policy, and the
// "Capabilities used" list of a workflow the profile proposes but no catalog
// defines. The page and its Markdown copy both call these functions.
import type { Code, Heading, List, RootContent } from 'mdast';
import { toString } from 'mdast-util-to-string';
import { parse } from 'yaml';
import { loadOntology } from '../data/ontology';
import { headingText, parseMarkdown } from './anchors';
import { evidencePolicy, headingWorkflowId } from './domain-figures';
import { htmlHeadings } from './inject';
import { andList, plural } from './words';

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);

/** The README heading the usage examples sit under. */
export const USAGE_HEADING = 'Capability Usage';

/** The blocks of the H2 or H3 section whose text is exactly `title`, or null. */
function section(nodes: RootContent[], i: number): RootContent[] {
  const depth = (nodes[i] as Heading).depth;
  const end = nodes.findIndex((n, j) => j > i && n.type === 'heading' && n.depth <= depth);
  return nodes.slice(i + 1, end === -1 ? undefined : end);
}

export interface UsageExample {
  /** The H3 text, as the page renders it. */
  heading: string;
  capability: string;
  domain: string | null;
  inputs: string[];
  outputs: string[];
  /** Evidence anchor types in the example's output, once each, in order. */
  anchors: string[];
}

/**
 * One example per H3 of the README's "Capability Usage" section whose first
 * fence is YAML with a single top-level key that is an ontology capability.
 * Anything else is skipped with a build warning, so a prose edit cannot
 * break the build. A README listed in NO_USAGE_SECTION has no such section
 * and gives []; any other README without one, or a listed README that gains
 * one, fails the build, so the list cannot drift.
 */
/** Domain READMEs written without a "Capability Usage" section (they get no usage figures). */
export const NO_USAGE_SECTION: ReadonlySet<string> = new Set([
  'docs/domains/data-analysis/README.md',
  'docs/domains/healthcare/README.md',
  'docs/domains/manufacturing/README.md',
  'docs/domains/personal-assistant/README.md',
]);

export function capabilityUsage(readmeText: string, where: string): UsageExample[] {
  const nodes = parseMarkdown(readmeText).children;
  const h2 = nodes.findIndex((n) => n.type === 'heading' && n.depth === 2 && headingText(n).trim() === USAGE_HEADING);
  const exempt = NO_USAGE_SECTION.has(where);
  if (h2 === -1) {
    if (exempt) return [];
    throw new Error(`${where}: no "## ${USAGE_HEADING}" section; add one, or add the README to NO_USAGE_SECTION in domain-usage.ts`);
  }
  if (exempt) throw new Error(`${where}: has a "## ${USAGE_HEADING}" section; remove it from NO_USAGE_SECTION in domain-usage.ts`);
  const known = new Set(loadOntology().capabilities.map((c) => c.id));
  const body = section(nodes, h2);
  const out: UsageExample[] = [];
  body.forEach((n, i) => {
    if (n.type !== 'heading' || n.depth !== 3) return;
    const heading = headingText(n).trim();
    const fence = section(body, i).find((b): b is Code => b.type === 'code');
    let value: unknown;
    let yamlError = '';
    try {
      value = fence && /^ya?ml$/.test(fence.lang ?? '') ? parse(fence.value) : null;
    } catch (e) {
      value = null;
      yamlError = ` (its YAML does not parse: ${(e as Error).message.split('\n')[0]})`;
    }
    const keys = isObj(value) ? Object.keys(value) : [];
    const capability = keys[0];
    const spec = capability ? (value as Obj)[capability] : null;
    if (keys.length !== 1 || !capability || !known.has(capability) || !isObj(spec)) {
      console.warn(`${where}: "${heading}" under ${USAGE_HEADING} has no single-capability YAML fence${yamlError}; no figure`);
      return;
    }
    const output = isObj(spec.output) ? spec.output : {};
    const anchors = Array.isArray(output.evidence_anchors)
      ? [...new Set(output.evidence_anchors.filter(isObj).map((a) => String(a.type ?? '')).filter(Boolean))]
      : [];
    out.push({
      heading,
      capability,
      domain: typeof spec.domain === 'string' ? spec.domain : null,
      inputs: isObj(spec.input) ? Object.keys(spec.input) : [],
      outputs: Object.keys(output),
      anchors,
    });
  });
  return out;
}

export interface UsageCheck {
  /** The profile's required anchor types, each with whether the example carries it. */
  required: { type: string; present: boolean }[];
  /** Anchor types the example carries that the profile does not require. */
  other: string[];
  /** Whether the profile's require_grounding lists the capability. */
  mustCite: boolean;
}

export function usageCheck(u: UsageExample, profile: Obj): UsageCheck {
  const e = evidencePolicy(profile);
  const required = (e?.anchorTypes ?? []).map((type) => ({ type, present: u.anchors.includes(type) }));
  return {
    required,
    other: u.anchors.filter((a) => !(e?.anchorTypes ?? []).includes(a)),
    mustCite: (e?.grounding ?? []).includes(u.capability),
  };
}

export function usageTitle(u: UsageExample): string {
  return `${u.capability}${u.domain ? ` with domain ${u.domain}` : ''}, against the profile's evidence policy`;
}

export function usageCaption(u: UsageExample, c: UsageCheck, key: string): string {
  const io = `The example reads ${plural(u.inputs.length, 'input')} and returns ${plural(u.outputs.length, 'output')}`;
  const have = c.required.filter((r) => r.present).length;
  const missing = c.required.filter((r) => !r.present).map((r) => r.type);
  const anchors =
    c.required.length === 0
      ? `the ${key} profile requires no anchor types`
      : `its evidence anchors include ${have} of the ${c.required.length} anchor types the ${key} profile requires${missing.length > 0 ? ` (not ${andList(missing)})` : ''}`;
  const cite = `the profile ${c.mustCite ? 'requires' : 'does not require'} ${u.capability} to cite evidence`;
  return `${io}; ${anchors}; ${cite}.`;
}

/**
 * The capabilities a README lists under "Capabilities used" for the workflow
 * whose H3 slugs to `workflowId`, in list order; null when there is no such
 * list or any item does not start with a backticked ontology id.
 */
export function listedCapabilities(readmeText: string, workflowId: string): string[] | null {
  const nodes = parseMarkdown(readmeText).children;
  const i = nodes.findIndex((n) => n.type === 'heading' && n.depth === 3 && headingWorkflowId(headingText(n)) === workflowId);
  if (i === -1) return null;
  const body = section(nodes, i);
  const lead = body.findIndex((b) => b.type === 'paragraph' && /^Capabilities used:?$/.test(toString(b).trim()));
  const list = lead === -1 ? undefined : body.slice(lead + 1).find((b): b is List => b.type === 'list');
  if (!list) return null;
  const known = new Set(loadOntology().capabilities.map((c) => c.id));
  const ids = list.children.map((item) => {
    const first = item.children[0];
    const code = first && first.type === 'paragraph' ? first.children[0] : undefined;
    return code && code.type === 'inlineCode' ? code.value : null;
  });
  return ids.length > 0 && ids.every((x): x is string => x !== null && known.has(x)) ? ids : null;
}

export function proposedCaption(ids: readonly string[]): string {
  const ontology = loadOntology();
  const layers = new Set(ids.map((id) => ontology.capabilities.find((c) => c.id === id)!.layer));
  const cp = ids.flatMap((id, k) => (id === 'checkpoint' ? [k + 1] : []));
  const where = cp.length === 0 ? 'no checkpoint' : `a checkpoint at position ${andList(cp.map(String))}`;
  return `The guide lists ${plural(ids.length, 'capability', 'capabilities')} from ${plural(layers.size, 'layer')}, with ${where}; no catalog defines the workflow's steps yet, so it has no step map, risk or bindings.`;
}

/** The README H2 the profile's compliance panel goes under when the README has it (its GitHub id). */
export const COMPLIANCE_ANCHOR = 'regulatory-compliance';

/** The headings of the usage examples whose figure no piece places (`placed`: each piece's `after`). */
export function unplacedUsage(usage: readonly UsageExample[], placed: readonly (string | null)[]): string[] {
  return usage.filter((u) => !placed.includes(`usage:${u.heading}`)).map((u) => u.heading);
}

/**
 * Rendered README HTML cut after each heading `pick` names, so a figure can
 * follow the heading. Pieces keep document order; `after` is what `pick`
 * returned for the heading a piece ends with, or null for the last piece.
 */
export function cutAfter(html: string, pick: (h: { level: number; id: string; text: string }) => string | null): { html: string; after: string | null }[] {
  const out: { html: string; after: string | null }[] = [];
  let last = 0;
  for (const h of htmlHeadings(html)) {
    const key = pick(h);
    if (key === null) continue;
    out.push({ html: html.slice(last, h.end), after: key });
    last = h.end;
  }
  out.push({ html: html.slice(last), after: null });
  return out;
}
