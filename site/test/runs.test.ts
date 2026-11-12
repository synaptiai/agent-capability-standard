// The figure-gap measurement (visual spec 3.12, 4.2, 6.3). Expected values
// are worked out by hand: the geometry of test/fixtures/runs-page.html is in
// runs-page.json (scripts/check-runs.mjs checks the browser measures the
// same), and the runs below are computed from it by hand. The exempt-run
// rows and the enforced scope are typed from the spec's table in 3.12 and
// the scope list in 4.2.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { reportLines, summarise } from '../scripts/check-runs.mjs';
import {
  EXEMPT_RUNS,
  exemptRunsFor,
  isEnforced,
  longestRun,
  measureRuns,
  pageMatches,
  RUN_LIMIT_VH,
  RUN_VIEWPORT,
  type PageGeometry,
} from '../src/lib/runs';

const fixture = JSON.parse(readFileSync('test/fixtures/runs-page.json', 'utf8')) as { geometry: PageGeometry };

describe('measureRuns on the fixture page', () => {
  const runs = measureRuns(fixture.geometry);

  it('finds the runs before, between and after the two counted figures', () => {
    // Body 100..7900 (the closed details under #code adds its 50px summary); figures 1100..1400 and 6200..6300.
    expect(runs.map((r) => [r.top, r.bottom, r.height])).toEqual([
      [100, 1100, 1000],
      [1400, 6200, 4800],
      [6300, 7900, 1600],
    ]);
  });

  it('subtracts the exempt sections each run crosses', () => {
    // #notes 1400..4050 lies inside the second run: 4800 - 2650 = 2150.
    // The visible tall fence 6500..7500 lies inside the third: 1600 - 1000 = 600.
    expect(runs.map((r) => [r.exempt, r.net, r.labels])).toEqual([
      [0, 1000, []],
      [2650, 2150, ['#notes (a)']],
      [1000, 600, ['#code (b)']],
    ]);
    expect(longestRun(runs)?.net).toBe(2150);
  });

  it('merges overlapping figures, clips to the body and counts overlapping exempt sections once', () => {
    const page: PageGeometry = {
      body: { top: 0, bottom: 1000 },
      figures: [
        { top: -50, bottom: 100 },
        { top: 400, bottom: 600 },
        { top: 500, bottom: 700 },
      ],
      exempt: [
        { label: 'a', top: 150, bottom: 300 },
        { label: 'b', top: 250, bottom: 350 },
        { label: 'c', top: 950, bottom: 1200 },
      ],
    };
    // Runs: 100..400 (exempt 150..350 = 200) and 700..1000 (exempt 950..1000 = 50).
    expect(measureRuns(page).map((r) => [r.top, r.bottom, r.exempt, r.net])).toEqual([
      [100, 400, 200, 100],
      [700, 1000, 50, 250],
    ]);
  });

  it('treats a page with no figure as one run', () => {
    const r = measureRuns({ body: { top: 10, bottom: 20 }, figures: [], exempt: [] });
    expect(r.map((x) => x.height)).toEqual([10]);
  });
});

