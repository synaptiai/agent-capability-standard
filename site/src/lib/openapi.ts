// /openapi.json: an OpenAPI 3.1 description of the static data API, built
// from the endpoint list in api.ts. Self-contained: every $ref points into
// this document's own components. Path parameters list every id the data
// defines as an enum, so a client cannot ask for a file that does not exist.
import { EDGE_TYPES, RISKS } from '../data/ontology';
import { API_BASE, API_VERSION, DEVELOPERS_URL, ENDPOINTS, capabilityIds, workflowIds } from './api';
import { SITE_ORIGIN } from './origin';
import { GITHUB_BASE, readRepoFile } from './repo';
import { SECTIONS } from './routes';

/** The version of this API's contract. Its major number is the /api/v<major> path. */
export const API_CONTRACT_VERSION = '1.0.0';
if (`v${API_CONTRACT_VERSION.split('.')[0]}` !== API_VERSION) throw new Error('openapi: API_CONTRACT_VERSION and API_VERSION disagree');

export const API_TITLE = 'Agent Capability Standard API';

type Schema = Record<string, unknown>;

const ref = (name: string): Schema => ({ $ref: `#/components/schemas/${name}` });
const str = (description: string, extra: Schema = {}): Schema => ({ type: 'string', description, ...extra });
const nullable = (type: string, description: string): Schema => ({ type: [type, 'null'], description });
const bool = (description: string): Schema => ({ type: 'boolean', description });
const int = (description: string, minimum = 0): Schema => ({ type: 'integer', minimum, description });
const arr = (items: Schema, description: string): Schema => ({ type: 'array', items, description });
const any = (description: string): Schema => ({ description });
const url = (description: string): Schema => str(description, { format: 'uri' });

/** An object whose every listed property is required and that allows no other. */
function obj(description: string, properties: Record<string, Schema>): Schema {
  return { type: 'object', description, properties, required: Object.keys(properties), additionalProperties: false };
}

/** The fields every file starts with. */
function envelopeProps(): Record<string, Schema> {
  return {
    api_version: str('The API version, the same as the path segment.', { const: API_VERSION }),
    version: ref('VersionBlock'),
    generated_from: ref('GeneratedFrom'),
  };
}

function collection(description: string, key: string, item: string, extra: Record<string, Schema> = {}): Schema {
  return obj(description, {
    ...envelopeProps(),
    count: int(`The number of items in \`${key}\`. Collections are not paginated, so this is the size of the whole collection.`),
    ...extra,
    [key]: arr(ref(item), 'Every item, in source order.'),
  });
}

function single(description: string, key: string, item: string): Schema {
  return obj(description, { ...envelopeProps(), [key]: ref(item) });
}

