import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { checkRoutes, DIRECTORY_MAP, markdownPages, publicMarkdown, ROUTES, type Route, type Section } from '../src/lib/routes';
import { claudeLayerTable, repoText, standardFileVersions, topLevelKeys } from './independent';

// The public set is computed here from `git ls-files` and the plan's
// exclusion list (plan "Recommended defaults" item 12), written out
// independently of src/lib/routes.ts. `.github/` is added because its only
// .md file is the pull request template, and `.claude/` because it holds
// agent configuration and memory.
const REPO = path.resolve(process.cwd(), '..');
const tracked = execFileSync('git', ['ls-files', '-z'], { cwd: REPO, encoding: 'utf8' })
  .split('\0')
  .filter(Boolean);
const PLAN_EXCLUDED = [
  /^_archive\//,
  /^analysis\//,
  /^tasks\//,
  /^docs\/reviews\//,
  /^docs\/research\/raw_data\//,
  /^skills\/[^/]+\/reference\//,
  /^CLAUDE\.md$/,
  /^\.github\//,
  /^\.claude\//,
];
const publicMd = tracked.filter((p) => p.endsWith('.md') && !PLAN_EXCLUDED.some((re) => re.test(p)));

const bySource = new Map(ROUTES.filter((r) => r.source !== null).map((r) => [r.source!, r]));
const byUrl = new Map(ROUTES.map((r) => [r.url, r]));

describe('exclusions', () => {
  it('gives no page to agent configuration and memory under .claude/', () => {
    // The flow plugin commits its agent memory as Markdown under .claude/agent-memory/.
    expect(publicMarkdown(['.claude/agent-memory/flow-convention-checker/MEMORY.md', '.claude/commands/x.md', 'docs/FAQ.md'])).toEqual([
      'docs/FAQ.md',
    ]);
  });
});

describe('route table against the repository', () => {
  it('routes every public Markdown file exactly once', () => {
    const missing = publicMd.filter((p) => !bySource.has(p));
    expect(missing).toEqual([]);
    const sources = ROUTES.flatMap((r) => (r.source ? [r.source] : []));
    expect(new Set(sources).size).toBe(sources.length);
  });

  it('routes no file outside the public set', () => {
    const extra = [...bySource.keys()].filter((s) => !publicMd.includes(s));
    expect(extra).toEqual([]);
  });

  it('uses each URL once', () => {
    expect(byUrl.size).toBe(ROUTES.length);
  });

  it('gives no route to excluded files', () => {
    for (const p of ['CLAUDE.md', '.github/pull_request_template.md', 'tasks/todo.md']) {
      expect(bySource.has(p)).toBe(false);
    }
  });

  // Expected URLs: design.md "review" section 1, resolutions 3-7 and 22-23.
  it.each([
    ['README.md', '/start/overview/'],
    ['docs/QUICKSTART.md', '/start/quickstart/'],
    ['spec/STANDARD-v1.1.0.md', '/spec/1.1.0/'],
    ['spec/STANDARD-v1.0.0.md', '/spec/1.0.0/'],
    ['spec/RFC-0001-agent-capability-ontology-and-workflow-dsl.md', '/rfcs/0001/'],
    ['spec/RFC-0004-agent-identity.md', '/rfcs/0004/'],
    ['docs/proposals/OASF_SAFETY_EXTENSIONS.md', '/rfcs/proposals/oasf-safety-extensions/'],
    ['docs/methodology/EXTENSION_GOVERNANCE.md', '/spec/extending/'],
    ['skills/capability-gap-analysis/SKILL.md', '/guides/skills/capability-gap-analysis/'],
    ['skills/digital-twin-sync-loop/SKILL.md', '/guides/skills/digital-twin-sync-loop/'],
    ['skills/detect/SKILL.md', '/capabilities/detect/'],
    ['benchmarks/README.md', '/background/research/benchmarks/'],
    ['tests/conformance/contrib/README.md', '/spec/conformance/contributed-fixtures/'],
    ['docs/compliance/iso42001/README.md', '/compliance/iso-42001/'],
    ['docs/domains/data-analysis/README.md', '/domains/data-analysis/'],
    ['docs/guides/ORCHESTRATION_EXTENSIONS.md', '/guides/orchestration-extensions/'],
  ])('routes %s to %s', (source, url) => {
    expect(bySource.get(source)?.url).toBe(url);
  });

  // Generated pages named in design.md "ia-home" section 3 and the review.
  it.each([
    '/',
    '/start/',
    '/capabilities/',
    '/layers/perceive/',
    '/workflows/',
    '/workflows/debug-code-change/',
    '/spec/diagnostics/',
    '/spec/schemas/',
    '/community/citation/',
  ])('has the generated page %s', (url) => {
    expect(byUrl.has(url)).toBe(true);
  });

  it('has no per-schema or profile-format pages (review resolution 6)', () => {
    expect(ROUTES.some((r) => r.url.startsWith('/reference/'))).toBe(false);
    expect(byUrl.has('/domains/profile-format/')).toBe(false);
  });

  it('leaves out the templates Phase 1 deleted', () => {
    expect(bySource.has('templates/capability_atoms.md')).toBe(false);
    expect(bySource.has('templates/output_contracts_full.md')).toBe(false);
  });

  it('tracks no YAML file under site/ (tests/test_core_yaml.py would load it)', () => {
    expect(tracked.filter((p) => p.startsWith('site/') && /\.ya?ml$/.test(p))).toEqual([]);
  });
});

