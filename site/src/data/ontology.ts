// schemas/capability_ontology.yaml as typed data. Missing safety flags
// default to false, so every capability exports the four booleans.
import { parse } from 'yaml';
import { readRepoFile } from '../lib/repo';

export const ONTOLOGY_SOURCE = 'schemas/capability_ontology.yaml';

export type Risk = 'low' | 'medium' | 'high';
export const RISKS: readonly Risk[] = ['low', 'medium', 'high'];

export const EDGE_TYPES = [
  'requires',
  'soft_requires',
  'enables',
  'precedes',
  'conflicts_with',
  'alternative_to',
  'specializes',
] as const;
export type EdgeType = (typeof EDGE_TYPES)[number];

export type JsonSchemaLite = Record<string, unknown>;
export type EdgeMap = Record<EdgeType, string[]>;

export interface Capability {
  id: string;
  layer: string;
  description: string;
  risk: Risk;
  mutation: boolean;
  requires_checkpoint: boolean;
  requires_approval: boolean;
  mutation_overridable: boolean;
  input_schema: JsonSchemaLite;
  output_schema: JsonSchemaLite;
  edgesOut: EdgeMap;
  edgesIn: EdgeMap;
}

export interface Layer {
  id: string;
  slug: string;
  order: number;
  description: string;
  cognitive_mapping: string;
  capabilities: string[];
}

export interface Edge {
  from: string;
  to: string;
  type: EdgeType;
}

export interface EdgeTypeInfo {
  id: EdgeType;
  description: string;
  semantics: string;
  transitive: boolean;
  symmetric: boolean;
  edges: { from: string; to: string }[];
}

export interface Ontology {
  version: string;
  name: string;
  description: string;
  derivationDoc: string | null;
  layers: Layer[];
  capabilities: Capability[];
  byId: ReadonlyMap<string, Capability>;
  edges: Edge[];
  edgeTypes: EdgeTypeInfo[];
}

type Obj = Record<string, unknown>;

