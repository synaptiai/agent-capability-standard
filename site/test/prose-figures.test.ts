// The prose, RFC and skill page figures (visual spec 3.10): box diagram
// panels, pattern chains, table marks, F-O1, the RFC lifecycle and heading
// glyphs. Expected values come from hand-written fixtures below (counted by
// hand), from an independent parse of the YAML mapping file, and from the
// GOVERNANCE.md sentence, never from the plugin's own output.
import { describe, expect, it } from 'vitest';
import { parse } from 'yaml';
import { loadOasfMapping } from '../src/data/oasf';
import { foldFirstBox } from '../src/lib/prose-figures';
import { foldFirstTable, foldFirstTaskList } from '../src/lib/inject';
import { isNumberedRfc, lifecycleSentence, rfcLifecycle, splitH1 } from '../src/lib/prose-page';
import { readRepoFile } from '../src/lib/repo';
import {
  capabilityChain,
  domainValues,
  isBoxDiagram,
  numberColumn,
  patternChain,
  riskColumn,
  yesNoColumn,
} from '../src/plugins/rehype-prose-figures';
import { oasfMapTwin } from '../src/twins/oasf';
import { renderRepoFile } from './pipeline';

// A pattern fence with a six-line flow, in the form WORKFLOW_PATTERNS.md uses.
const ANALYZE = `analyze:
  description: Examine subject thoroughly and report findings
  capabilities:
    - retrieve       # Get the data
    - detect         # Find patterns
    - explain        # Summarize findings

  flow:
    1. retrieve(target) → data
    2. detect(data, patterns) → occurrences
    3. explain(occurrences) → report
`;

describe('box diagrams', () => {
  it('frames a fence with two or more box or tree lines, and only those', () => {
    expect(isBoxDiagram('┌──┐\n│ a │\n└──┘')).toBe(true);
    expect(isBoxDiagram('root/\n├── a\n└── b')).toBe(true);
    // One box line is a stray character, not a drawing.
    expect(isBoxDiagram('a → b\n─ one line')).toBe(false);
    expect(isBoxDiagram('plain text\nmore text')).toBe(false);
  });

  it('folds the first framed drawing into a details element, and throws on html without one', () => {
    const html = '<p>a</p><figure class="fig fig-ascii" aria-label="Diagram: x"><pre>┌┐</pre></figure><p>b</p>';
    expect(foldFirstBox(html, 'Text version', 'fixture')).toBe(
      '<p>a</p><details class="fig-details"><summary>Text version</summary><figure class="fig fig-ascii" aria-label="Diagram: x"><pre>┌┐</pre></figure></details><p>b</p>',
    );
    expect(() => foldFirstBox('<p>none</p>', 'x', 'README.md')).toThrow('README.md: no box diagram to fold');
  });
});

