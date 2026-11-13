// schemas/workflow_catalog.schema.json, the parts the Standard's figures draw
// (visual spec 3.9): the step's properties and required list, and the enums
// of the gate and failure-mode actions and the gate phase. Throws when a part
// the figures need is missing, so a schema change fails the build.
import { readRepoFile } from '../lib/repo';

export const CATALOG_SCHEMA_SOURCE = 'schemas/workflow_catalog.schema.json';

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);

export interface SchemaSlot {
  name: string;
  /** A type string in the site's vocabulary (typeGlyphs reads it): string, boolean, object, array, integer, a|b. */
  type: string;
  required: boolean;
  description: string;
}

export interface CatalogSchema {
  /** The properties of `$defs/step`, in schema order. */
  stepSlots: SchemaSlot[];
  gateActions: string[];
  gatePhases: string[];
  /** Gate actions the schema forbids on an after-gate (its if/then on phase). */
  afterGateForbidden: string[];
  failureActions: string[];
}

function enumOf(node: unknown, where: string): string[] {
  if (!isObj(node) || !Array.isArray(node.enum)) throw new Error(`catalog schema: ${where} has no enum`);
  return node.enum.map(String);
}

/** A property's type as one string. A $ref names the definition, whose type is read in turn. */
export function slotType(node: unknown, defs: Obj, where: string): string {
  if (!isObj(node)) throw new Error(`catalog schema: ${where} is not an object`);
  if (typeof node.$ref === 'string') {
    const name = /^#\/\$defs\/(.+)$/.exec(node.$ref)?.[1];
    if (!name || !(name in defs)) throw new Error(`catalog schema: ${where} refers to ${node.$ref}, which is not defined`);
    return slotType(defs[name], defs, `$defs/${name}`);
  }
  if (typeof node.type === 'string') return node.type;
  if (Array.isArray(node.type)) return node.type.map(String).join('|');
  const alts = Array.isArray(node.oneOf) ? node.oneOf : Array.isArray(node.anyOf) ? node.anyOf : null;
  if (alts) return [...new Set(alts.map((a, i) => slotType(a, defs, `${where} option ${i + 1}`)))].join('|');
  // allOf narrows a type (a duration that is not zero): the type is the first member's that has one.
  if (Array.isArray(node.allOf)) {
    for (const [i, part] of node.allOf.entries()) {
      try {
        return slotType(part, defs, `${where} allOf ${i + 1}`);
      } catch {
        // a member with no type, such as a `not`
      }
    }
  }
  if (Array.isArray(node.enum)) return [...new Set(node.enum.map((v) => (v === null ? 'null' : typeof v)))].join('|');
  throw new Error(`catalog schema: ${where} has no type`);
}

export function buildCatalogSchema(doc: unknown): CatalogSchema {
  if (!isObj(doc) || !isObj(doc.$defs)) throw new Error('catalog schema: no $defs');
  const defs = doc.$defs;
  const step = defs.step;
  if (!isObj(step) || !isObj(step.properties)) throw new Error('catalog schema: $defs/step has no properties');
  const required = new Set(Array.isArray(step.required) ? step.required.map(String) : []);
  const stepSlots = Object.entries(step.properties).map(([name, node]) => ({
    name,
    type: slotType(node, defs, `$defs/step/properties/${name}`),
    required: required.has(name),
    description: isObj(node) && typeof node.description === 'string' ? node.description : '',
  }));
  const gate = defs.gate;
  const fm = defs.failure_mode;
  if (!isObj(gate) || !isObj(gate.properties)) throw new Error('catalog schema: $defs/gate has no properties');
  if (!isObj(fm) || !isObj(fm.properties)) throw new Error('catalog schema: $defs/failure_mode has no properties');
  const gateActions = enumOf(gate.properties.action, '$defs/gate action');
  const gatePhases = enumOf(gate.properties.phase, '$defs/gate phase');
  // The schema's rule for an after-gate: if phase is "after", then action is not one of these.
  const afterGateForbidden: string[] = [];
  const cond = gate.if;
  const then = gate.then;
  if (isObj(cond) && isObj(cond.properties) && isObj(cond.properties.phase) && cond.properties.phase.const === 'after') {
    const action = isObj(then) && isObj(then.properties) ? then.properties.action : undefined;
    const not = isObj(action) ? action.not : undefined;
    if (isObj(not) && typeof not.const === 'string') afterGateForbidden.push(not.const);
    if (isObj(not) && Array.isArray(not.enum)) afterGateForbidden.push(...not.enum.map(String));
  }
  return { stepSlots, gateActions, gatePhases, afterGateForbidden, failureActions: enumOf(fm.properties.action, '$defs/failure_mode action') };
}

let cached: CatalogSchema | null = null;

export function loadCatalogSchema(): CatalogSchema {
  cached ??= buildCatalogSchema(JSON.parse(readRepoFile(CATALOG_SCHEMA_SOURCE)));
  return cached;
}
