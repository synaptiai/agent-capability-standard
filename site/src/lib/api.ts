// The static data API at /api/v1/: the payload of every JSON file, built from
// the same loaders the pages use, and the list of endpoints that the endpoint
// files, the OpenAPI document and the /developers/ page all read. Field names
// are snake_case, like the YAML sources. Every file is an object with the
// same envelope (api_version, version, generated_from) and then its data.
// The pages index (pages.json) is in api-pages.ts, because it reads the
// Markdown copies, which need Astro's content collection.
import { loadDiagnostics, DIAG_RS, type Diagnostic } from '../data/diagnostics';
import { EDGE_TYPES, loadOntology, ONTOLOGY_SOURCE, type Capability, type EdgeMap, type Layer } from '../data/ontology';
import { loadProfiles, type DomainProfile } from '../data/profiles';
import { loadVersions } from '../data/versions';
import { capabilityUsage, CORE_CATALOG, loadWorkflows, type Step, type Workflow } from '../data/workflows';
import { SITE_ORIGIN } from './origin';
import { COMMIT_SHA, GITHUB_BASE } from './repo';
import { kebab, ROUTES } from './routes';

import { OPENAPI_MEDIA_TYPE } from './agent-contract';
import { API_BASE, API_CATALOG_PATH, API_VERSION, DEVELOPERS_URL, OPENAPI_PATH } from './api-paths';

export { API_BASE, API_CATALOG_PATH, API_CATALOG_PROFILE, API_VERSION, DEVELOPERS_URL, OPENAPI_PATH } from './api-paths';
/** The MCP endpoint the worker serves on the same origin. Not a file in dist. */
export const MCP_URL = `${SITE_ORIGIN}/mcp`;
/** The MCP server's tools, by name, as the worker defines them. */
export const MCP_TOOLS: readonly { name: string; does: string }[] = [
  { name: 'search_standard', does: 'Searches the titles, descriptions and headings of the pages, the capability and workflow ids, and each page\'s search terms (its most distinctive words and every diagnostic code it names). Returns ranked matches with their URLs and, for a capability or a workflow, the id to read it by.' },
  { name: 'read_capability', does: 'Returns a capability: its layer, risk, safety flags, input and output schemas and edges.' },
  { name: 'read_workflow', does: 'Returns a workflow with its steps, bindings and effective safety flags.' },
  { name: 'read_page', does: 'Returns the Markdown copy of one page of the site.' },
];

type Json = null | boolean | number | string | Json[] | { [k: string]: Json };
export type JsonObject = { [k: string]: Json };

/** A value read from YAML, as JSON: undefined becomes null. */
function json(v: unknown): Json {
  return v === undefined ? null : (JSON.parse(JSON.stringify(v)) as Json);
}

const abs = (p: string) => `${SITE_ORIGIN}${p}`;

// ------------------------------------------------------------------ envelope

export interface VersionBlock {
  standard: string;
  standard_status: string;
  ontology: string;
  plugin: string;
}

export function versionBlock(): VersionBlock {
  const v = loadVersions();
  return { standard: v.standard.current.version, standard_status: v.standard.current.status, ontology: v.ontology, plugin: v.plugin };
}

export function envelope(sources: string[]): JsonObject {
  return {
    api_version: API_VERSION,
    version: versionBlock() as unknown as JsonObject,
    generated_from: { repository: GITHUB_BASE, commit: COMMIT_SHA, sources },
  };
}

/** The current Standard's file, which the diagnostics and versions come from. */
function standardSource(): string {
  return loadVersions().standard.current.source;
}

// ------------------------------------------------------------------ resources

function edgeMap(m: EdgeMap): JsonObject {
  return Object.fromEntries(EDGE_TYPES.map((t) => [t, [...m[t]]]));
}

export function capabilityUrls(id: string): { page_url: string; markdown_url: string; api_url: string } {
  const page = `/capabilities/${kebab(id)}/`;
  return { page_url: abs(page), markdown_url: abs(`${page}index.md`), api_url: abs(`${API_BASE}/capabilities/${id}.json`) };
}

export function capabilityResource(c: Capability): JsonObject {
  return {
    id: c.id,
    layer: c.layer,
    description: c.description,
    risk: c.risk,
    mutation: c.mutation,
    requires_checkpoint: c.requires_checkpoint,
    requires_approval: c.requires_approval,
    mutation_overridable: c.mutation_overridable,
    input_schema: json(c.input_schema),
    output_schema: json(c.output_schema),
    edges: { outgoing: edgeMap(c.edgesOut), incoming: edgeMap(c.edgesIn) },
    used_in: capabilityUsage(c.id).map((u) => ({ workflow_id: u.workflowId, steps: u.steps })),
    skill_source: `skills/${c.id}/SKILL.md`,
    ...capabilityUrls(c.id),
  };
}