// Sidebar order, copied from design.md "ia-home" section 3. Rows the design
// did not list (README, contributed fixtures) are filtered out before comparing.
describe('sidebar order', () => {
  const urlsOf = (section: Section) =>
    ROUTES.filter((r) => r.section === section)
      .sort((a, b) => a.order - b.order)
      .map((r) => r.url);
  const only = (urls: string[], keep: string[]) => urls.filter((u) => keep.includes(u));

  it('orders the Specification section', () => {
    // Newest Standard first and older versions last, by the spec/ file names.
    const [newest, ...older] = standardFileVersions();
    const expected = [
      `/spec/${newest}/`,
      '/spec/conformance/',
      '/spec/edge-types/',
      '/spec/diagnostics/',
      '/spec/security/',
      '/spec/schemas/',
      '/spec/extending/',
      '/spec/changelog/',
      ...older.map((v) => `/spec/${v}/`),
    ];
    expect(only(urlsOf('spec'), expected)).toEqual(expected);
  });

  it('orders the EU AI Act sub-group', () => {
    const eu = urlsOf('compliance').filter((u) => u.startsWith('/compliance/eu-ai-act/'));
    expect(eu).toEqual([
      '/compliance/eu-ai-act/',
      '/compliance/eu-ai-act/risk-classification/',
      '/compliance/eu-ai-act/annex-iv-technical-documentation/',
      '/compliance/eu-ai-act/quality-management-system/',
      '/compliance/eu-ai-act/post-market-monitoring/',
      '/compliance/eu-ai-act/notified-body-assessment/',
    ]);
  });

  it('orders the reference workflows as the core catalog does', () => {
    const ref = ROUTES.filter((r) => r.group === 'Reference workflows')
      .sort((a, b) => a.order - b.order)
      .map((r) => r.url.split('/')[2]);
    // Top-level keys of schemas/workflow_catalog.yaml by a line scan, '_' read as '-'.
    const keys = topLevelKeys(repoText('schemas/workflow_catalog.yaml'));
    expect(keys).toContain('debug_code_change');
    expect(ref).toEqual(keys.map((k) => k.replace(/_/g, '-')));
  });

  it('orders the Community section', () => {
    expect(urlsOf('community')).toEqual([
      '/community/',
      '/community/contributing/',
      '/community/governance/',
      '/community/code-of-conduct/',
      '/community/roadmap/',
      '/community/release-notes/',
      '/community/citation/',
      '/community/press-kit/',
    ]);
  });

  it('puts each layer page before its capabilities, in ontology order', () => {
    // The CLAUDE.md layer table, which lists each layer's capabilities in ontology order.
    const expected = [
      '/capabilities/',
      ...claudeLayerTable().flatMap((l) => [
        `/layers/${l.id.toLowerCase()}/`,
        ...l.capabilities.map((c) => `/capabilities/${c}/`),
      ]),
    ];
    const caps = urlsOf('capabilities');
    expect(caps.slice(0, expected.length)).toEqual(expected);
  });
});

describe('directory map', () => {
  // design.md "pipeline" section 3, "Directory links".
  it.each([
    ['docs/compliance', '/compliance/'],
    ['docs/compliance/iso42001', '/compliance/iso-42001/'],
    ['docs/domains', '/domains/'],
    ['docs/domains/healthcare', '/domains/healthcare/'],
    ['skills/detect', '/capabilities/detect/'],
    ['spec', '/spec/1.1.0/'],
  ])('maps %s to %s', (dir, url) => {
    expect(DIRECTORY_MAP[dir]).toBe(url);
  });

  it('does not map the excluded raw data folder', () => {
    expect(DIRECTORY_MAP['docs/research/raw_data']).toBeUndefined();
  });
});