function schemas(): Record<string, Schema> {
  const edgeMap = obj(
    'Capability ids by edge type. Every edge type is present; an empty list means no edge of that type.',
    Object.fromEntries(EDGE_TYPES.map((t) => [t, arr(ref('CapabilityId'), `Capabilities on the other end of a \`${t}\` edge.`)])),
  );
  const urls = (what: string) => ({
    page_url: url(`The HTML page of the ${what}.`),
    markdown_url: url(`The Markdown copy of that page.`),
  });
  return {
    CapabilityId: str('A capability id from the ontology.', { enum: capabilityIds() }),
    Risk: str('A risk level.', { enum: [...RISKS] }),
    VersionBlock: obj('The versions this file was built from.', {
      standard: str('The current version of the Standard.'),
      standard_status: str('The status of that version, e.g. "Candidate Standard".'),
      ontology: str('The version of the capability ontology.'),
      plugin: str('The version of the Claude Code plugin.'),
    }),
    GeneratedFrom: obj('Where the data comes from.', {
      repository: url('The source repository.'),
      commit: str('The commit the site was built from.', { pattern: '^[0-9a-f]{40}$' }),
      sources: arr(str('A repository path.'), 'The repository files the data is read from.'),
    }),
    Capability: obj('An atomic capability of the ontology.', {
      id: ref('CapabilityId'),
      layer: str('The id of the layer it belongs to.'),
      description: str('What the capability does.'),
      risk: ref('Risk'),
      mutation: bool('Whether it changes state.'),
      requires_checkpoint: bool('Whether a checkpoint must run before it.'),
      requires_approval: bool('Whether it needs approval before it runs.'),
      mutation_overridable: bool('Whether a workflow step may declare `mutation: false` for it.'),
      input_schema: { type: 'object', description: 'The JSON Schema of its input, as the ontology states it.' },
      output_schema: { type: 'object', description: 'The JSON Schema of its output, as the ontology states it.' },
      edges: obj('Its edges in the ontology.', {
        outgoing: { ...edgeMap, description: 'Edges from this capability, by type.' },
        incoming: { ...edgeMap, description: 'Edges to this capability, by type.' },
      }),
      used_in: arr(
        obj('A workflow that uses the capability.', {
          workflow_id: str('The workflow id.'),
          steps: arr(int('A 1-based step number.', 1), 'The steps that run the capability.'),
        }),
        'Every workflow with a step that runs it, in catalog order.',
      ),
      skill_source: str('The repository path of its skill file.'),
      ...urls('capability'),
      api_url: url('This capability\'s file in the API.'),
    }),
    Layer: obj('A cognitive layer.', {
      id: str('The layer id, e.g. PERCEIVE.'),
      position: int('Its position in the ontology, from 1.', 1),
      description: str('What the layer is for.'),
      cognitive_mapping: str('The cognitive function it maps to.'),
      capabilities: arr(ref('CapabilityId'), 'Its capabilities, in the layer\'s own order.'),
      ...urls('layer'),
    }),
    EdgeType: obj('A kind of edge between capabilities.', {
      id: str('The edge type.', { enum: [...EDGE_TYPES] }),
      description: str('What the edge means.'),
      semantics: str('How a validator applies it.'),
      transitive: bool('Whether it is transitive.'),
      symmetric: bool('Whether it is symmetric.'),
      count: int('The number of edges of this type.'),
    }),
    Edge: obj('An edge of the ontology.', {
      from: ref('CapabilityId'),
      to: ref('CapabilityId'),
      type: str('The edge type.', { enum: [...EDGE_TYPES] }),
    }),
    Step: obj('A workflow step. Fields the step does not set are null.', {
      index: int('Its 1-based position in the workflow.', 1),
      capability: ref('CapabilityId'),
      layer: str('The layer of its capability.'),
      purpose: str('What the step is for; empty when the step does not say.'),
      domain: nullable('string', 'The `domain` parameter of the capability, when set.'),
      declared: obj('The safety flags the step itself declares; null where it declares none.', {
        risk: any('The declared risk, as written.'),
        mutation: any('The declared mutation flag, as written.'),
        requires_checkpoint: any('The declared requires_checkpoint flag, as written.'),
        requires_approval: any('The declared requires_approval flag, as written.'),
      }),
      effective: obj('The flags that apply: the stricter of the step\'s declaration and the ontology (Standard section 5.2.1).', {
        risk: ref('Risk'),
        mutation: bool('Effective mutation flag.'),
        requires_checkpoint: bool('Effective requires_checkpoint flag.'),
        requires_approval: bool('Effective requires_approval flag.'),
        downgrades: arr(str('A safety flag.', { enum: ['risk', 'mutation', 'requires_checkpoint', 'requires_approval'] }), 'Flags the step declares weaker than the ontology; each is warning W602.'),
        checkpoint: obj('Whether a checkpoint step must run before this step.', {
          needed: bool('Whether one must.'),
          via: { type: ['string', 'null'], enum: ['requires-edge', 'flag', null], description: 'Why: the ontology\'s requires edge from checkpoint, or the flag.' },
          code: { type: ['string', 'null'], enum: ['V102', 'F501', null], description: 'The diagnostic a validator reports when no checkpoint runs before it.' },
        }),
      }),
      store_as: nullable('string', 'The name its output is stored under.'),
      input_bindings: { type: 'object', description: 'Its input bindings, as written; `${...}` references name earlier outputs or workflow inputs.' },
      gates: any('Its gates, as written, or null.'),
      condition: any('Its condition, as written, or null.'),
      skip_if_false: nullable('boolean', 'Whether a false condition skips the step.'),
      parallel_group: nullable('string', 'The parallel group it runs in.'),
      join: any('Its join, as written, or null.'),
      workflow_id: nullable('string', 'The workflow it invokes.'),
      mapping_ref: nullable('string', 'The repository path of its transform mapping.'),
      failure_modes: any('Its failure modes, as written, or null.'),
      timeout: any('Its timeout, as written, or null.'),
      retry: any('Its retry policy, as written, or null.'),
      consumes: arr(str('A store_as name.'), 'Outputs of earlier steps this step reads.'),
      extra: { type: 'object', description: 'Any other keys of the step, as written.' },
    }),
    Workflow: obj('A workflow from the reference catalog or a domain catalog. Fields the workflow does not set are null.', {
      id: str('The workflow id: its catalog key.', { enum: workflowIds() }),
      slug: str('The id with hyphens, as its page URL uses it.'),
      catalog: str('Which catalog defines it.', { enum: ['core', 'domain'] }),
      source: str('The repository path of its catalog file.'),
      standard_version: nullable('string', 'The Standard version the catalog file declares.'),
      domain: nullable('string', 'Its domain, for a domain workflow.'),
      profile: nullable('string', 'The repository path of its domain profile.'),
      goal: str('What the workflow achieves.'),
      risk: ref('Risk'),
      description: nullable('string', 'A longer description.'),
      success: arr(str('A success criterion.'), 'Its success criteria.'),
      inputs: { type: 'object', description: 'Its inputs, as written.' },
      steps: arr(ref('Step'), 'Its steps, in order.'),
      invoked_by: arr(str('A workflow id.'), 'Workflows with a step that invokes this one.'),
      data_flow: any('Its data flow, as written, or null.'),
      risk_propagation: any('Its risk propagation, as written, or null.'),
      workflow_extensions: any('Its extensions, as written, or null.'),
      triggers: any('Its triggers, as written, or null.'),
      extra: { type: 'object', description: 'Any other keys of the workflow, as written.' },
      ...urls('workflow'),
      api_url: url('This workflow\'s file in the API.'),
    }),
    Profile: obj('A domain profile.', {
      domain: str('The domain key.'),
      version: str('The profile version.'),
      description: str('What the profile is for; empty when it does not say.'),
      profile_file: str('The repository path of the profile.'),
      readme: nullable('string', 'The repository path of the domain\'s README.'),
      workflows: arr(
        obj('A workflow the profile lists.', {
          id: str('The workflow id.'),
          defined: bool('Whether a catalog defines it; false for a proposed workflow.'),
        }),
        'The workflows the profile lists.',
      ),
      profile: { type: 'object', description: 'The whole profile file: trust weights, risk thresholds, checkpoint and evidence policies.' },
      ...urls('domain'),
      api_url: url('This profile\'s file in the API.'),
    }),
    Diagnostic: obj('A diagnostic code of the current Standard.', {
      code: str('The code, e.g. V102.', { pattern: '^[A-Z][0-9]{3}$' }),
      name: str('Its name, in capitals.'),
      severity: str('Whether a validator reports it as an error or a warning.', { enum: ['error', 'warning'] }),
      category: str('The heading of its Standard section.'),
      section: str('The Standard section number, e.g. 9.2.'),
      description: str('What it means, in Markdown.'),
      page_url: url('Its entry on the diagnostics page.'),
    }),
    Page: obj('A page of the documentation site.', {
      url: url('The HTML page.'),
      markdown_url: url('Its Markdown copy.'),
      title: str('The page title.'),
      description: nullable('string', 'A one-paragraph summary.'),
      section: str('The site section id.', { enum: SECTIONS.map((s) => s.id) }),
      section_label: str('The site section, as the navigation names it.'),
      group: nullable('string', 'Its group in the section\'s sidebar.'),
      source: nullable('string', 'The repository path of its Markdown source; null for a page built from data.'),
      headings: arr(
        obj('A heading of the page.', { level: { type: 'integer', enum: [2, 3], description: 'The heading level.' }, text: str('The heading text.') }),
        'Its H2 and H3 headings, in order.',
      ),
      search_terms: str(
        'Words for search, separated by spaces: every diagnostic code the page names, and the words that most set its text apart from the other pages, lower case and stemmed ("mutation" becomes "mutat"). The MCP server\'s search_standard tool matches query words against them.',
      ),
    }),
    ApiIndex: obj('The entry point of the API.', {
      ...envelopeProps(),
      openapi_url: url('This OpenAPI document.'),
      documentation_url: url('The documentation of the API and the other ways agents can read the site.'),
      resources: arr(
        obj('One operation of the API.', {
          operation_id: str('Its operationId in the OpenAPI document.'),
          url: str('Its URL; `{...}` marks a path parameter.'),
          summary: str('What it returns.'),
          count: nullable('integer', 'The size of the collection, for a list operation.'),
        }),
        'Every operation but this one.',
      ),
    }),
    CapabilityList: collection('Every capability.', 'capabilities', 'Capability'),
    CapabilityDocument: single('A capability.', 'capability', 'Capability'),
    LayerList: collection('Every layer.', 'layers', 'Layer'),
    EdgeList: collection('Every edge, and the edge types.', 'edges', 'Edge', { edge_types: arr(ref('EdgeType'), 'The edge types, in ontology order.') }),
    WorkflowList: collection('Every workflow.', 'workflows', 'Workflow'),
    WorkflowDocument: single('A workflow.', 'workflow', 'Workflow'),
    ProfileList: collection('Every domain profile.', 'profiles', 'Profile'),
    ProfileDocument: single('A domain profile.', 'profile', 'Profile'),
    DiagnosticList: collection('Every diagnostic code.', 'diagnostics', 'Diagnostic'),
    PageList: collection('Every page of the site.', 'pages', 'Page'),
    Problem: {
      type: 'object',
      description: 'An error, as RFC 9457 problem details (media type application/problem+json).',
      properties: {
        type: str('A URI that identifies the kind of problem.', { format: 'uri-reference' }),
        title: str('A short summary of the kind of problem.'),
        status: int('The HTTP status code.', 400),
        detail: str('What went wrong with this request.'),
        instance: str('The path that was requested.', { format: 'uri-reference' }),
      },
      required: ['type', 'title', 'status'],
    },
  };
}

