// Pure functions that turn the loaded data into what the generated pages show.
// The templates stay thin and the tests check these functions directly.
import { parse, stringify } from 'yaml';
import { loadOntology, EDGE_TYPES, type Capability, type EdgeType, type EdgeTypeInfo, type Ontology } from '../data/ontology';
import { loadProfiles, type DomainProfile } from '../data/profiles';
import { COMPOSED_SKILLS } from '../data/skills';
import { loadWorkflows, type Step, type Workflow } from '../data/workflows';
import { readRepoFile, TRACKED_FILES } from './repo';

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);

/** Plain words for each edge type, read from the target's side and from the source's side. */
export const EDGE_LABELS: Record<EdgeType, { out: string; in: string }> = {
  requires: { out: 'Must run before', in: 'Must run after' },
  soft_requires: { out: 'Recommended before', in: 'Recommended after' },
  enables: { out: 'Unlocks', in: 'Unlocked by' },
  precedes: { out: 'Comes before, when both are present', in: 'Comes after, when both are present' },
  conflicts_with: { out: 'May not share a parallel group with', in: 'May not share a parallel group with' },
  alternative_to: { out: 'Can substitute for', in: 'Can be substituted by' },
  specializes: { out: 'Specializes', in: 'Specialized by' },
};

// ---------------------------------------------------------------- contracts

export interface SchemaRow {
  /** Dotted path from the top of the schema, e.g. `merged.meta`. */
  path: string;
  name: string;
  /** 0 for a top-level field, 1 for a field of a top-level object. */
  depth: number;
  type: string;
  required: boolean;
  description: string;
  /** enum, minimum, maximum, default and format, in plain words. */
  constraints: string[];
  /** A repository path the field refers to (`ref`), if any. */
  ref?: string;
  /** Schema nested deeper than the table shows, as YAML. */
  nested?: string;
}

function typeOf(s: Obj): string {
  const t = typeof s.type === 'string' ? s.type : 'any';
  if (t === 'array' && isObj(s.items) && typeof s.items.type === 'string') return `array of ${s.items.type}`;
  return t;
}

function constraintsOf(s: Obj): string[] {
  const c: string[] = [];
  if (Array.isArray(s.enum)) c.push(`One of: ${s.enum.map(String).join(', ')}`);
  if (s.minimum !== undefined && s.maximum !== undefined) c.push(`From ${String(s.minimum)} to ${String(s.maximum)}`);
  else if (s.minimum !== undefined) c.push(`At least ${String(s.minimum)}`);
  else if (s.maximum !== undefined) c.push(`At most ${String(s.maximum)}`);
  if (s.default !== undefined) c.push(`Default: ${JSON.stringify(s.default)}`);
  if (typeof s.format === 'string') c.push(`Format: ${s.format}`);
  return c;
}

function hasStructure(s: Obj): boolean {
  return isObj(s.properties) || (isObj(s.items) && (isObj(s.items.properties) || isObj(s.items.items)));
}

/**
 * Rows of a contract table. Top-level fields are rows; the fields of a
 * top-level object are rows one level in; anything deeper is shown as YAML.
 * `required` may be a list on the parent (the ontology's form) or a boolean on
 * the field (the form workflow `inputs` use).
 */
export function schemaRows(properties: unknown, parentRequired: unknown = []): SchemaRow[] {
  const rows: SchemaRow[] = [];
  const walk = (props: unknown, required: unknown, depth: number, prefix: string): void => {
    if (!isObj(props)) return;
    const requiredList = Array.isArray(required) ? required.map(String) : [];
    for (const [name, raw] of Object.entries(props)) {
      const s = isObj(raw) ? raw : {};
      const path = prefix === '' ? name : `${prefix}.${name}`;
      const row: SchemaRow = {
        path,
        name,
        depth,
        type: typeOf(s),
        required: requiredList.includes(name) || s.required === true,
        description: typeof s.description === 'string' ? s.description.trim() : '',
        constraints: constraintsOf(s),
      };
      if (typeof s.ref === 'string') row.ref = s.ref;
      rows.push(row);
      if (!hasStructure(s)) continue;
      if (depth === 0 && isObj(s.properties) && !isObj(s.items)) {
        walk(s.properties, s.required, depth + 1, path);
      } else {
        const inner = isObj(s.properties) ? { properties: s.properties, ...(s.required ? { required: s.required } : {}) } : { items: s.items };
        row.nested = stringify(inner).trimEnd();
      }
    }
  };
  walk(properties, parentRequired, 0, '');
  return rows;
}

