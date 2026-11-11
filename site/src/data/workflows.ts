// Workflows from schemas/workflow_catalog.yaml (core) and
// schemas/workflows/*.yaml (domain). examples/ is never read: it repeats a
// core workflow id.
import { parse } from 'yaml';
import { effectiveFlags, type EffectiveFlags } from '../lib/flags';
import { readRepoFile, trackedUnder } from '../lib/repo';
import { loadOntology, type Ontology, type Risk } from './ontology';

export const CORE_CATALOG = 'schemas/workflow_catalog.yaml';
export const DOMAIN_CATALOG_DIR = 'schemas/workflows';

/** Slugs the workflow section uses for its prose pages. */
export const RESERVED_WORKFLOW_SLUGS: readonly string[] = ['patterns', 'roadmap'];

export interface Step {
  /** 1-based position in the workflow. */
  index: number;
  capability: string;
  layer: string;
  purpose: string;
  domain?: string;
  /** What the step itself declares, before §5.2.1 is applied. */
  declared: {
    risk?: unknown;
    mutation?: unknown;
    requires_checkpoint?: unknown;
    requires_approval?: unknown;
  };
  effective: EffectiveFlags;
  timeout?: unknown;
  retry?: unknown;
  store_as?: string;
  input_bindings: Record<string, unknown>;
  gates?: unknown[];
  condition?: unknown;
  skip_if_false?: boolean;
  parallel_group?: string;
  join?: unknown;
  workflow_id?: string;
  mapping_ref?: string;
  failure_modes?: unknown[];
  /** store_as names of earlier steps this step reads through `${...}`. */
  consumes: string[];
  /** Step keys not listed above, kept for a "Raw YAML" view. */
  extra: Record<string, unknown>;
}

export interface Workflow {
  id: string;
  slug: string;
  source: string;
  catalog: 'core' | 'domain';
  /** Standard version from the file's `# Standard version:` header comment. */
  standardVersion: string | null;
  domain?: string;
  profile?: string;
  goal: string;
  risk: Risk;
  description?: string;
  success: string[];
  inputs: Record<string, unknown>;
  steps: Step[];
  data_flow?: unknown;
  risk_propagation?: unknown;
  workflow_extensions?: unknown;
  triggers?: unknown;
  /** Ids of workflows with a step that invokes this one. */
  invokedBy: string[];
  extra: Record<string, unknown>;
}

export interface CapabilityUse {
  workflowId: string;
  slug: string;
  catalog: 'core' | 'domain';
  /** 1-based step indexes that use the capability. */
  steps: number[];
}

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);

const STEP_KEYS = new Set([
  'capability', 'purpose', 'domain', 'risk', 'mutation', 'requires_checkpoint', 'requires_approval',
  'timeout', 'retry', 'store_as', 'input_bindings', 'gates', 'condition', 'skip_if_false',
  'parallel_group', 'join', 'workflow_id', 'mapping_ref', 'failure_modes',
]);
const WORKFLOW_KEYS = new Set([
  'goal', 'risk', 'description', 'success', 'inputs', 'steps', 'domain', 'profile', 'data_flow',
  'risk_propagation', 'workflow_extensions', 'triggers',
]);

export function workflowSlug(id: string): string {
  return id.replace(/_/g, '-');
}