export function apiDescription(): string {
  return [
    'The data of the Agent Capability Standard as static JSON: the capability ontology (capabilities with their input and output schemas, risk and safety flags, layers and edges), the reference and domain workflows with their steps, the domain profiles, the diagnostic codes, and an index of every page of the documentation site.',
    '',
    '- **Open.** No authentication and no API key. Every operation is a plain GET; send no credentials.',
    '- **Read-only.** The files are built from the source repository at the commit in `generated_from.commit`, and change only when the site is rebuilt.',
    '- **Not paginated.** Each list operation returns the full collection in one response, with its size in `count`.',
    `- **Versioned path.** The major version is in the path (\`${API_BASE}\`). Adding a field or a file is not a breaking change. Removing or renaming one gets a new major path (\`/api/v2\`). The old path then stays available for at least one minor version of the Standard, and its responses carry \`Deprecation\` and \`Sunset\` headers before it is removed.`,
    `- **Errors.** A path under \`${API_BASE}\` that names no file returns 404 with an RFC 9457 problem details body (\`application/problem+json\`).`,
    '',
    `Documentation, curl examples and the other ways agents can read the site (Markdown copies, llms.txt, an MCP server): ${SITE_ORIGIN}${DEVELOPERS_URL}`,
  ].join('\n');
}