describe('exempt runs and scope', () => {
  it('matches pages by URL, by one-segment pattern and by template', () => {
    expect(pageMatches('/spec/1.1.0/', '/spec/1.1.0/', 'spec')).toBe(true);
    expect(pageMatches('/spec/1.1.0/', '/spec/1x1x0/', 'spec')).toBe(false);
    expect(pageMatches('/rfcs/*/', '/rfcs/0002/', 'rfc')).toBe(true);
    expect(pageMatches('/rfcs/*/', '/rfcs/proposals/oasf-safety-extensions/', 'rfc')).toBe(false);
    expect(pageMatches('template:domain', '/domains/vision/', 'domain')).toBe(true);
    expect(pageMatches('template:domain', '/domains/', 'domains-index')).toBe(false);
  });

  it('seeds every row of the spec 3.12 table', () => {
    const rows = (page: string) => EXEMPT_RUNS.filter((e) => e.page === page).map((e) => `${e.anchor}:${e.category}`);
    expect(rows('/spec/1.1.0/')).toEqual([
      '13-references:c',
      'appendix-a-layer-reference:c',
      'appendix-b-reserved-identifiers:c',
      'appendix-c-changes-from-100:c',
    ]);
    expect(rows('/start/overview/')).toEqual([
      'why-this-matters:a',
      'quick-start:b',
      'claude-agent-sdk-integration:b',
      'installation:b',
      'validation:b',
      'license:c',
      'citation:c',
      'contributing:c',
      // Not in the spec's table: added at integration, read from README.md
      // (five tables of document links).
      'documentation:a',
    ]);
    expect(rows('/guides/claude-agent-sdk/')).toEqual([
      'quick-start:b',
      'using-groundedclient:b',
      'using-wrap_options-low-level:b',
      'configuration-options:b',
      'using-with-capability-skills:b',
      // Not in the spec's table: added at integration, read from
      // docs/integrations/claude_agent_sdk.md (each section is code fences
      // with a one-line lead-in).
      'structured-output:b',
      'budget-enforcement:b',
      'evidence-anchors:b',
      'validation:b',
      'troubleshooting:b',
      'api-reference:b',
    ]);
    // Added at integration: rollback's Intent.
    expect(rows('template:capability')).toEqual(['examples:b']);
    expect(rows('/capabilities/rollback/')).toEqual(['intent:a']);
    expect(rows('template:domain')).toEqual(['customization-guide:b', 'integration-examples:b']);
    expect(EXEMPT_RUNS.find((e) => e.page === 'template:capability')?.extent).toBe('first-tall-fence');
    expect(exemptRunsFor('/rfcs/0001/', 'rfc').map((e) => e.anchor)).toEqual(['*']);
    expect(exemptRunsFor('/compliance/eu-ai-act/', 'prose').map((e) => e.anchor)).toEqual(['reading-order', 'document-register']);
  });

  it('enforces the generated templates and the four named pages, and only reports the rest', () => {
    for (const t of ['home', 'capability', 'layer', 'workflow', 'domain', 'edge-types', 'diagnostics']) expect(isEnforced('/x/', t), t).toBe(true);
    for (const u of ['/spec/1.1.0/', '/start/overview/', '/workflows/patterns/', '/guides/claude-agent-sdk/']) expect(isEnforced(u, 'prose'), u).toBe(true);
    for (const u of ['/background/grounded-agency/', '/background/whitepaper/', '/guides/modality-handling/', '/rfcs/proposals/oasf-safety-extensions/', '/spec/1.0.0/']) {
      expect(isEnforced(u, u === '/spec/1.0.0/' ? 'spec' : 'prose'), u).toBe(false);
    }
  });

  it('limits a run to two 900px viewports, measured 1440px wide', () => {
    expect(RUN_VIEWPORT).toEqual({ width: 1440, height: 900 });
    expect(RUN_LIMIT_VH * RUN_VIEWPORT.height).toBe(1800);
  });
});

describe('the report', () => {
  const run = (top: number, height: number, exempt = 0, labels: string[] = []) => ({ top, bottom: top + height, height, exempt, net: height - exempt, labels });

  it('fails an enforced page only on a net run over the limit, reports the rest, and flags a missing page anchor', () => {
    const missing = EXEMPT_RUNS.find((e) => e.page === '/start/overview/' && e.anchor === 'license')!;
    const pages = new Map([
      ['/capabilities/x/', { wide: { template: 'capability', width: 1440, runs: [run(0, 2000), run(2000, 500)], small: [{ top: 300, bottom: 340 }], missing: [] } }],
      ['/start/overview/', { wide: { template: 'prose', width: 1440, runs: [run(0, 3000, 1500, ['#quick-start (b)'])], missing: [missing] } }],
      ['/background/grounded-agency/', { wide: { template: 'prose', width: 1440, runs: [run(0, 5000)], missing: [] } }],
    ]);
    const s = summarise(pages);
    expect(s.results.map((r) => [r.url, r.over.length, r.failing.length])).toEqual([
      ['/capabilities/x/', 1, 1],
      ['/start/overview/', 1, 0],
      ['/background/grounded-agency/', 1, 0],
    ]);
    expect(s.missing).toEqual(['/start/overview/#license']);
    const lines = reportLines(s);
    expect(lines[0]).toMatch(/^report \/background\/grounded-agency\/ \[prose\] run of 5000px/);
    expect(lines.find((l) => l.includes('/capabilities/x/'))).toMatch(/^FAIL .*; 1 figure\(s\) inside drawn under 96x64px, not counted;/);
    expect(lines.find((l) => l.includes('/start/overview/'))).toMatch(/^exempt .*1500px exempt \(#quick-start \(b\)\), net 1500px/);
    expect(lines.at(-1)).toBe('STALE  exempt run /start/overview/#license: no such heading');
  });

  it('calls a template entry stale when no page of its template has the heading', () => {
    const pages = new Map([['/domains/a/', { wide: { template: 'domain', width: 1440, runs: [], missing: EXEMPT_RUNS.filter((e) => e.page === 'template:domain') } }]]);
    expect(summarise(pages).missing).toEqual(['template:domain#customization-guide', 'template:domain#integration-examples']);
  });
});