export function contractRows(schema: Obj): SchemaRow[] {
  return schemaRows(schema.properties, schema.required);
}

// --------------------------------------------------------------- tile symbols

const VOWELS = new Set(['a', 'e', 'i', 'o', 'u']);

/**
 * Two-letter symbols for the periodic table (design notes, design-system
 * section 11): the id's first letter in upper case, then the first consonant
 * after it that gives an unused symbol, then the first vowel that does.
 * Capabilities are taken in ontology layer order, so earlier ones keep theirs.
 */
export function capabilitySymbols(ids: string[]): Map<string, string> {
  const used = new Set<string>();
  const out = new Map<string, string>();
  for (const id of ids) {
    const letters = [...id.toLowerCase()].filter((c) => /[a-z]/.test(c));
    const first = letters[0]!.toUpperCase();
    const rest = letters.slice(1);
    const candidates = [...rest.filter((c) => !VOWELS.has(c)), ...rest.filter((c) => VOWELS.has(c))];
    const second = candidates.find((c) => !used.has(first + c));
    if (second === undefined) throw new Error(`views: no unused symbol for ${id}`);
    used.add(first + second);
    out.set(id, first + second);
  }
  return out;
}

/** Capability ids in layer order, as the periodic table numbers them from 1. */
export function tableOrder(ontology: Ontology = loadOntology()): string[] {
  return ontology.layers.flatMap((l) => l.capabilities);
}

let symbols: Map<string, string> | null = null;

/** The periodic-table symbol of a capability, as the table computes it. */
export function capabilitySymbol(id: string): string {
  symbols ??= capabilitySymbols(tableOrder());
  const s = symbols.get(id);
  if (!s) throw new Error(`views: ${id} is not a capability`);
  return s;
}

// -------------------------------------------------------------------- edges

export interface EdgeGroup {
  type: EdgeType;
  symmetric: boolean;
  /** For a symmetric type, every capability on the other end, once. */
  related: string[];
  outgoing: string[];
  incoming: string[];
}

/** A capability's edges grouped by type, in the ontology's edge type order. Empty groups are left out. */
export function edgeGroups(cap: Capability, ontology: Ontology = loadOntology()): EdgeGroup[] {
  const groups: EdgeGroup[] = [];
  for (const type of EDGE_TYPES) {
    const info = ontology.edgeTypes.find((t) => t.id === type)!;
    const outgoing = [...cap.edgesOut[type]];
    const incoming = [...cap.edgesIn[type]];
    if (outgoing.length === 0 && incoming.length === 0) continue;
    const related = info.symmetric ? [...new Set([...outgoing, ...incoming])] : [];
    groups.push({ type, symmetric: info.symmetric, related, outgoing, incoming });
  }
  return groups;
}

export interface CrossLayerEdge {
  from: string;
  to: string;
  /** Layer of the capability outside this layer. */
  otherLayer: string;
  direction: 'out' | 'in';
}

/**
 * Edges with one end in the layer and the other outside it, grouped by type.
 * The ontology declares a symmetric relation (conflicts_with, alternative_to)
 * in both directions; it is listed once, as first declared, as on capability
 * pages.
 */
