// Tests for the data API (src/lib/api.ts) and its OpenAPI document
// (src/lib/openapi.ts). Expected ids and counts come from test/independent.ts
// (line scans of the YAML and Markdown sources) and from plugin.json read
// here, never from the loaders the API is built on. The built files,
// pages.json among them, are checked against the same schemas in dist.test.ts.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { catalogEntries } from '../src/lib/resource-catalog';
import { pageLinks } from '../src/worker/site';
import {
  apiCatalog,
  capabilitiesFile,
  capabilityFile,
  diagnosticsFile,
  edgesFile,
  ENDPOINTS,
  indexFile,
  layersFile,
  profileFile,
  profilesFile,
  workflowFile,
  workflowsFile,
} from '../src/lib/api';
import { openApiDocument } from '../src/lib/openapi';
import {
  allCatalogSteps,
  claudeLayerTable,
  diagnosticRowsPerSection,
  ontologyEdgeTriples,
  profileFiles,
  profileWorkflowIds,
  repoText,
  standardFileVersions,
} from './independent';
import { refsIn, resolveRef, validate } from './json-schema-lite';

type Obj = Record<string, any>;
const doc = openApiDocument() as Obj;
const schemaFor = (name: string) => ({ $ref: `#/components/schemas/${name}` });
const check = (name: string, payload: unknown) => validate(doc, schemaFor(name), payload);

const capIds = claudeLayerTable().flatMap((l) => l.capabilities);
const wfSteps = allCatalogSteps();
const domains = profileFiles().map((f) => f.replace(/\.yaml$/, '').replace(/_/g, '-'));

describe('data API payloads match the sources', () => {
  it('lists every capability in every layer, by the CLAUDE.md layer table', () => {
    const f = capabilitiesFile() as Obj;
    expect([...f.capabilities.map((c: Obj) => c.id)].sort()).toEqual([...capIds].sort());
    expect(f.count).toBe(capIds.length);
    const layers = layersFile() as Obj;
    expect(layers.layers.map((l: Obj) => [l.id, l.capabilities.length])).toEqual(claudeLayerTable().map((r) => [r.id, r.count]));
    expect(layers.layers.map((l: Obj) => l.position)).toEqual(claudeLayerTable().map((_, i) => i + 1));
  });

  it('gives each capability the workflows and steps that use it, by a line scan of the catalogs', () => {
    for (const id of ['checkpoint', 'mutate', 'retrieve']) {
      const expected = [...wfSteps]
        .map(([wf, caps]) => ({ workflow_id: wf, steps: caps.flatMap((c, i) => (c === id ? [i + 1] : [])) }))
        .filter((u) => u.steps.length > 0);
      expect((capabilityFile(id) as Obj).capability.used_in).toEqual(expected);
    }
  });

  it('states checkpoint and mutate flags as the Standard\'s safety model does', () => {
    // CLAUDE.md "Safety Model": mutate and send need a checkpoint and approval; checkpoint itself needs none.
    const caps = new Map((capabilitiesFile() as Obj).capabilities.map((c: Obj) => [c.id, c]));
    for (const id of ['mutate', 'send']) {
      const c = caps.get(id) as Obj;
      expect([c.risk, c.mutation, c.requires_checkpoint, c.requires_approval]).toEqual(['high', true, true, true]);
    }
    expect((caps.get('checkpoint') as Obj).requires_checkpoint).toBe(false);
    expect((caps.get('audit') as Obj).mutation_overridable).toBe(true);
  });

  it('lists every edge of the ontology, and each one on both of its capabilities', () => {
    const triples = ontologyEdgeTriples();
    const f = edgesFile() as Obj;
    expect(f.edges).toEqual(triples);
    expect(f.count).toBe(triples.length);
    const caps = new Map((capabilitiesFile() as Obj).capabilities.map((c: Obj) => [c.id, c]));
    for (const t of triples) {
      expect((caps.get(t.from) as Obj).edges.outgoing[t.type]).toContain(t.to);
      expect((caps.get(t.to) as Obj).edges.incoming[t.type]).toContain(t.from);
    }
    const perType = f.edge_types.reduce((n: number, t: Obj) => n + t.count, 0);
    expect(perType).toBe(triples.length);
  });

  it('lists every workflow of every catalog with its steps in order', () => {
    const f = workflowsFile() as Obj;
    expect(f.workflows.map((w: Obj) => w.id)).toEqual([...wfSteps.keys()]);
    for (const w of f.workflows) expect(w.steps.map((s: Obj) => s.capability)).toEqual(wfSteps.get(w.id));
    const one = workflowFile('model_deployment') as Obj;
    expect(one.workflow.steps.map((s: Obj) => s.capability)).toEqual(wfSteps.get('model_deployment'));
  });

  it('lists every domain profile with the workflows its file lists', () => {
    const f = profilesFile() as Obj;
    expect(f.profiles.map((p: Obj) => p.domain)).toEqual([...domains].sort());
    for (const file of profileFiles()) {
      const domain = file.replace(/\.yaml$/, '').replace(/_/g, '-');
      const p = (profileFile(domain) as Obj).profile;
      expect(p.workflows.map((w: Obj) => w.id)).toEqual(profileWorkflowIds(repoText(`schemas/profiles/${file}`)));
    }
  });

  it('lists every diagnostic code of the current Standard', () => {
    const current = standardFileVersions()[0]!;
    const rows = diagnosticRowsPerSection(repoText(`spec/STANDARD-v${current}.md`));
    const f = diagnosticsFile() as Obj;
    expect(f.count).toBe(Object.values(rows).reduce((a, b) => a + b, 0));
    for (const [section, n] of Object.entries(rows)) expect(f.diagnostics.filter((d: Obj) => d.section === section)).toHaveLength(n);
  });

  it('names the versions and the commit in every file', () => {
    const plugin = JSON.parse(repoText('.claude-plugin/plugin.json')).version;
    for (const f of [indexFile(), capabilitiesFile(), workflowsFile(), diagnosticsFile()] as Obj[]) {
      expect(f.api_version).toBe('v1');
      expect(f.version.standard).toBe(standardFileVersions()[0]);
      expect(f.version.plugin).toBe(plugin);
      expect(f.version.ontology).toBe(/^ {2}version: "?([^"\s]+)"?/m.exec(repoText('schemas/capability_ontology.yaml'))![1]);
      expect(f.generated_from.commit).toMatch(/^[0-9a-f]{40}$/);
    }
  });

  it('points every file URL at an endpoint path', () => {
    const idx = indexFile() as Obj;
    expect(idx.resources.map((r: Obj) => r.operation_id)).toEqual(ENDPOINTS.map((e) => e.operationId).filter((o) => o !== 'readApiIndex'));
    expect(idx.resources.find((r: Obj) => r.operation_id === 'listCapabilities').count).toBe(capIds.length);
    expect((capabilityFile('checkpoint') as Obj).capability.api_url).toBe('https://acs.synapti.ai/api/v1/capabilities/checkpoint.json');
  });
});