describe('pattern chains', () => {
  it('orders the tiles by the flow lines and names each output', () => {
    expect(patternChain(ANALYZE)).toEqual({
      name: 'analyze',
      ids: ['retrieve', 'detect', 'explain'],
      outputs: ['data', 'occurrences', 'report'],
      // From the fixture's flow lines: target and patterns come from outside;
      // data and occurrences are outputs of earlier lines.
      inputs: [['target'], ['patterns'], []],
      fromFlow: true,
    });
  });

  it('keeps the list order when there is no flow, and reads an inline list', () => {
    expect(patternChain('p:\n  capabilities: [plan, execute, verify]\n')).toEqual({
      name: 'p',
      ids: ['plan', 'execute', 'verify'],
      outputs: [null, null, null],
      inputs: [[], [], []],
      fromFlow: false,
    });
    expect(patternChain('p:\n  composes: [a, b]\n')).toBeNull();
  });

  it('draws a chain above a pattern fence and none above one a mermaid figure follows', async () => {
    const fence = '```yaml\n' + ANALYZE + '```\n';
    const mmd = '```mermaid\nflowchart LR\n  accDescr: Retrieve then detect.\n  a[retrieve] --> b[detect]\n```\n';
    const text = `# Title\n\n## One\n\n${fence}\n## Two\n\n${fence}\n${mmd}`;
    const { code } = await renderRepoFile('docs/WORKFLOW_PATTERNS.md', text);
    expect([...code.matchAll(/data-fig-kind="pattern-chain"/g)]).toHaveLength(1);
    // The chain comes before the fence it draws, with three tiles, and figures are numbered in page order.
    expect(code).toMatch(/data-fig-kind="pattern-chain"[\s\S]*?<\/figure><pre[^>]*data-language="yaml"/);
    const chain = /<figure[^>]*data-fig-kind="pattern-chain"[\s\S]*?<\/figure>/.exec(code)![0];
    expect([...chain.matchAll(/class="mini-tile mini-tile--32/g)]).toHaveLength(3);
    // The inputs from outside the chain, under their steps, in flow order.
    expect([...chain.matchAll(/<span class="prose-chain__in">.*?in: <\/span>([^<]*)<\/span>/g)].map((m) => m[1])).toEqual(['target', 'patterns']);
    expect([...code.matchAll(/>Fig (\d+)</g)].map((m) => m[1])).toEqual(['1', '2']);
  });
});

describe('table marks', () => {
  it('reads a number column of fractions or counts, and not an id column', () => {
    expect(numberColumn('Trust Weight', ['0.95', '0.55', '0.80'])).toEqual({ values: [0.95, 0.55, 0.8], fraction: true });
    expect(numberColumn('Count', ['4', '6', '**2**'])).toEqual({ values: [4, 6, 2], fraction: false });
    expect(numberColumn('ID', ['2', '3', '7'])).toBeNull();
    expect(numberColumn('Count', ['4', '4', '4'])).toBeNull();
    // 0 and 1 alone are counts, not fractions.
    expect(numberColumn('Parallel', ['0', '1', '0'])).toEqual({ values: [0, 1, 0], fraction: false });
  });

  it('reads yes/no, risk and domain cells', () => {
    expect(yesNoColumn(['✓', '—', 'Partial', 'Yes (opt-in)'])).toEqual(['yes', 'no', 'partial', 'yes']);
    expect(yesNoColumn(['✓', '✓'])).toBeNull();
    expect(yesNoColumn(['Yes', 'maybe'])).toBeNull();
    expect(riskColumn('Default Risk', ['low', 'High', 'varies'])).toEqual(['low', 'high', null]);
    expect(riskColumn('Rationale', ['low', 'high'])).toBeNull();
    expect(domainValues('`domain: text.entity`, `domain: text.pattern` -- Find')).toBe(2);
    expect(capabilityChain('retrieve → detect → classify')).toEqual(['retrieve', 'detect', 'classify']);
    expect(capabilityChain('retrieve → frobnicate')).toBeNull();
  });

  it('marks a hand-written table: bars, checks, pips and tiles, keeping each cell\'s words', async () => {
    const text = [
      '# T',
      '',
      '| Capability | Count | Checked | Risk |',
      '|---|---|---|---|',
      '| `mutate` | 3 | ✓ | high |',
      '| `verify` | 5 | — | low |',
      '| `plan` | 1 | ✓ | medium |',
      '| **Total** | 9 | 2 | — |',
      '',
    ].join('\n');
    const { code } = await renderRepoFile('docs/FAQ.md', text);
    // Three rows have bars; the Total row keeps its text and is off the scale.
    expect([...code.matchAll(/class="pixel-bar"/g)]).toHaveLength(3);
    expect(code).toMatch(/style="width: 60\.000%"/); // 3 of 5
    expect([...code.matchAll(/prose-yn--yes/g)]).toHaveLength(2);
    expect([...code.matchAll(/prose-yn--no/g)]).toHaveLength(1);
    expect([...code.matchAll(/data-risk="(low|medium|high)"/g)].map((m) => m[1])).toEqual(['high', 'low', 'medium']);
    expect([...code.matchAll(/class="mini-tile mini-tile--24/g)]).toHaveLength(3);
    expect(code).toContain('</span> high</td>');
    // Three rows carry marks; the Total row carries none.
    expect(code).toContain('data-enriched="3"');
    // Three marked rows make it an information figure (visual spec 4.2).
    expect(code).toContain('data-info-figure="enriched-table"');
  });

  it('gives a step table a tile for an id written with its parameters, and none for a word that is not an id', async () => {
    // As templates/composition_patterns.md writes its step tables.
    const text = ['# T', '', '| Step | Capability | Purpose |', '|---|---|---|', '| 1 | `observe` | a |', '| 2 | `attribute` (domain: dependencies) | b |', '| 3 | `invoke` (workflow_id: world_model_build) | c |', ''].join('\n');
    const { code } = await renderRepoFile('docs/FAQ.md', text);
    const tiles = [...code.matchAll(/class="mini-tile mini-tile--24[^"]*"[^>]*data-capability="([a-z_]+)"/g)].map((m) => m[1]);
    expect(tiles).toEqual(['observe', 'attribute', 'invoke']);
    expect(code).toContain('data-info-figure="enriched-table"');
    const plain = await renderRepoFile('docs/FAQ.md', ['# T', '', '| Capability | x |', '|---|---|', '| `observe` | a |', '| reflect (domain: self) | b |', ''].join('\n'));
    expect(plain.code).not.toContain('mini-tile');
  });

  it('leaves a table with fewer than three marked rows out of the figure count', async () => {
    const text = ['# T', '', '| Capability | Count |', '|---|---|', '| `plan` | 1 |', '| `verify` | 2 |', ''].join('\n');
    const { code } = await renderRepoFile('docs/FAQ.md', text);
    expect(code).toContain('data-enriched="2"');
    expect(code).not.toContain('data-info-figure');
  });
});

describe('F-O1, OASF categories mapped to capabilities', () => {
  const doc = parse(readRepoFile('schemas/interop/oasf_mapping.yaml')) as { categories: object; ga_extensions: object };

  it('has one row per OASF category and per GA extension of the mapping file', () => {
    const m = loadOasfMapping();
    expect(m.categories).toBe(Object.keys(doc.categories).length);
    expect(m.rows.map((r) => r.code)).toEqual([...Object.keys(doc.categories), ...Object.keys(doc.ga_extensions)]);
  });

  it('is drawn once on the proposal, under its section 4.1, with a tile per mapped capability', async () => {
    const { code } = await renderRepoFile('docs/proposals/OASF_SAFETY_EXTENSIONS.md');
    const figs = [...code.matchAll(/<figure[^>]*data-fig-kind="oasf-map"[\s\S]*?<\/figure>/g)];
    expect(figs).toHaveLength(1);
    expect(code).toMatch(/<h3[^>]*>4\.1 [\s\S]*?<\/h3>\s*<figure[^>]*data-fig-kind="oasf-map"/);
    const tiles = [...figs[0]![0].matchAll(/class="mini-tile mini-tile--24/g)].length;
    const expected = Object.values({ ...doc.categories, ...doc.ga_extensions }).reduce((n: number, v) => n + (v as { capabilities: string[] }).capabilities.length, 0);
    expect(tiles).toBe(expected);
  });

  it('has a table twin with the same rows', () => {
    const twin = oasfMapTwin();
    const rows = twin.split('\n').filter((l) => l.startsWith('| ') && !l.startsWith('| OASF category') && !l.startsWith('| ---'));
    expect(rows).toHaveLength(Object.keys(doc.categories).length + Object.keys(doc.ga_extensions).length);
  });
});

describe('RFC pages', () => {
  // GOVERNANCE.md: "An RFC's status is Draft, Accepted (...), Rejected or Superseded."
  const allowed = ['Draft', 'Accepted', 'Rejected', 'Superseded'];

  it('starts at Draft, ends at one of the others, and fills the RFC\'s own state', () => {
    const l = rfcLifecycle('Accepted', allowed, 'test');
    expect(l.start.status).toBe('Draft');
    expect(l.outcomes.map((o) => o.status)).toEqual(['Accepted', 'Rejected', 'Superseded']);
    expect([l.start, ...l.outcomes].filter((s) => s.current).map((s) => s.status)).toEqual(['Accepted']);
    // A proposal's "Draft Proposal" is a draft.
    expect(rfcLifecycle('Draft Proposal', allowed, 'test').current).toBe('Draft');
    expect(() => rfcLifecycle('Withdrawn', allowed, 'test')).toThrow(/Withdrawn/);
    expect(lifecycleSentence(l, '2026-01-24')).toBe('An RFC starts as Draft and ends as Accepted, Rejected or Superseded; this one is Accepted, dated 2026-01-24.');
  });

  it('puts a check before "Goals" and a cross before "Non-goals"', async () => {
    const { code } = await renderRepoFile('spec/RFC-0002-agent-reliability-profile.md');
    expect(code).toMatch(/<h2 id="goals">\s*<svg [^>]*data-glyph="check"/);
    expect(code).toMatch(/<h2 id="non-goals">\s*<svg [^>]*data-glyph="close"/);
  });

  it('draws the lifecycle only for numbered RFCs, not the OASF proposal', () => {
    expect(isNumberedRfc('spec/RFC-0002-agent-reliability-profile.md')).toBe(true);
    expect(isNumberedRfc('docs/proposals/OASF_SAFETY_EXTENSIONS.md')).toBe(false);
  });

  it('takes the first h1 out of rendered html for the hero', () => {
    expect(splitH1('<p>a</p><h1 id="t">Title <a>#</a></h1><p>b</p>')).toEqual({ h1: '<h1 id="t">Title <a>#</a></h1>', rest: '<p>a</p><p>b</p>' });
    expect(splitH1('<p>x</p>')).toEqual({ h1: null, rest: '<p>x</p>' });
  });
});

describe('folding a source block under its figure', () => {
  it('folds a whole task list, nested list included, and what follows stays outside', () => {
    const html = '<p>a</p><ul class="contains-task-list"><li><input type="checkbox" disabled> one<ul><li>sub</li></ul></li><li><input type="checkbox" disabled> two</li></ul><p>b</p>';
    expect(foldFirstTaskList(html, 'Text version', 'fixture')).toBe(
      '<p>a</p><details class="fig-details"><summary>Text version</summary><ul class="contains-task-list"><li><input type="checkbox" disabled> one<ul><li>sub</li></ul></li><li><input type="checkbox" disabled> two</li></ul></details><p>b</p>',
    );
  });

  it('folds the first table in its wrapper', () => {
    const html = '<div class="table-wrap" tabindex="0"><table><tr><td>1</td></tr></table></div><p>b</p>';
    expect(foldFirstTable(html, 'S & T', 'fixture')).toBe(
      '<details class="fig-details"><summary>S &amp; T</summary><div class="table-wrap" tabindex="0"><table><tr><td>1</td></tr></table></div></details><p>b</p>',
    );
  });

  it('throws when there is no block to fold', () => {
    expect(() => foldFirstTaskList('<ul><li>plain</li></ul>', 's', 'skills/x/SKILL.md')).toThrow('skills/x/SKILL.md: no task list to fold');
    expect(() => foldFirstTable('<p>none</p>', 's', 'edge types')).toThrow('edge types: no table to fold');
  });
});