function licence(): string {
  const p = JSON.parse(readRepoFile('.claude-plugin/plugin.json')) as { license?: unknown };
  if (typeof p.license !== 'string') throw new Error('openapi: plugin.json has no license');
  return p.license;
}

const TAGS: Record<string, string> = {
  readApiIndex: 'index',
  listCapabilities: 'ontology',
  readCapability: 'ontology',
  listLayers: 'ontology',
  listEdges: 'ontology',
  listWorkflows: 'workflows',
  readWorkflow: 'workflows',
  listProfiles: 'profiles',
  readProfile: 'profiles',
  listDiagnostics: 'diagnostics',
  listPages: 'site',
};

export function openApiDocument(): Record<string, unknown> {
  const paths: Record<string, unknown> = {};
  for (const e of ENDPOINTS) {
    const tag = TAGS[e.operationId];
    if (!tag) throw new Error(`openapi: ${e.operationId} has no tag`);
    const responses: Record<string, unknown> = {
      '200': { description: e.summary, content: { 'application/json': { schema: ref(e.schema) } } },
    };
    if (e.param) responses['404'] = { $ref: '#/components/responses/NotFound' };
    const op: Record<string, unknown> = { operationId: e.operationId, summary: e.summary, description: e.description, tags: [tag], responses };
    if (e.param) {
      op.parameters = [
        {
          name: e.param.name,
          in: 'path',
          required: true,
          description: e.param.description,
          schema: { type: 'string', enum: e.param.values() },
          example: e.example!(),
        },
      ];
    }
    paths[e.path] = { get: op };
  }
  return {
    openapi: '3.1.1',
    jsonSchemaDialect: 'https://spec.openapis.org/oas/3.1/dialect/base',
    info: {
      title: API_TITLE,
      version: API_CONTRACT_VERSION,
      summary: 'Open, read-only JSON data of the Agent Capability Standard.',
      description: apiDescription(),
      contact: { name: 'Agent Capability Standard on GitHub', url: `${GITHUB_BASE}/issues` },
      license: { name: licence(), identifier: licence() },
    },
    servers: [{ url: SITE_ORIGIN, description: 'The documentation site, which serves the files.' }],
    externalDocs: { description: 'API and agent access', url: `${SITE_ORIGIN}${DEVELOPERS_URL}` },
    tags: [
      { name: 'index', description: 'The entry point.' },
      { name: 'ontology', description: 'Capabilities, layers and edges.' },
      { name: 'workflows', description: 'Reference and domain workflows.' },
      { name: 'profiles', description: 'Domain profiles.' },
      { name: 'diagnostics', description: 'Diagnostic codes of the Standard.' },
      { name: 'site', description: 'The pages of the documentation site.' },
    ],
    paths,
    components: {
      schemas: schemas(),
      responses: {
        NotFound: {
          description: 'No file at this path: the id is not one the enum lists.',
          content: { 'application/problem+json': { schema: ref('Problem') } },
        },
      },
    },
  };
}