describe('OpenAPI document', () => {
  const ops = Object.entries(doc.paths as Obj).map(([path, item]) => ({ path, item: item as Obj, op: (item as Obj).get as Obj }));

  it('is OpenAPI 3.1 with only the fields 3.1 defines at each level', () => {
    expect(doc.openapi).toMatch(/^3\.1\.\d+$/);
    const top = new Set(['openapi', 'info', 'jsonSchemaDialect', 'servers', 'paths', 'webhooks', 'components', 'security', 'tags', 'externalDocs']);
    for (const k of Object.keys(doc)) expect(top.has(k) || k.startsWith('x-'), k).toBe(true);
    expect(typeof doc.info.title).toBe('string');
    expect(typeof doc.info.version).toBe('string');
    const opKeys = new Set(['tags', 'summary', 'description', 'externalDocs', 'operationId', 'parameters', 'requestBody', 'responses', 'callbacks', 'deprecated', 'security', 'servers']);
    for (const { path, item, op } of ops) {
      expect(path.startsWith('/'), path).toBe(true);
      expect(Object.keys(item), path).toEqual(['get']);
      for (const k of Object.keys(op)) expect(opKeys.has(k), `${path} ${k}`).toBe(true);
      for (const p of op.parameters ?? []) {
        expect(Object.keys(p).every((k) => ['name', 'in', 'description', 'required', 'schema', 'example', 'deprecated'].includes(k))).toBe(true);
      }
    }
  });

  it('declares no authentication anywhere, and says so', () => {
    expect(doc.security).toBeUndefined();
    expect(doc.components.securitySchemes).toBeUndefined();
    for (const { op } of ops) expect(op.security).toBeUndefined();
    const d = doc.info.description as string;
    for (const words of ['No authentication', 'Read-only', 'Not paginated', '/api/v1', 'Deprecation', 'Sunset', 'RFC 9457']) expect(d).toContain(words);
  });

  it('gives every operation a unique, verb-led camelCase operationId, a summary and a description', () => {
    const ids = ops.map((o) => o.op.operationId);
    expect(new Set(ids).size).toBe(ids.length);
    for (const { op } of ops) {
      expect(op.operationId).toMatch(/^(list|read)[A-Z][A-Za-z]*$/);
      expect(op.summary.length).toBeGreaterThan(0);
      expect(op.description.length).toBeGreaterThan(op.summary.length);
    }
  });

  it('types each path parameter with an enum of the ids in the sources', () => {
    const want: Record<string, string[]> = {
      '/api/v1/capabilities/{id}.json': capIds,
      '/api/v1/workflows/{id}.json': [...wfSteps.keys()],
      '/api/v1/profiles/{domain}.json': domains,
    };
    const withParams = ops.filter((o) => o.path.includes('{'));
    expect(withParams.map((o) => o.path).sort()).toEqual(Object.keys(want).sort());
    for (const { path, op } of withParams) {
      const name = /\{([^}]+)\}/.exec(path)![1];
      expect(op.parameters).toHaveLength(1);
      const p = op.parameters[0];
      expect([p.name, p.in, p.required, p.schema.type]).toEqual([name, 'path', true, 'string']);
      expect([...p.schema.enum].sort()).toEqual([...want[path]!].sort());
      expect(p.schema.enum).toContain(p.example);
      expect(op.responses['404']).toEqual({ $ref: '#/components/responses/NotFound' });
    }
  });

  it('answers 200 with a JSON schema and 404 with RFC 9457 problem details', () => {
    for (const { op } of ops) expect(Object.keys(op.responses['200'].content)).toEqual(['application/json']);
    const nf = resolveRef(doc, '#/components/responses/NotFound') as Obj;
    expect(Object.keys(nf.content)).toEqual(['application/problem+json']);
    const problem = resolveRef(doc, nf.content['application/problem+json'].schema.$ref) as Obj;
    expect(Object.keys(problem.properties)).toEqual(['type', 'title', 'status', 'detail', 'instance']);
  });

  // The worker answers any /api/ path it cannot read with a 503 problem body
  // and Retry-After (src/worker/site.ts), so every operation documents it.
  it('documents the 503 problem response on every operation, and types each 200 body as an object', () => {
    for (const { op } of ops) {
      expect(op.responses['503'], op.operationId).toEqual({ $ref: '#/components/responses/Unavailable' });
      expect(op.responses['200'].content['application/json'].schema.type, op.operationId).toBe('object');
    }
    const un = resolveRef(doc, '#/components/responses/Unavailable') as Obj;
    expect(un.content['application/problem+json'].schema).toEqual({ $ref: '#/components/schemas/Problem' });
    expect(un.headers['Retry-After'].schema.type).toBe('integer');
  });

  it('resolves every $ref inside the document', () => {
    const refs = refsIn(doc);
    expect(refs.length).toBeGreaterThan(0);
    for (const r of refs) expect(() => resolveRef(doc, r), r).not.toThrow();
  });

  it('describes every payload exactly: each file validates against its response schema', () => {
    const byOp = new Map(ENDPOINTS.map((e) => [e.operationId, e]));
    for (const { op } of ops) {
      const e = byOp.get(op.operationId)!;
      if (op.operationId === 'listPages') continue; // needs the Markdown copies; checked on the build in dist.test.ts
      const schema = op.responses['200'].content['application/json'].schema;
      const values = e.param ? e.param.values() : [undefined];
      for (const v of values) expect(validate(doc, schema, e.payload(v)), `${op.operationId} ${v ?? ''}`).toEqual([]);
    }
  });

  it('catches a payload that drifts from its schema', () => {
    const f = capabilityFile('checkpoint') as Obj;
    expect(check('CapabilityDocument', { ...f, capability: { ...f.capability, risk: 'extreme' } })).toEqual(['$.capability.risk: "extreme" is not in the enum']);
    expect(check('CapabilityDocument', { ...f, capability: { ...f.capability, colour: 'red' } })).toEqual(['$.capability: colour is not in the schema']);
    const { count: _c, ...noCount } = edgesFile() as Obj;
    expect(check('EdgeList', noCount)).toEqual(['$: missing count']);
  });
});