export function crossLayerEdges(
  layerId: string,
  ontology: Ontology = loadOntology(),
): { type: EdgeType; symmetric: boolean; edges: CrossLayerEdge[] }[] {
  const layerOf = (id: string) => ontology.byId.get(id)!.layer;
  return EDGE_TYPES.map((type) => {
    const symmetric = ontology.edgeTypes.find((t) => t.id === type)!.symmetric;
    const seen = new Set<string>();
    const edges = ontology.edges
      .filter((e) => e.type === type && (layerOf(e.from) === layerId) !== (layerOf(e.to) === layerId))
      .filter((e) => {
        if (!symmetric) return true;
        const pair = [e.from, e.to].sort().join('|');
        if (seen.has(pair)) return false;
        seen.add(pair);
        return true;
      })
      .map((e) => {
        const out = layerOf(e.from) === layerId;
        return { from: e.from, to: e.to, otherLayer: layerOf(out ? e.to : e.from), direction: out ? 'out' : 'in' } as const;
      });
    return { type, symmetric, edges };
  }).filter((g) => g.edges.length > 0);
}

// ---------------------------------------------------------------- workflows

/** Workflows that use any capability of the layer, with the capabilities each uses. */
export function layerUsage(layerId: string): { workflow: Workflow; capabilities: string[] }[] {
  return loadWorkflows()
    .all.map((workflow) => ({
      workflow,
      capabilities: [...new Set(workflow.steps.filter((s) => s.layer === layerId).map((s) => s.capability))],
    }))
    .filter((u) => u.capabilities.length > 0);
}

/** A step's role in the diagram (design notes, design-system section 12). */
export type StepRole = 'checkpoint' | 'mutating' | 'verify' | 'rollback' | 'plain';

/** Capabilities that change state only by recording: not drawn as mutating steps. */
const RECORDING = new Set(['checkpoint', 'audit', 'persist']);

/**
 * The role of a step, from its capability and its effective flags (Standard
 * §5.2.1), never from its name alone:
 * - checkpoint, rollback: the step runs that capability;
 * - verify: it runs `verify` or `constrain`;
 * - mutating: its effective `mutation` is true and it is not a checkpoint,
 *   audit or persist step;
 * - plain: anything else.
 */
export function stepRole(step: Step): StepRole {
  if (step.capability === 'checkpoint') return 'checkpoint';
  if (step.capability === 'rollback') return 'rollback';
  if (step.capability === 'verify' || step.capability === 'constrain') return 'verify';
  if (step.effective.mutation && !RECORDING.has(step.capability)) return 'mutating';
  return 'plain';
}

export interface DiagramStep {
  step: Step;
  role: StepRole;
  /** The step has gates or a condition, so the diagram draws it as a branch. */
  branch: boolean;
  /** Index of the nearest checkpoint step that runs before it, for mutating and rollback steps. */
  checkpointStep: number | null;
  /** The step needs a checkpoint and none runs before it: the diagnostic a validator reports. */
  missingCheckpoint: 'V102' | 'F501' | null;
}

/**
 * Checkpoints count only when they run before the step (Standard terms table,
 * "Runs before"): earlier in the list and not in the step's parallel group,
 * as the validator reads it.
 */
export function diagramSteps(wf: Workflow): DiagramStep[] {
  const checkpoints: { index: number; group: string | null }[] = [];
  return wf.steps.map((step) => {
    const role = stepRole(step);
    const group = step.parallel_group ?? null;
    const cp = checkpoints.findLast((c) => group === null || c.group !== group)?.index ?? null;
    if (step.capability === 'checkpoint') checkpoints.push({ index: step.index, group });
    const branch = (step.gates?.length ?? 0) > 0 || (step.condition !== undefined && step.condition !== null);
    const missingCheckpoint = step.effective.checkpoint.needed && cp === null ? step.effective.checkpoint.code : null;
    return {
      step,
      role,
      branch,
      checkpointStep: role === 'mutating' || role === 'rollback' ? cp : null,
      missingCheckpoint,
    };
  });
}