export function layerResource(l: Layer): JsonObject {
  const page = `/layers/${l.slug}/`;
  return {
    id: l.id,
    position: l.order + 1,
    description: l.description,
    cognitive_mapping: l.cognitive_mapping,
    capabilities: [...l.capabilities],
    page_url: abs(page),
    markdown_url: abs(`${page}index.md`),
  };
}

function stepResource(s: Step): JsonObject {
  return {
    index: s.index,
    capability: s.capability,
    layer: s.layer,
    purpose: s.purpose,
    domain: s.domain ?? null,
    declared: {
      risk: json(s.declared.risk),
      mutation: json(s.declared.mutation),
      requires_checkpoint: json(s.declared.requires_checkpoint),
      requires_approval: json(s.declared.requires_approval),
    },
    effective: {
      risk: s.effective.risk,
      mutation: s.effective.mutation,
      requires_checkpoint: s.effective.requires_checkpoint,
      requires_approval: s.effective.requires_approval,
      downgrades: [...s.effective.downgrades],
      checkpoint: { ...s.effective.checkpoint },
    },
    store_as: s.store_as ?? null,
    input_bindings: json(s.input_bindings),
    gates: json(s.gates),
    condition: json(s.condition),
    skip_if_false: s.skip_if_false ?? null,
    parallel_group: s.parallel_group ?? null,
    join: json(s.join),
    workflow_id: s.workflow_id ?? null,
    mapping_ref: s.mapping_ref ?? null,
    failure_modes: json(s.failure_modes),
    timeout: json(s.timeout),
    retry: json(s.retry),
    consumes: [...s.consumes],
    extra: json(s.extra),
  };
}

export function workflowUrls(w: Workflow): { page_url: string; markdown_url: string; api_url: string } {
  const page = `/workflows/${w.slug}/`;
  return { page_url: abs(page), markdown_url: abs(`${page}index.md`), api_url: abs(`${API_BASE}/workflows/${w.id}.json`) };
}

export function workflowResource(w: Workflow): JsonObject {
  return {
    id: w.id,
    slug: w.slug,
    catalog: w.catalog,
    source: w.source,
    standard_version: w.standardVersion,
    domain: w.domain ?? null,
    profile: w.profile ?? null,
    goal: w.goal,
    risk: w.risk,
    description: w.description ?? null,
    success: [...w.success],
    inputs: json(w.inputs),
    steps: w.steps.map(stepResource),
    invoked_by: [...w.invokedBy],
    data_flow: json(w.data_flow),
    risk_propagation: json(w.risk_propagation),
    workflow_extensions: json(w.workflow_extensions),
    triggers: json(w.triggers),
    extra: json(w.extra),
    ...workflowUrls(w),
  };
}

export function profileResource(p: DomainProfile): JsonObject {
  const page = `/domains/${p.key}/`;
  return {
    domain: p.key,
    version: p.version,
    description: p.description,
    profile_file: p.profileFile,
    readme: p.readme,
    workflows: p.workflows.map((w) => ({ id: w.id, defined: w.defined })),
    profile: json(p.profile),
    page_url: abs(page),
    markdown_url: abs(`${page}index.md`),
    api_url: abs(`${API_BASE}/profiles/${p.key}.json`),
  };
}

export function diagnosticResource(d: Diagnostic): JsonObject {
  return {
    code: d.code,
    name: d.name,
    severity: d.severity,
    category: d.category,
    section: d.section,
    description: d.descriptionMd,
    page_url: abs(`/spec/diagnostics/#${d.anchor}`),
  };
}

// ------------------------------------------------------------------ files

function workflowSources(): string[] {
  return [CORE_CATALOG, ...loadWorkflows().domainSources];
}

function profileSources(): string[] {
  return loadProfiles().map((p) => p.profileFile);
}

export function capabilitiesFile(): JsonObject {
  const caps = loadOntology().capabilities;
  return { ...envelope([ONTOLOGY_SOURCE, ...workflowSources()]), count: caps.length, capabilities: caps.map(capabilityResource) };
}

export function capabilityFile(id: string): JsonObject {
  const c = loadOntology().byId.get(id);
  if (!c) throw new Error(`api: unknown capability ${id}`);
  return { ...envelope([ONTOLOGY_SOURCE, ...workflowSources()]), capability: capabilityResource(c) };
}

export function layersFile(): JsonObject {
  const layers = loadOntology().layers;
  return { ...envelope([ONTOLOGY_SOURCE]), count: layers.length, layers: layers.map(layerResource) };
}

