// The schema and policy files the Standard's figures draw from (visual spec
// 3.9, "New loaders"), each read for the parts a figure needs and checked
// for shape, so a change to one fails the build instead of drawing a wrong
// picture:
// - loadCatalogEnums(): enums of workflow_catalog.schema.json beyond the
//   step slots and actions loadCatalogSchema() reads;
// - loadTrustModel(): authority_trust_model.yaml's trust-class weights and
//   decay model;
// - loadIdentitySchema(): agent_identity_schema.yaml's trust_class and kind
//   values;
// - loadWorldStateSchema(): the approval `decision` enum of
//   world_state_schema.yaml;
// - loadIdentityPolicy(): identity_resolution_policy.yaml's merge thresholds;
// - loadRuntimeFixture(name): one file of tests/conformance/runtime/.
import { parse } from 'yaml';
import { readRepoFile } from '../lib/repo';

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);

/** The value at a path of keys, or a thrown error naming the file and the path. */
function at(doc: unknown, path: string[], file: string): unknown {
  let cur = doc;
  for (const k of path) {
    if (!isObj(cur) || !(k in cur)) throw new Error(`${file}: no ${path.join('.')}`);
    cur = cur[k];
  }
  return cur;
}

function strings(v: unknown, what: string): string[] {
  if (!Array.isArray(v) || v.length === 0 || !v.every((x) => typeof x === 'string')) throw new Error(`${what} is not a list of strings`);
  return v as string[];
}

// ------------------------------------------------- workflow catalog enums

export const CATALOG_SCHEMA_FILE = 'schemas/workflow_catalog.schema.json';

export interface CatalogEnums {
  /** workflow_extensions.requires items. */
  extensions: string[];
  triggerKinds: string[];
  attendance: string[];
  overlap: string[];
  livenessModes: string[];
  approverKinds: string[];
  whenUnattended: string[];
  /** The failure-mode on_error codes a failure mode may name. */
  fireableCodes: string[];
}

let catalogEnums: CatalogEnums | null = null;

export function loadCatalogEnums(): CatalogEnums {
  if (catalogEnums) return catalogEnums;
  const f = CATALOG_SCHEMA_FILE;
  const doc: unknown = JSON.parse(readRepoFile(f));
  const e = (...path: string[]) => strings(at(doc, [...path, 'enum'], f), `${f}: ${path.join('.')}`);
  catalogEnums = {
    extensions: e('$defs', 'workflow', 'properties', 'workflow_extensions', 'properties', 'requires', 'items'),
    triggerKinds: e('$defs', 'trigger', 'properties', 'kind'),
    attendance: e('$defs', 'trigger', 'properties', 'attendance'),
    overlap: e('$defs', 'schedule', 'properties', 'overlap'),
    livenessModes: e('$defs', 'wait', 'properties', 'liveness', 'properties', 'mode'),
    approverKinds: e('$defs', 'approval', 'properties', 'approver', 'properties', 'kind'),
    whenUnattended: e('$defs', 'approval', 'properties', 'when_unattended'),
    fireableCodes: e('$defs', 'fireable_code'),
  };
  return catalogEnums;
}

// ------------------------------------------------------ authority trust model

export const TRUST_MODEL_FILE = 'schemas/authority_trust_model.yaml';

export interface TrustModel {
  /** Default source weight of each trust class, in file order. */
  classWeights: { cls: string; weight: number }[];
  /** decay_model.half_life, as written (an ISO-8601 duration such as P10D). */
  halfLife: string;
  /** half_life in days. */
  halfLifeDays: number;
  minTrust: number;
  /** conflict_resolution_function.recency_factor, as written. */
  recencyFactor: string;
}

let trustModel: TrustModel | null = null;

export function loadTrustModel(): TrustModel {
  if (trustModel) return trustModel;
  const f = TRUST_MODEL_FILE;
  const doc: unknown = parse(readRepoFile(f));
  const w = at(doc, ['trust_classes', 'weights'], f);
  if (!isObj(w)) throw new Error(`${f}: trust_classes.weights is not a mapping`);
  const classWeights = Object.entries(w).map(([cls, v]) => {
    if (typeof v !== 'number' || v < 0 || v > 1) throw new Error(`${f}: trust_classes.weights.${cls} is not a number from 0 to 1`);
    return { cls, weight: v };
  });
  const halfLife = at(doc, ['decay_model', 'half_life'], f);
  const m = typeof halfLife === 'string' ? /^P(\d+)D$/.exec(halfLife) : null;
  if (!m) throw new Error(`${f}: decay_model.half_life is not a whole number of days (PnD)`);
  const minTrust = at(doc, ['decay_model', 'min_trust'], f);
  if (typeof minTrust !== 'number' || minTrust < 0 || minTrust > 1) throw new Error(`${f}: decay_model.min_trust is not a number from 0 to 1`);
  const recencyFactor = at(doc, ['conflict_resolution_function', 'recency_factor'], f);
  if (typeof recencyFactor !== 'string') throw new Error(`${f}: conflict_resolution_function.recency_factor is not a string`);
  trustModel = { classWeights, halfLife: halfLife as string, halfLifeDays: Number(m[1]), minTrust, recencyFactor };
  return trustModel;
}

// ---------------------------------------------------------- agent identity

export const IDENTITY_SCHEMA_FILE = 'schemas/agent_identity_schema.yaml';

export interface IdentitySchema {
  trustClasses: string[];
  kinds: string[];
}