function isObj(v: unknown): v is Obj {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function str(v: unknown, where: string): string {
  if (typeof v !== 'string') throw new Error(`ontology: ${where} must be a string`);
  return v;
}

function bool(v: unknown, where: string): boolean {
  if (v === undefined) return false;
  if (typeof v !== 'boolean') throw new Error(`ontology: ${where} must be a boolean`);
  return v;
}

function emptyEdges(): EdgeMap {
  return Object.fromEntries(EDGE_TYPES.map((t) => [t, [] as string[]])) as EdgeMap;
}

/** Build the ontology from parsed YAML. Exported so tests can feed it bad input. */
export function buildOntology(doc: unknown): Ontology {
  if (!isObj(doc)) throw new Error('ontology: top level is not a mapping');
  const meta = doc.meta;
  if (!isObj(meta)) throw new Error('ontology: meta is missing');
  const derivation = isObj(meta.derivation) ? meta.derivation : {};

  const rawLayers = doc.layers;
  if (!isObj(rawLayers)) throw new Error('ontology: layers is not a mapping');
  const layers: Layer[] = Object.entries(rawLayers).map(([id, l], order) => {
    if (!isObj(l)) throw new Error(`ontology: layer ${id} is not a mapping`);
    const caps = l.capabilities;
    if (!Array.isArray(caps) || !caps.every((c) => typeof c === 'string')) {
      throw new Error(`ontology: layer ${id} capabilities must be a list of ids`);
    }
    return {
      id,
      slug: id.toLowerCase(),
      order,
      description: str(l.description, `layer ${id} description`),
      cognitive_mapping: str(l.cognitive_mapping, `layer ${id} cognitive_mapping`),
      capabilities: caps as string[],
    };
  });
  const layerIds = new Set(layers.map((l) => l.id));

  const rawNodes = doc.nodes;
  if (!Array.isArray(rawNodes)) throw new Error('ontology: nodes is not a list');
  const capabilities: Capability[] = rawNodes.map((n, i) => {
    if (!isObj(n)) throw new Error(`ontology: node ${i} is not a mapping`);
    const id = str(n.id, `node ${i} id`);
    const layer = str(n.layer, `${id}.layer`);
    if (!layerIds.has(layer)) throw new Error(`ontology: ${id} names unknown layer ${layer}`);
    const risk = str(n.risk, `${id}.risk`);
    if (!(RISKS as readonly string[]).includes(risk)) {
      throw new Error(`ontology: ${id}.risk is ${risk}, not low, medium or high`);
    }
    if (!isObj(n.input_schema) || !isObj(n.output_schema)) {
      throw new Error(`ontology: ${id} needs input_schema and output_schema mappings`);
    }
    return {
      id,
      layer,
      description: str(n.description, `${id}.description`),
      risk: risk as Risk,
      mutation: bool(n.mutation, `${id}.mutation`),
      requires_checkpoint: bool(n.requires_checkpoint, `${id}.requires_checkpoint`),
      requires_approval: bool(n.requires_approval, `${id}.requires_approval`),
      mutation_overridable: bool(n.mutation_overridable, `${id}.mutation_overridable`),
      input_schema: n.input_schema,
      output_schema: n.output_schema,
      edgesOut: emptyEdges(),
      edgesIn: emptyEdges(),
    };
  });

  const byId = new Map<string, Capability>();
  for (const c of capabilities) {
    if (byId.has(c.id)) throw new Error(`ontology: duplicate capability id ${c.id}`);
    byId.set(c.id, c);
  }

  // Each layer's list must name exactly the nodes that declare that layer.
  for (const l of layers) {
    const declared = capabilities.filter((c) => c.layer === l.id).map((c) => c.id).sort();
    const listed = [...l.capabilities].sort();
    if (declared.join() !== listed.join()) {
      throw new Error(
        `ontology: layer ${l.id} lists [${listed.join(', ')}] but its nodes are [${declared.join(', ')}]`,
      );
    }
  }

  const rawTypes = doc.edge_types;
  if (!isObj(rawTypes)) throw new Error('ontology: edge_types is not a mapping');
  const typeKeys = Object.keys(rawTypes);
  if (typeKeys.join() !== [...EDGE_TYPES].join()) {
    throw new Error(`ontology: edge_types are [${typeKeys.join(', ')}], expected [${EDGE_TYPES.join(', ')}]`);
  }

  const rawEdges = doc.edges;
  if (!Array.isArray(rawEdges)) throw new Error('ontology: edges is not a list');
  const edges: Edge[] = rawEdges.map((e, i) => {
    if (!isObj(e)) throw new Error(`ontology: edge ${i} is not a mapping`);
    const from = str(e.from, `edge ${i} from`);
    const to = str(e.to, `edge ${i} to`);
    const type = str(e.type, `edge ${i} type`);
    if (!(EDGE_TYPES as readonly string[]).includes(type)) {
      throw new Error(`ontology: edge ${from} -> ${to} has unknown type ${type}`);
    }
    if (!byId.has(from) || !byId.has(to)) {
      throw new Error(`ontology: edge ${from} -> ${to} names a capability that does not exist`);
    }
    return { from, to, type: type as EdgeType };
  });
  for (const e of edges) {
    byId.get(e.from)!.edgesOut[e.type].push(e.to);
    byId.get(e.to)!.edgesIn[e.type].push(e.from);
  }

  const edgeTypes: EdgeTypeInfo[] = EDGE_TYPES.map((id) => {
    const t = rawTypes[id];
    if (!isObj(t)) throw new Error(`ontology: edge type ${id} is not a mapping`);
    return {
      id,
      description: str(t.description, `edge type ${id} description`),
      semantics: str(t.semantics, `edge type ${id} semantics`),
      transitive: bool(t.transitive, `edge type ${id} transitive`),
      symmetric: bool(t.symmetric, `edge type ${id} symmetric`),
      edges: edges.filter((e) => e.type === id).map(({ from, to }) => ({ from, to })),
    };
  });

  return {
    version: str(meta.version, 'meta.version'),
    name: str(meta.name, 'meta.name'),
    description: str(meta.description, 'meta.description'),
    derivationDoc: typeof derivation.documentation === 'string' ? derivation.documentation : null,
    layers,
    capabilities,
    byId,
    edges,
    edgeTypes,
  };
}

let cached: Ontology | undefined;

export function loadOntology(): Ontology {
  cached ??= buildOntology(parse(readRepoFile(ONTOLOGY_SOURCE)));
  return cached;
}

/** The capabilities of one layer, in the layer's own list order. */
export function capabilitiesOfLayer(o: Ontology, layerId: string): Capability[] {
  const layer = o.layers.find((l) => l.id === layerId);
  if (!layer) throw new Error(`ontology: unknown layer ${layerId}`);
  return layer.capabilities.map((id) => o.byId.get(id)!);
}