/** Root names of every `${...}` reference inside a value. Roots follow Standard §5.3. */
export function referenceRoots(value: unknown, out: Set<string> = new Set()): Set<string> {
  if (typeof value === 'string') {
    for (const m of value.matchAll(/\$\{\s*([A-Za-z_][A-Za-z0-9_-]*)/g)) out.add(m[1]!);
  } else if (Array.isArray(value)) {
    for (const v of value) referenceRoots(v, out);
  } else if (isObj(value)) {
    for (const v of Object.values(value)) referenceRoots(v, out);
  }
  return out;
}

function pick(o: Obj, keys: Set<string>): Obj {
  return Object.fromEntries(Object.entries(o).filter(([k]) => !keys.has(k)));
}

function standardVersionOf(text: string): string | null {
  const m = /^#\s*Standard version:\s*(\S+)/m.exec(text);
  return m ? m[1]! : null;
}

function buildSteps(wfId: string, rawSteps: unknown, ontology: Ontology): Step[] {
  if (!Array.isArray(rawSteps)) throw new Error(`workflows: ${wfId}.steps is not a list`);
  const earlierStores = new Set<string>();
  return rawSteps.map((s, i) => {
    const where = `${wfId} step ${i + 1}`;
    if (!isObj(s)) throw new Error(`workflows: ${where} is not a mapping`);
    const capId = s.capability;
    if (typeof capId !== 'string') throw new Error(`workflows: ${where} has no capability`);
    const cap = ontology.byId.get(capId);
    if (!cap) throw new Error(`workflows: ${where} uses unknown capability ${capId}`);
    const bindings = isObj(s.input_bindings) ? s.input_bindings : {};
    const roots = referenceRoots([bindings, s.gates ?? null, s.condition ?? null]);
    const consumes = [...roots].filter((r) => earlierStores.has(r));
    const step: Step = {
      index: i + 1,
      capability: capId,
      layer: cap.layer,
      purpose: typeof s.purpose === 'string' ? s.purpose : '',
      declared: {
        risk: s.risk,
        mutation: s.mutation,
        requires_checkpoint: s.requires_checkpoint,
        requires_approval: s.requires_approval,
      },
      effective: effectiveFlags(s, cap),
      input_bindings: bindings,
      consumes,
      extra: pick(s, STEP_KEYS),
    };
    if (typeof s.domain === 'string') step.domain = s.domain;
    if ('timeout' in s) step.timeout = s.timeout;
    if ('retry' in s) step.retry = s.retry;
    if (typeof s.store_as === 'string') step.store_as = s.store_as;
    if (Array.isArray(s.gates)) step.gates = s.gates;
    if ('condition' in s) step.condition = s.condition;
    if (typeof s.skip_if_false === 'boolean') step.skip_if_false = s.skip_if_false;
    if (typeof s.parallel_group === 'string') step.parallel_group = s.parallel_group;
    if ('join' in s) step.join = s.join;
    if (typeof s.workflow_id === 'string') step.workflow_id = s.workflow_id;
    if (typeof s.mapping_ref === 'string') step.mapping_ref = s.mapping_ref;
    if (Array.isArray(s.failure_modes)) step.failure_modes = s.failure_modes;
    if (step.store_as) earlierStores.add(step.store_as);
    return step;
  });
}

/** Parse one catalog file. Top-level `x-` keys are vendor data, not workflows (§5.1). */
export function parseCatalog(source: string, text: string, catalog: 'core' | 'domain', ontology: Ontology): Workflow[] {
  const doc: unknown = parse(text);
  if (!isObj(doc)) throw new Error(`workflows: ${source} is not a mapping`);
  const standardVersion = standardVersionOf(text);
  const out: Workflow[] = [];
  for (const [id, w] of Object.entries(doc)) {
    if (id.startsWith('x-')) continue;
    if (!isObj(w)) throw new Error(`workflows: ${source}: ${id} is not a mapping`);
    if (typeof w.goal !== 'string') throw new Error(`workflows: ${id}.goal is missing`);
    if (w.risk !== 'low' && w.risk !== 'medium' && w.risk !== 'high') {
      throw new Error(`workflows: ${id}.risk is not low, medium or high`);
    }
    const wf: Workflow = {
      id,
      slug: workflowSlug(id),
      source,
      catalog,
      standardVersion,
      goal: w.goal,
      risk: w.risk,
      success: Array.isArray(w.success) ? w.success.map(String) : [],
      inputs: isObj(w.inputs) ? w.inputs : {},
      steps: buildSteps(id, w.steps, ontology),
      invokedBy: [],
      extra: pick(w, WORKFLOW_KEYS),
    };
    if (typeof w.description === 'string') wf.description = w.description;
    if (typeof w.domain === 'string') wf.domain = w.domain;
    if (typeof w.profile === 'string') wf.profile = w.profile;
    if ('data_flow' in w) wf.data_flow = w.data_flow;
    if ('risk_propagation' in w) wf.risk_propagation = w.risk_propagation;
    if ('workflow_extensions' in w) wf.workflow_extensions = w.workflow_extensions;
    if ('triggers' in w) wf.triggers = w.triggers;
    out.push(wf);
  }
  return out;
}

/** Cross-file checks: unique ids and slugs, and every invoked workflow resolves. */
export function linkWorkflows(all: Workflow[]): Workflow[] {
  const byId = new Map<string, Workflow>();
  const slugs = new Map<string, string>();
  for (const wf of all) {
    const prior = byId.get(wf.id);
    if (prior) throw new Error(`workflows: ${wf.id} is defined in ${prior.source} and ${wf.source}`);
    byId.set(wf.id, wf);
    const clash = slugs.get(wf.slug);
    if (clash) throw new Error(`workflows: ${wf.id} and ${clash} share the slug ${wf.slug}`);
    if (RESERVED_WORKFLOW_SLUGS.includes(wf.slug)) {
      throw new Error(`workflows: ${wf.id} has the reserved slug ${wf.slug}`);
    }
    slugs.set(wf.slug, wf.id);
  }
  for (const wf of all) {
    for (const step of wf.steps) {
      if (step.workflow_id === undefined) continue;
      const target = byId.get(step.workflow_id);
      if (!target) {
        throw new Error(`workflows: ${wf.id} step ${step.index} invokes unknown workflow ${step.workflow_id}`);
      }
      if (!target.invokedBy.includes(wf.id)) target.invokedBy.push(wf.id);
    }
  }
  return all;
}

export interface WorkflowSet {
  all: Workflow[];
  core: Workflow[];
  domain: Workflow[];
  byId: ReadonlyMap<string, Workflow>;
  /** Domain catalog files in name order. */
  domainSources: string[];
}

let cached: WorkflowSet | undefined;

export function loadWorkflows(): WorkflowSet {
  if (cached) return cached;
  const ontology = loadOntology();
  const core = parseCatalog(CORE_CATALOG, readRepoFile(CORE_CATALOG), 'core', ontology);
  const domainSources = trackedUnder(DOMAIN_CATALOG_DIR, '.yaml');
  const domain = domainSources.flatMap((src) => parseCatalog(src, readRepoFile(src), 'domain', ontology));
  const all = linkWorkflows([...core, ...domain]);
  cached = { all, core, domain, byId: new Map(all.map((w) => [w.id, w])), domainSources };
  return cached;
}

/** Where each capability is used, grouped by workflow, in workflow order. */
export function capabilityUsage(capId: string): CapabilityUse[] {
  return loadWorkflows()
    .all.map((wf) => ({
      workflowId: wf.id,
      slug: wf.slug,
      catalog: wf.catalog,
      steps: wf.steps.filter((s) => s.capability === capId).map((s) => s.index),
    }))
    .filter((u) => u.steps.length > 0);
}