let identitySchema: IdentitySchema | null = null;

/** The identity's properties, wherever the file nests them. */
function identityProperties(doc: unknown, f: string): Obj {
  let found: Obj | null = null;
  const walk = (n: unknown) => {
    if (found || !isObj(n)) return;
    if (isObj(n.properties) && 'trust_class' in n.properties) {
      found = n.properties;
      return;
    }
    Object.values(n).forEach(walk);
  };
  walk(doc);
  if (!found) throw new Error(`${f}: no object schema with a trust_class property`);
  return found;
}

export function loadIdentitySchema(): IdentitySchema {
  if (identitySchema) return identitySchema;
  const f = IDENTITY_SCHEMA_FILE;
  const props = identityProperties(parse(readRepoFile(f)), f);
  const en = (k: string) => strings(at(props, [k, 'enum'], f), `${f}: ${k}`);
  identitySchema = { trustClasses: en('trust_class'), kinds: en('kind') };
  return identitySchema;
}

// ------------------------------------------------------------- world state

export const WORLD_STATE_FILE = 'schemas/world_state_schema.yaml';

let decisions: string[] | null = null;

/** The values of an action record's approval `decision` (world_state_schema.yaml 1.1). */
export function loadWorldStateSchema(): { approvalDecisions: string[] } {
  if (!decisions) {
    const f = WORLD_STATE_FILE;
    let found: string[] | null = null;
    const walk = (n: unknown) => {
      if (found || !isObj(n)) return;
      if (isObj(n.properties) && isObj(n.properties.decision) && isObj(n.properties.digest) && Array.isArray(n.properties.decision.enum)) {
        found = n.properties.decision.enum.map(String);
        return;
      }
      Object.values(n).forEach(walk);
    };
    walk(parse(readRepoFile(f)));
    if (!found) throw new Error(`${f}: no approval object with digest and a decision enum`);
    decisions = found;
  }
  return { approvalDecisions: decisions };
}

// ------------------------------------------------- identity resolution policy

export const IDENTITY_POLICY_FILE = 'schemas/identity_resolution_policy.yaml';

export interface IdentityPolicy {
  /** alias_confidence_scoring.thresholds, highest first. */
  thresholds: { name: string; value: number }[];
  range: [number, number];
}

let identityPolicy: IdentityPolicy | null = null;

export function loadIdentityPolicy(): IdentityPolicy {
  if (identityPolicy) return identityPolicy;
  const f = IDENTITY_POLICY_FILE;
  const doc: unknown = parse(readRepoFile(f));
  const t = at(doc, ['alias_confidence_scoring', 'thresholds'], f);
  if (!isObj(t)) throw new Error(`${f}: alias_confidence_scoring.thresholds is not a mapping`);
  const range = at(doc, ['alias_confidence_scoring', 'score_range'], f);
  if (!Array.isArray(range) || range.length !== 2 || !range.every((x) => typeof x === 'number')) throw new Error(`${f}: score_range is not two numbers`);
  const [lo, hi] = range as [number, number];
  const thresholds = Object.entries(t).map(([name, value]) => {
    if (typeof value !== 'number' || value < lo || value > hi) throw new Error(`${f}: threshold ${name} is outside the score range`);
    return { name, value };
  });
  thresholds.sort((a, b) => b.value - a.value);
  identityPolicy = { thresholds, range: [lo, hi] };
  return identityPolicy;
}

// ------------------------------------------------------ runtime fixtures

export const RUNTIME_FIXTURE_DIR = 'tests/conformance/runtime';

export interface ScriptEntry {
  expect: { kind: string; capability?: string; step?: number } & Obj;
  respond: { kind: string } & Obj;
}

export interface RuntimeFixture {
  name: string;
  file: string;
  description: string;
  catalog: Obj;
  workflow: string;
  attendance: string;
  start: number;
  script: ScriptEntry[];
  end: { kind: string; code?: string; outcome?: string; deferred?: { step: number; reason?: string }[] } & Obj;
}

export function loadRuntimeFixture(name: string): RuntimeFixture {
  const file = `${RUNTIME_FIXTURE_DIR}/${name}.json`;
  let doc: unknown;
  try {
    doc = JSON.parse(readRepoFile(file));
  } catch (e) {
    throw new Error(`runtime fixture ${file}: ${(e as Error).message}`);
  }
  if (!isObj(doc) || !isObj(doc.catalog) || typeof doc.workflow !== 'string' || !Array.isArray(doc.script) || !isObj(doc.end)) {
    throw new Error(`runtime fixture ${file}: needs catalog, workflow, script and end`);
  }
  if (!isObj(doc.catalog[doc.workflow])) throw new Error(`runtime fixture ${file}: its catalog has no workflow ${doc.workflow}`);
  for (const [i, s] of doc.script.entries()) {
    if (!isObj(s) || !isObj(s.expect) || typeof s.expect.kind !== 'string' || !isObj(s.respond) || typeof s.respond.kind !== 'string') {
      throw new Error(`runtime fixture ${file}: script entry ${i} needs expect.kind and respond.kind`);
    }
  }
  return {
    name,
    file,
    description: typeof doc.description === 'string' ? doc.description : '',
    catalog: doc.catalog,
    workflow: doc.workflow,
    attendance: typeof doc.attendance === 'string' ? doc.attendance : 'attended',
    start: typeof doc.start === 'number' ? doc.start : 0,
    script: doc.script as ScriptEntry[],
    end: doc.end as RuntimeFixture['end'],
  };
}