export function edgesFile(): JsonObject {
  const o = loadOntology();
  return {
    ...envelope([ONTOLOGY_SOURCE]),
    count: o.edges.length,
    edge_types: o.edgeTypes.map((t) => ({
      id: t.id,
      description: t.description,
      semantics: t.semantics,
      transitive: t.transitive,
      symmetric: t.symmetric,
      count: t.edges.length,
    })),
    edges: o.edges.map((e) => ({ from: e.from, to: e.to, type: e.type })),
  };
}

export function workflowsFile(): JsonObject {
  const all = loadWorkflows().all;
  return { ...envelope(workflowSources()), count: all.length, workflows: all.map(workflowResource) };
}

export function workflowFile(id: string): JsonObject {
  const w = loadWorkflows().byId.get(id);
  if (!w) throw new Error(`api: unknown workflow ${id}`);
  return { ...envelope([w.source]), workflow: workflowResource(w) };
}

export function profilesFile(): JsonObject {
  const ps = loadProfiles();
  return { ...envelope(profileSources()), count: ps.length, profiles: ps.map(profileResource) };
}

export function profileFile(domain: string): JsonObject {
  const p = loadProfiles().find((x) => x.key === domain);
  if (!p) throw new Error(`api: unknown domain ${domain}`);
  return { ...envelope([p.profileFile]), profile: profileResource(p) };
}

export function diagnosticsFile(): JsonObject {
  const ds = loadDiagnostics();
  return { ...envelope([standardSource(), DIAG_RS]), count: ds.length, diagnostics: ds.map(diagnosticResource) };
}

/** The values of each path parameter: every id the data defines. */
export function capabilityIds(): string[] {
  return loadOntology().capabilities.map((c) => c.id);
}
export function workflowIds(): string[] {
  return loadWorkflows().all.map((w) => w.id);
}
export function domainKeys(): string[] {
  return loadProfiles().map((p) => p.key);
}

// ------------------------------------------------------------------ endpoints

export interface Endpoint {
  /** Path as OpenAPI writes it, e.g. /api/v1/capabilities/{id}.json. */
  path: string;
  operationId: string;
  summary: string;
  description: string;
  /** The component schema name of the 200 response. */
  schema: string;
  /** The path parameter, when the path has one. */
  param?: { name: string; description: string; values: () => string[] };
  /** The example the /developers/ page shows for a path with a parameter. */
  example?: () => string;
  /** The file's payload for one parameter value (none for a collection). */
  payload: (value?: string) => JsonObject;
}

export const ENDPOINTS: readonly Endpoint[] = [
  {
    path: `${API_BASE}/index.json`,
    operationId: 'readApiIndex',
    summary: 'List the resources of the API',
    description: 'The entry point: every collection with its URL and size, the versions of the Standard, the ontology and the plugin, and links to the OpenAPI document and the documentation.',
    schema: 'ApiIndex',
    payload: () => indexFile(),
  },
  {
    path: `${API_BASE}/capabilities.json`,
    operationId: 'listCapabilities',
    summary: 'List every capability',
    description: 'Every atomic capability of the ontology in ontology order, each with its layer, risk, safety flags, input and output JSON Schemas, edges and the workflows that use it.',
    schema: 'CapabilityList',
    payload: () => capabilitiesFile(),
  },
  {
    path: `${API_BASE}/capabilities/{id}.json`,
    operationId: 'readCapability',
    summary: 'Read a capability',
    description: 'A capability by id, in the same shape as an item of listCapabilities.',
    schema: 'CapabilityDocument',
    param: { name: 'id', description: 'The capability id, as the ontology spells it.', values: capabilityIds },
    example: () => 'checkpoint',
    payload: (id) => capabilityFile(id!),
  },
  {
    path: `${API_BASE}/layers.json`,
    operationId: 'listLayers',
    summary: 'List the cognitive layers',
    description: 'The layers of the ontology in order, each with the ids of its capabilities.',
    schema: 'LayerList',
    payload: () => layersFile(),
  },
  {
    path: `${API_BASE}/edges.json`,
    operationId: 'listEdges',
    summary: 'List the edges between capabilities',
    description: 'Every edge of the ontology as a from, to and type triple, and the edge types with their semantics.',
    schema: 'EdgeList',
    payload: () => edgesFile(),
  },
  {
    path: `${API_BASE}/workflows.json`,
    operationId: 'listWorkflows',
    summary: 'List every workflow',
    description: 'Every workflow of the reference catalog and the domain catalogs, each with its steps, input bindings and effective safety flags.',
    schema: 'WorkflowList',
    payload: () => workflowsFile(),
  },
  {
    path: `${API_BASE}/workflows/{id}.json`,
    operationId: 'readWorkflow',
    summary: 'Read a workflow',
    description: 'A workflow by its catalog key, in the same shape as an item of listWorkflows.',
    schema: 'WorkflowDocument',
    param: { name: 'id', description: 'The workflow id: its key in the catalog file, with underscores.', values: workflowIds },
    example: () => (workflowIds().includes('model_deployment') ? 'model_deployment' : workflowIds()[0]!),
    payload: (id) => workflowFile(id!),
  },
  {
    path: `${API_BASE}/profiles.json`,
    operationId: 'listProfiles',
    summary: 'List the domain profiles',
    description: 'Every domain profile: trust weights, risk thresholds, checkpoint and evidence policies, and the workflows it lists.',
    schema: 'ProfileList',
    payload: () => profilesFile(),
  },
  {
    path: `${API_BASE}/profiles/{domain}.json`,
    operationId: 'readProfile',
    summary: 'Read a domain profile',
    description: 'A domain profile by its domain key, in the same shape as an item of listProfiles.',
    schema: 'ProfileDocument',
    param: { name: 'domain', description: 'The domain key, as the profile\'s `domain` field spells it.', values: domainKeys },
    example: () => domainKeys()[0]!,
    payload: (d) => profileFile(d!),
  },
  {
    path: `${API_BASE}/diagnostics.json`,
    operationId: 'listDiagnostics',
    summary: 'List the diagnostic codes',
    description: 'Every diagnostic code a conforming validator reports, from the current Standard, with its name, severity and section.',
    schema: 'DiagnosticList',
    payload: () => diagnosticsFile(),
  },
  {
    path: `${API_BASE}/pages.json`,
    operationId: 'listPages',
    summary: 'List every page of the site',
    description: 'Every page of the documentation site with its URL, the URL of its Markdown copy, its title, description, section and H2 and H3 headings. Use it to find the page that answers a question, then read its Markdown copy.',
    schema: 'PageList',
    payload: () => {
      throw new Error('api: pages.json is built by api-pages.ts');
    },
  },
];