/** Runs of steps for the diagram: consecutive steps in one parallel group form one run. */
export function diagramRuns(steps: DiagramStep[]): { group: string | null; join: unknown; steps: DiagramStep[] }[] {
  const runs: { group: string | null; join: unknown; steps: DiagramStep[] }[] = [];
  for (const d of steps) {
    const group = d.step.parallel_group ?? null;
    const last = runs.at(-1);
    if (group !== null && last && last.group === group) {
      last.steps.push(d);
      if (d.step.join !== undefined) last.join = d.step.join;
    } else {
      runs.push({ group, join: d.step.join, steps: [d] });
    }
  }
  return runs;
}

export interface GateRow {
  when: string;
  action: string;
  message: string;
  phase: string;
}

export function gateRows(step: Step): GateRow[] {
  return (step.gates ?? []).map((g) => {
    const o = isObj(g) ? g : {};
    return {
      when: String(o.when ?? ''),
      action: String(o.action ?? ''),
      message: typeof o.message === 'string' ? o.message : '',
      phase: typeof o.phase === 'string' ? o.phase : '',
    };
  });
}

export interface FailureRow {
  condition: string;
  when: string;
  action: string;
  recovery: string;
  codes: string[];
}

export function failureRows(step: Step): FailureRow[] {
  return (step.failure_modes ?? []).map((f) => {
    const o = isObj(f) ? f : {};
    return {
      condition: typeof o.condition === 'string' ? o.condition : '',
      when: typeof o.when === 'string' ? o.when : '',
      action: String(o.action ?? ''),
      recovery: typeof o.recovery === 'string' ? o.recovery : '',
      // Standard 1.1.0 §5.x: `on_error` is a code or a list of codes.
      codes: Array.isArray(o.on_error) ? o.on_error.map(String) : typeof o.on_error === 'string' ? [o.on_error] : [],
    };
  });
}

/** The 1-based index of the step that stores each name, for "uses output of step N". */
export function producerSteps(wf: Workflow, step: Step): { name: string; index: number }[] {
  return step.consumes.map((name) => {
    const producer = wf.steps.find((s) => s.index < step.index && s.store_as === name);
    if (!producer) throw new Error(`views: ${wf.id} step ${step.index} reads ${name}, which no earlier step stores`);
    return { name, index: producer.index };
  });
}

/**
 * Rendered Markdown split before its first H2: the title and lead, then the
 * sections. With no H2 the whole text is the head.
 */
export function splitAtFirstH2(html: string): { head: string; rest: string } {
  const i = html.search(/<h2[\s>]/);
  return i === -1 ? { head: html, rest: '' } : { head: html.slice(0, i), rest: html.slice(i) };
}

/** Profiles whose `workflows` list names the workflow. */
export function profilesListing(workflowId: string, profiles: DomainProfile[] = loadProfiles()): DomainProfile[] {
  return profiles.filter((p) => p.workflows.some((w) => w.id === workflowId));
}

/** Composed skill directories that run the workflow. */
export function composedSkillsFor(workflowId: string): string[] {
  return Object.entries(COMPOSED_SKILLS)
    .filter(([, wf]) => wf === workflowId)
    .map(([dir]) => dir)
    .sort();
}

/** Capabilities a workflow uses, once each, in first-use order. */
export function capabilitiesUsed(wf: Workflow): string[] {
  return [...new Set(wf.steps.map((s) => s.capability))];
}

export function toYaml(value: unknown): string {
  return stringify(value).trimEnd();
}

// ------------------------------------------------------------------ profiles

/** Trust weights, highest first; ties keep file order. */
export function sortedTrustWeights(profile: Obj): { source: string; weight: number }[] {
  const tw = profile.trust_weights;
  if (!isObj(tw)) return [];
  return Object.entries(tw)
    .map(([source, w]) => ({ source, weight: Number(w) }))
    .sort((a, b) => b.weight - a.weight);
}

