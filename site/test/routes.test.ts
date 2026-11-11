import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { checkRoutes, ROUTES, type Route } from '../src/lib/routes';

// The public set is computed here from `git ls-files` and the plan's
// exclusion list (plan "Recommended defaults" item 12), written out
// independently of src/lib/routes.ts. `.github/` is added because its only
// .md file is the pull request template.
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
];
const publicMd = tracked.filter((p) => p.endsWith('.md') && !PLAN_EXCLUDED.some((re) => re.test(p)));

const bySource = new Map(ROUTES.filter((r) => r.source !== null).map((r) => [r.source!, r]));
const byUrl = new Map(ROUTES.map((r) => [r.url, r]));

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

  it('reports a URL without the trailing slash', () => {
    const b: Route = { ...ok, source: 'docs/B.md', url: '/b' };
    expect(checkRoutes([ok, b], files)).toEqual(['/b: URL must look like /a/b/']);
  });
});