describe('checkRoutes on a broken table', () => {
  const ok: Route = { source: 'docs/A.md', url: '/a/', section: 'guides', order: 0, template: 'prose', title: 'A' };
  const files = new Set(['docs/A.md', 'docs/B.md', 'CLAUDE.md', 'tasks/x.md', 'schemas/x.yaml']);

  it('passes a table that covers every public file', () => {
    const b: Route = { ...ok, source: 'docs/B.md', url: '/b/' };
    expect(checkRoutes([ok, b], files)).toEqual([]);
  });

  it('reports a public file with no route', () => {
    expect(checkRoutes([ok], files)).toEqual(['docs/B.md: public Markdown with no route']);
  });

  it('reports a duplicate URL', () => {
    const b: Route = { ...ok, source: 'docs/B.md' };
    expect(checkRoutes([ok, b], files)).toEqual(['/a/: used by docs/A.md and docs/B.md']);
  });

  it('reports a routed excluded file', () => {
    const b: Route = { ...ok, source: 'docs/B.md', url: '/b/' };
    const c: Route = { ...ok, source: 'CLAUDE.md', url: '/c/' };
    expect(checkRoutes([ok, b, c], files)).toEqual(['CLAUDE.md: routed but excluded']);
  });

  it('reports a source git does not track', () => {
    const b: Route = { ...ok, source: 'docs/B.md', url: '/b/' };
    const c: Route = { ...ok, source: 'docs/C.md', url: '/c/' };
    expect(checkRoutes([ok, b, c], files)).toEqual(['docs/C.md: routed but not tracked by git']);
  });

  it('reports a file routed twice', () => {
    const b: Route = { ...ok, source: 'docs/B.md', url: '/b/' };
    const again: Route = { ...ok, url: '/a2/' };
    expect(checkRoutes([ok, b, again], files)).toEqual(['docs/A.md: routed twice (/a/ and /a2/)']);
  });

  it('reports a workflow that takes a reserved slug', () => {
    const b: Route = { ...ok, source: 'docs/B.md', url: '/b/' };
    const wf: Route = { source: null, url: '/workflows/patterns/', section: 'workflows', order: 1, template: 'workflow', title: 'x' };
    expect(checkRoutes([ok, b, wf], files)).toEqual(['/workflows/patterns/: workflow slug patterns is reserved']);
  });

  it('reports a mapped directory that is missing or points nowhere', () => {
    const b: Route = { ...ok, source: 'docs/B.md', url: '/b/' };
    expect(checkRoutes([ok, b], files, { docs: '/a/', nowhere: '/a/', schemas: '/missing/' })).toEqual([
      'nowhere/: mapped but no tracked file is in it',
      'schemas/: maps to /missing/, which is not a route',
    ]);
  });

  it('reports a URL without the trailing slash', () => {
    const b: Route = { ...ok, source: 'docs/B.md', url: '/b' };
    expect(checkRoutes([ok, b], files)).toEqual(['/b: URL must look like /a/b/']);
  });
});

describe('pages that render a Markdown source on their own', () => {
  // Design notes, "ia-home" section 3: the prose, spec, RFC, skill and raw
  // templates show one source each. Capability, domain and edge-type pages
  // (and the domains overview) wrap their source in a generated page instead.
  const own = new Set(['prose', 'spec', 'rfc', 'skill', 'raw']);

  it('selects exactly the non-embedded rows with a Markdown template', () => {
    const want = ROUTES.filter((r) => r.source !== null && !r.embed && own.has(r.template)).map((r) => r.url);
    expect(markdownPages().map((r) => r.url)).toEqual(want);
  });

  it('builds the three pages the phase done-check names', () => {
    const urls = markdownPages().map((r) => r.url);
    for (const u of ['/spec/1.1.0/', '/start/overview/', '/rfcs/0002/']) expect(urls).toContain(u);
  });

  it('rejects a Markdown row whose template neither renders nor wraps it', () => {
    const bad: Route = { source: 'docs/A.md', url: '/a/', section: 'start', order: 0, template: 'workflow', title: 'A' };
    expect(() => markdownPages([bad])).toThrow(/neither renders nor wraps Markdown/);
  });
});
