// Pure functions that turn the loaded data into what the generated pages show.
// The templates stay thin and the tests check these functions directly.
import { stringify } from 'yaml';
import { loadOntology, EDGE_TYPES, type Capability, type EdgeType, type Ontology } from '../data/ontology';
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

/** Edges with one end in the layer and the other outside it, grouped by type. */
export function crossLayerEdges(
  layerId: string,
  ontology: Ontology = loadOntology(),
): { type: EdgeType; edges: CrossLayerEdge[] }[] {
  const layerOf = (id: string) => ontology.byId.get(id)!.layer;
  return EDGE_TYPES.map((type) => ({
    type,
    edges: ontology.edges
      .filter((e) => e.type === type && (layerOf(e.from) === layerId) !== (layerOf(e.to) === layerId))
      .map((e) => {
        const out = layerOf(e.from) === layerId;
        return { from: e.from, to: e.to, otherLayer: layerOf(out ? e.to : e.from), direction: out ? 'out' : 'in' } as const;
      }),
  })).filter((g) => g.edges.length > 0);
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

export type MarkerKind = 'checkpoint' | 'mutate' | 'verify' | 'rollback' | 'approval' | 'gate' | 'condition' | 'parallel' | 'invoke';

export interface StepMarker {
  kind: MarkerKind;
  label: string;
}

/**
 * Markers for one step of the diagram, from the step's effective flags
 * (Standard §5.2.1) and its capability:
 * - checkpoint, verify and rollback mark steps that run those capabilities;
 * - mutate marks a step whose effective `mutation` is true;
 * - approval marks an effective `requires_approval`;
 * - gate, condition, parallel and invoke mark the step's own keys.
 */
export function stepMarkers(step: Step): StepMarker[] {
  const m: StepMarker[] = [];
  if (step.capability === 'checkpoint') m.push({ kind: 'checkpoint', label: 'Checkpoint' });
  if (step.effective.mutation) m.push({ kind: 'mutate', label: 'Changes state' });
  if (step.capability === 'verify') m.push({ kind: 'verify', label: 'Verify' });
  if (step.capability === 'rollback') m.push({ kind: 'rollback', label: 'Rollback' });
  if (step.effective.requires_approval) m.push({ kind: 'approval', label: 'Needs approval' });
  const gates = step.gates?.length ?? 0;
  if (gates > 0) m.push({ kind: 'gate', label: gates === 1 ? '1 gate' : `${gates} gates` });
  if (step.condition !== undefined && step.condition !== null) m.push({ kind: 'condition', label: 'Conditional' });
  if (step.parallel_group) m.push({ kind: 'parallel', label: `Parallel group ${step.parallel_group}` });
  if (step.workflow_id) m.push({ kind: 'invoke', label: `Runs ${step.workflow_id}` });
  return m;
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
      codes: Array.isArray(o.on_error) ? o.on_error.map(String) : [],
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
}

/**
 * The schema files the Standard names in §6.1: the table lists the required
 * ones, and the sentence after it names the supporting ones. Read from the
 * Standard's text so the listing follows it.
 */
export function standardSchemaNames(specText: string): { required: string[]; supporting: string[] } {
  const lines = specText.split('\n');
  const start = lines.findIndex((l) => /^### 6\.1 /.test(l));
  if (start === -1) throw new Error('views: the Standard has no §6.1');
  const rest = lines.slice(start + 1);
  const end = rest.findIndex((l) => /^#{2,3} /.test(l));
  const body = end === -1 ? rest : rest.slice(0, end);
  const required = body.flatMap((l) => {
    const m = /^\|\s*`([^`]+)`\s*\|/.exec(l);
    return m ? [m[1]!] : [];
  });
  const prose = body.filter((l) => !l.startsWith('|')).join(' ');
  const supportingText = /Supporting schemas[^:]*:([\s\S]*)$/.exec(prose)?.[1] ?? '';
  const supporting = [...supportingText.matchAll(/`([^`]+\.(?:ya?ml|json))`/g)].map((m) => m[1]!);
  if (required.length === 0) throw new Error('views: §6.1 lists no schema files');
  return { required, supporting };
}

/** The first comment block of a YAML file, or a JSON schema's description, as one line. */
export function schemaDescription(source: string, text: string): string {
  if (source.endsWith('.json')) {
    const doc = JSON.parse(text) as Obj;
    const d = typeof doc.description === 'string' ? doc.description : typeof doc.title === 'string' ? doc.title : '';
    return d.replace(/\s+/g, ' ').trim();
  }
  const lines: string[] = [];
  for (const l of text.split('\n')) {
    if (/^#/.test(l)) {
      const t = l.replace(/^#+\s?/, '').trim();
      if (/^[=\-#]+$/.test(t)) continue;
      if (t === '') {
        if (lines.length > 0) break;
        continue;
      }
      lines.push(t);
    } else if (l.trim() === '') {
      if (lines.length > 0) break;
    } else break;
  }
  return lines.join(' ').trim();
}

/**
 * Every schema file under schemas/ except the workflow catalogs and domain
 * profiles, which have their own pages. Required and supporting files come
 * from the Standard's §6.1; the rest are grouped by folder.
 */
export function schemaListing(specText: string): SchemaEntry[] {
  const { required, supporting } = standardSchemaNames(specText);
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
    return { source, name, group, description: schemaDescription(source, readRepoFile(source)) };
  });
}

// ---------------------------------------------------------------------- RFCs

/** RFC statuses spec/GOVERNANCE.md allows, read from its "An RFC's status is ..." sentence. */
export function governanceStatuses(text: string): string[] {
  const m = /An RFC's status is ([^.]+)\./.exec(text.replace(/\s+/g, ' '));
  if (!m) throw new Error("views: spec/GOVERNANCE.md has no \"An RFC's status is\" sentence");
  return m[1]!
    .replace(/\([^)]*\)/g, '')
    .split(/,\s*|\s+or\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
}