/** Profile keys the domain page shows in their own sections. */
export const PROFILE_SECTION_KEYS: ReadonlySet<string> = new Set([
  'domain',
  'version',
  'description',
  'trust_weights',
  'trust_model_reviewed',
  'trust_model_reviewed_at',
  'risk_thresholds',
  'checkpoint_policy',
  'evidence_policy',
  'domain_sources',
  'workflows',
  'compliance',
]);

// ------------------------------------------------------------------- schemas

export interface SchemaEntry {
  source: string;
  name: string;
  group: 'required' | 'supporting' | 'ontology' | 'interop' | 'transforms' | 'profiles' | 'other';
  description: string;
  /** The Purpose column of the Standard's §6.1 table, for a required schema. */
  purpose?: string;
}

/**
 * The schema files the Standard names in §6.1: the table lists the required
 * ones, and the sentence after it names the supporting ones. Read from the
 * Standard's text so the listing follows it.
 */
export function standardSchemaNames(specText: string): {
  required: string[];
  supporting: string[];
  /** The Purpose column of the §6.1 table, by file name. */
  purposes: Record<string, string>;
} {
  const lines = specText.split('\n');
  const start = lines.findIndex((l) => /^### 6\.1 /.test(l));
  if (start === -1) throw new Error('views: the Standard has no §6.1');
  const rest = lines.slice(start + 1);
  const end = rest.findIndex((l) => /^#{2,3} /.test(l));
  const body = end === -1 ? rest : rest.slice(0, end);
  const purposes: Record<string, string> = {};
  const required = body.flatMap((l) => {
    const m = /^\|\s*`([^`]+)`\s*\|\s*(.*?)\s*\|\s*$/.exec(l);
    if (!m) return [];
    purposes[m[1]!] = m[2]!;
    return [m[1]!];
  });
  const prose = body.filter((l) => !l.startsWith('|')).join(' ');
  const supportingText = /Supporting schemas[^:]*:([\s\S]*)$/.exec(prose)?.[1] ?? '';
  const supporting = [...supportingText.matchAll(/`([^`]+\.(?:ya?ml|json))`/g)].map((m) => m[1]!);
  if (required.length === 0) throw new Error('views: §6.1 lists no schema files');
  return { required, supporting, purposes };
}

/**
 * What a schema file says it is: a JSON schema's description or title; for
 * YAML, the `description` of the top-level mapping or of its header mapping
 * (`schema:`, `meta:`, `registry:` or `mapping:`), else the first line of its
 * leading comment that is not a "Key: value" line. Empty when it says nothing.
 */
export function schemaDescription(source: string, text: string): string {
  const one = (v: string) => v.replace(/\s+/g, ' ').trim();
  if (source.endsWith('.json')) {
    const doc = JSON.parse(text) as Obj;
    return one(typeof doc.description === 'string' ? doc.description : typeof doc.title === 'string' ? doc.title : '');
  }
  const doc: unknown = parse(text);
  if (isObj(doc)) {
    if (typeof doc.description === 'string') return one(doc.description);
    for (const key of ['schema', 'meta', 'registry', 'mapping']) {
      const v = doc[key];
      if (isObj(v) && typeof v.description === 'string') return one(v.description);
    }
  }
  for (const l of text.split('\n')) {
    if (!l.startsWith('#')) break;
    const t = l.replace(/^#+\s?/, '').trim();
    if (t === '' || /^[A-Za-z ]+:\s/.test(t)) continue;
    return t;
  }
  return '';
}

/**
 * Every schema file under schemas/ except the workflow catalogs and domain
 * profiles, which have their own pages. Required and supporting files come
 * from the Standard's §6.1; the rest are grouped by folder.
 */
export function schemaListing(specText: string): SchemaEntry[] {
  const { required, supporting, purposes } = standardSchemaNames(specText);
  const files = [...TRACKED_FILES]
    .filter(
      (p) =>
        p.startsWith('schemas/') &&
        /\.(ya?ml|json)$/.test(p) &&
        !p.startsWith('schemas/workflows/') &&
        (!p.startsWith('schemas/profiles/') || p === 'schemas/profiles/profile_schema.yaml'),
    )
    .sort();
  for (const name of [...required, ...supporting]) {
    if (!files.includes(`schemas/${name}`)) throw new Error(`views: §6.1 names ${name}, which is not in schemas/`);
  }
  return files.map((source) => {
    const name = source.slice('schemas/'.length);
    const group: SchemaEntry['group'] = required.includes(name)
      ? 'required'
      : supporting.includes(name)
        ? 'supporting'
        : name.startsWith('interop/')
          ? 'interop'
          : name.startsWith('transforms/')
            ? 'transforms'
            : name.startsWith('profiles/')
              ? 'profiles'
              : /^(capability_ontology|workflow_catalog)\./.test(name)
                ? 'ontology'
                : 'other';
    const entry: SchemaEntry = { source, name, group, description: schemaDescription(source, readRepoFile(source)) };
    const purpose = purposes[name];
    if (purpose !== undefined) entry.purpose = purpose;
    return entry;
  });
}

/** The groups of the schemas page, in order, with their intro lines. */
export function schemaGroups(standardVersion: string): { key: SchemaEntry['group']; label: string; intro: string }[] {
  return [
  { key: 'required', label: 'Required by the Standard', intro: `Section 6.1 of Standard ${standardVersion} requires every implementation to provide these schemas.` },
  { key: 'supporting', label: 'Supporting schemas', intro: `Section 6.1 names these schemas as used by specific sections. They are not required of every implementation.` },
  { key: 'ontology', label: 'Ontology and workflow catalog', intro: 'The capability ontology, the reference workflow catalog, and the JSON Schemas that check them.' },
  { key: 'profiles', label: 'Domain profile format', intro: 'The schema every domain profile follows.' },
  { key: 'interop', label: 'Interoperability', intro: 'Mappings to other agent frameworks.' },
  { key: 'other', label: 'Other schemas', intro: 'Schema files the Standard does not name.' },
  { key: 'transforms', label: 'Transforms', intro: 'The coercion registry and the mappings the transform capability uses.' },
  ];
}

// -------------------------------------------------------------- type glyphs

/** Type strings that name one field-type family glyph (visual spec 2.3). */
const TYPE_FAMILIES: Readonly<Record<string, string>> = {
  string: 'type:text',
  number: 'type:number',
  integer: 'type:number',
  boolean: 'type:boolean',
  array: 'type:list',
  object: 'type:record',
  any: 'type:open',
  unknown: 'type:open',
};

/** Split on commas or pipes that are not inside angle brackets. */
function splitTopLevel(s: string, sep: ',' | '|'): string[] {
  const parts: string[] = [];
  let depth = 0;
  let cur = '';
  for (const ch of s) {
    if (ch === '<') depth++;
    if (ch === '>') depth--;
    if (ch === sep && depth === 0) {
      parts.push(cur.trim());
      cur = '';
    } else cur += ch;
  }
  parts.push(cur.trim());
  return parts.filter((p) => p !== '');
}

/**
 * The family glyph keys of a field type string (visual spec 2.3, the
 * normalising rule). The exact string is always printed beside the glyphs,
 * so the glyphs only give the family:
 * 1. a union (`a|b` or `union<a, b>`) gives each part's glyphs in order;
 * 2. `nullable<T>` gives T's glyphs;
 * 3. `array of T` and `array<T>` give `type:list`;
 * 4. other strings are looked up by family (`map<K,V>` is a record);
 * 5. `null` and anything else give no glyph.
 */
export function typeGlyphs(type: string): string[] {
  const t = type.trim();
  const top = splitTopLevel(t, '|');
  if (top.length > 1) return top.flatMap(typeGlyphs);
  const generic = /^([a-z_]+)\s*<([\s\S]*)>$/i.exec(t);
  if (generic) {
    const [, name, inner] = generic;
    switch (name!.toLowerCase()) {
      case 'union':
        return splitTopLevel(inner!, ',').flatMap(typeGlyphs);
      case 'nullable':
        return typeGlyphs(inner!);
      case 'array':
        return ['type:list'];
      case 'map':
        return ['type:record'];
      default:
        return [];
    }
  }
  if (/^array\s+of\s+/i.test(t)) return ['type:list'];
  const family = TYPE_FAMILIES[t.toLowerCase()];
  return family ? [family] : [];
}

// ------------------------------------------------------------- safety panel

/** The domain profiles that never let a capability run autonomously (`risk_thresholds.block_autonomous`). */
export function autonomyBlocks(capId: string, profiles: DomainProfile[] = loadProfiles()): { blocked: string[]; total: number } {
  const blocked = profiles
    .filter((p) => {
      const t = p.profile.risk_thresholds;
      return isObj(t) && Array.isArray(t.block_autonomous) && t.block_autonomous.map(String).includes(capId);
    })
    .map((p) => p.key);
  return { blocked, total: profiles.length };
}

export interface SafetyRow {
  /** Stable key: risk, mutation, checkpoint, approval, overridable, autonomy. */
  key: 'risk' | 'mutation' | 'checkpoint' | 'approval' | 'overridable' | 'autonomy';
  term: string;
  /** Whether the cell is drawn as on. Risk is always on. */
  on: boolean;
  value: string;
  glyph: string;
}

/**
 * The six cells of a capability's safety panel (visual spec F-C3), shared by
 * the page and its Markdown copy. A checkpoint that comes only from a
 * `requires` edge (rollback) says so.
 */
export function safetyRows(cap: Capability, profiles: DomainProfile[] = loadProfiles()): SafetyRow[] {
  const viaEdge = !cap.requires_checkpoint && cap.edgesIn.requires.includes('checkpoint');
  const needsCheckpoint = cap.requires_checkpoint || viaEdge;
  const { blocked, total } = autonomyBlocks(cap.id, profiles);
  const yes = (b: boolean) => (b ? 'Yes' : 'No');
  return [
    { key: 'risk', term: 'Risk', on: true, value: cap.risk[0]!.toUpperCase() + cap.risk.slice(1), glyph: `risk:${cap.risk}` },
    { key: 'mutation', term: 'Changes state', on: cap.mutation, value: yes(cap.mutation), glyph: cap.mutation ? 'pencil' : 'eye' },
    { key: 'checkpoint', term: 'Needs checkpoint', on: needsCheckpoint, value: viaEdge ? 'Yes, via requires edge' : yes(needsCheckpoint), glyph: 'flag' },
    { key: 'approval', term: 'Needs approval', on: cap.requires_approval, value: yes(cap.requires_approval), glyph: 'stamp' },
    { key: 'overridable', term: 'Overridable', on: cap.mutation_overridable, value: yes(cap.mutation_overridable), glyph: 'flag:overridable' },
    {
      key: 'autonomy',
      term: 'Blocked from autonomy',
      on: blocked.length > 0,
      value: blocked.length > 0 ? `In ${blocked.length} of ${total} profiles` : 'No',
      glyph: 'approve:blocked',
    },
  ];
}

// -------------------------------------------------------------- edge types

/**
 * How many edges of a type the ontology has, counting a symmetric type once
 * per pair of capabilities (conflicts_with lists each pair in both directions).
 */
export function edgeTypeCount(info: EdgeTypeInfo): number {
  if (!info.symmetric) return info.edges.length;
  return new Set(info.edges.map((e) => [e.from, e.to].sort().join('\u0000'))).size;
}