describe('media types the site names for the files it serves', () => {
  // The Content-Type public/_headers gives a path, without parameters: what
  // a client gets. Every link, catalog entry and Link header that names the
  // file's type must say the same.
  function served(file: string): string {
    const lines = readFileSync('public/_headers', 'utf8').split('\n');
    const at = lines.indexOf(file);
    expect(at, `${file} in _headers`).toBeGreaterThan(-1);
    const m = /^\s+Content-Type:\s*([^;\s]+)/.exec(lines[at + 1] ?? '');
    expect(m, `${file} Content-Type`).not.toBeNull();
    return m![1]!;
  }

  it('names the OpenAPI document by the type it is served with', () => {
    const type = served('/openapi.json');
    const api = apiCatalog().linkset.find((e) => e.anchor === 'https://acs.synapti.ai/api/v1/') as Obj;
    expect(api['service-desc'][0].type).toBe(type);
    expect(catalogEntries().find((e) => e.url.endsWith('/openapi.json'))!.type).toBe(type);
    expect(pageLinks('/')).toContain(`</openapi.json>; rel="service-desc"; type="${type}"`);
  });

  it('names llms.txt by the type it is served with', () => {
    expect(catalogEntries().find((e) => e.url.endsWith('/llms.txt'))!.type).toBe(served('/llms.txt'));
  });
});

describe('api-catalog', () => {
  it('anchors the API at /api/v1/ and links its OpenAPI document and documentation, with no status link', () => {
    const c = apiCatalog();
    const api = c.linkset.find((e) => e.anchor === 'https://acs.synapti.ai/api/v1/') as Obj;
    expect(api['service-desc'][0].href).toBe('https://acs.synapti.ai/openapi.json');
    expect(api['service-doc'][0].href).toBe('https://acs.synapti.ai/developers/');
    expect(c.linkset.some((e) => 'status' in e)).toBe(false);
    expect((c.linkset.find((e) => e.anchor === 'https://acs.synapti.ai/.well-known/api-catalog') as Obj).item).toEqual([{ href: 'https://acs.synapti.ai/api/v1/' }]);
  });
});