/** The file path of an endpoint for one parameter value: /api/v1/capabilities/{id}.json -> …/retrieve.json. */
export function concretePath(e: Endpoint, value?: string): string {
  return e.param ? e.path.replace(`{${e.param.name}}`, value!) : e.path;
}

export function endpointById(operationId: string): Endpoint {
  const e = ENDPOINTS.find((x) => x.operationId === operationId);
  if (!e) throw new Error(`api: no endpoint ${operationId}`);
  return e;
}

export function indexFile(): JsonObject {
  const counts: Record<string, number> = {
    listCapabilities: loadOntology().capabilities.length,
    listLayers: loadOntology().layers.length,
    listEdges: loadOntology().edges.length,
    listWorkflows: loadWorkflows().all.length,
    listProfiles: loadProfiles().length,
    listDiagnostics: loadDiagnostics().length,
    listPages: ROUTES.length,
  };
  return {
    ...envelope([ONTOLOGY_SOURCE, ...workflowSources(), ...profileSources(), standardSource(), '.claude-plugin/plugin.json']),
    openapi_url: abs(OPENAPI_PATH),
    documentation_url: abs(DEVELOPERS_URL),
    resources: ENDPOINTS.filter((e) => e.operationId !== 'readApiIndex').map((e) => ({
      operation_id: e.operationId,
      url: abs(e.path),
      summary: e.summary,
      count: counts[e.operationId] ?? null,
    })),
  };
}

/** The JSON text of a file: two-space indent and a final newline. */
export function jsonText(payload: unknown): string {
  return `${JSON.stringify(payload, null, 2)}\n`;
}

export function jsonResponse(payload: unknown): Response {
  return new Response(jsonText(payload), { headers: { 'Content-Type': 'application/json; charset=utf-8' } });
}


/**
 * The /.well-known/api-catalog linkset (RFC 9727, RFC 9264): one entry for
 * the data API, anchored at its base URL, with its OpenAPI document
 * (service-desc) and its documentation page (service-doc), and the catalog's
 * own entry that lists the API as an item. No status link:
 * the API is static files and has no status endpoint.
 */
export function apiCatalog(): { linkset: JsonObject[] } {
  return {
    linkset: [
      { anchor: abs(API_CATALOG_PATH), item: [{ href: abs(`${API_BASE}/`) }] },
      {
        anchor: abs(`${API_BASE}/`),
        'service-desc': [{ href: abs(OPENAPI_PATH), type: OPENAPI_MEDIA_TYPE }],
        'service-doc': [{ href: abs(DEVELOPERS_URL), type: 'text/html' }],
      },
    ],
  };
}
