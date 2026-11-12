// The capability skill step (rehype-capability-skill), run through the build
// pipeline on a hand-written SKILL.md. The fixture is rendered at the path of
// a capability skill (mutate) and at the path of a composed skill
// (debug-workflow), which the step must leave alone. Expected values are
// read off the fixture below.
import { describe, expect, it } from 'vitest';
import { loadOntology } from '../src/data/ontology';
import { renderRepoFile } from './pipeline';

const FIXTURE = [
  '---',
  'name: fixture',
  '---',
  '',
  '## Inputs',
  '',
  '| Parameter | Required | Type |',
  '|---|---|---|',
  '| `target` | Yes | string |',
  '| `content` | Yes | string |',
  '| `mode` | No | string |',
  '',
  '## Procedure',
  '',
  '1. **First**: a',
  '2. **Second**: b',
  '',
  '## Output Contract',
  '',
  'Return:',
  '',
  '```yaml',
  'success: boolean',
  '```',
  '',
  '### Field Definitions',
  '',
  '| Field | Type |',
  '|---|---|',
  '| `success` | boolean |',
  '| `new_state` | object |',
  '| `rollback_command` | string |',
  '| `previous_state.hash` | string |',
  '',
  '## Examples',
  '',
  'Lead-in.',
  '',
  '### Example 1: Happy Path',
  '',
  'one',
  '',
  '### Example 2: Mutation Failure',
  '',
  'two',
  '',
  '## Safety Constraints',
  '',
  '- `mutation`: true',
  '',
  '## Composition Patterns',
  '',
  'after',
  '',
].join('\n');

const render = async (path: string) => (await renderRepoFile(path, FIXTURE)).code;

describe('rehype-capability-skill', () => {
  it('numbers the procedure: its ordered list gets the skill-steps class', async () => {
    const html = await render('skills/mutate/SKILL.md');
    expect(html).toMatch(/<ol class="skill-steps">/);
  });

  it('folds the first fence of Output Contract into a details, and leaves the Field Definitions table open', async () => {
    const html = await render('skills/mutate/SKILL.md');
    const section = html.slice(html.indexOf('id="output-contract"'), html.indexOf('id="examples"'));
    expect(section).toMatch(/<details class="fig-details skill-fence"><summary>The output as the skill writes it, in YAML<\/summary><pre[^>]*data-language="yaml"/);
    expect(section).toContain('<p>Return:</p>');
    expect(section).toMatch(/<table/);
    expect(section.indexOf('</details>')).toBeLessThan(section.indexOf('<table'));
  });

  it('marks the Inputs table Required column with check and cross glyphs', async () => {
    const html = await render('skills/mutate/SKILL.md');
    const section = html.slice(html.indexOf('id="inputs"'), html.indexOf('id="procedure"'));
    const marks = [...section.matchAll(/class="pg skill-req skill-req--(yes|no)"/g)].map((m) => m[1]);
    expect(marks).toEqual(['yes', 'yes', 'no']);
    // The glyphs repeat the Yes and No, so the table is not an information figure (issue #125 review).
    expect(section).toMatch(/<table[^>]*data-enriched="3"/);
    expect(section).not.toContain('data-info-figure');
  });

  it("marks each top-level Field Definitions row with mutate's output contract, and leaves a nested path unmarked", async () => {
    // mutate's output contract (ontology): success, rollback_command and new_state are fields of it, so
    // each gets a pin; previous_state.hash is a nested path and gets an empty cell.
    const html = await render('skills/mutate/SKILL.md');
    const section = html.slice(html.indexOf('id="field-definitions"'), html.indexOf('id="examples"'));
    expect(section).toContain('<th>In the output contract</th>');
    expect(section).toMatch(/<table[^>]*data-info-figure="enriched-table"/);
    const cellsIn = [...section.matchAll(/<td class="skill-contract-cell">([\s\S]*?)<\/td>/g)].map((m) => m[1]!);
    expect(cellsIn).toHaveLength(4);
    expect(cellsIn[3]).toBe('');
    const out = loadOntology().byId.get('mutate')!.output_schema as { properties: Record<string, unknown>; required?: string[] };
    ['success', 'new_state', 'rollback_command'].forEach((name, i) => {
      const want = !(name in out.properties) ? "no, the skill's own" : (out.required ?? []).includes(name) ? 'required' : 'optional';
      expect(cellsIn[i]).toContain(want);
    });
  });

  it("adds the output contract's required and optional marks to Field Definitions when the skill's fields all match it", async () => {
    // invoke's skill names every field of its output contract, so F-C6 is a sentence and the table carries the contract.
    const html = (await renderRepoFile('skills/invoke/SKILL.md')).code;
    const section = html.slice(html.indexOf('id="field-definitions"'), html.indexOf('id="examples"'));
    expect(section).toContain('<th>In the output contract</th>');
    expect(section).toMatch(/<table[^>]*data-info-figure="enriched-table"/);
    const out = loadOntology().byId.get('invoke')!.output_schema as { properties: Record<string, unknown>; required?: string[] };
    const rows = [...section.matchAll(/<tr>\s*<td><code>([a-z_]+)<\/code><\/td>[\s\S]*?<td class="skill-contract-cell">([\s\S]*?)<\/td><\/tr>/g)].map((m) => [m[1], /required/.test(m[2]!) ? 'required' : /optional/.test(m[2]!) ? 'optional' : '']);
    expect(rows.length).toBeGreaterThanOrEqual(3);
    for (const [name, mark] of rows) expect([name, mark]).toEqual([name, name! in out.properties ? ((out.required ?? []).includes(name!) ? 'required' : 'optional') : '']);
  });

  it('makes each example a closed details whose summary keeps the H3 and its id, with no anchor link', async () => {
    const html = await render('skills/mutate/SKILL.md');
    const details = [...html.matchAll(/<details class="skill-example"( open)?>/g)];
    expect(details).toHaveLength(2);
    expect(details.every((d) => d[1] === undefined)).toBe(true);
    expect(html).toMatch(/<summary class="skill-example__summary">[^]*?<h3 id="example-1-happy-path">Example 1: Happy Path<\/h3><\/summary>/);
    const summaries = [...html.matchAll(/<summary class="skill-example__summary">([^]*?)<\/summary>/g)].map((m) => m[1]!);
    expect(summaries.some((s) => s.includes('heading-anchor'))).toBe(false);
    // The lead-in paragraph stays outside the examples.
    expect(html).toMatch(/<p>Lead-in.<\/p>\s*<details class="skill-example">/);
  });

  it('gives a "Failure" example the caution glyph and the others the code glyph', async () => {
    const html = await render('skills/mutate/SKILL.md');
    const summaries = [...html.matchAll(/<summary class="skill-example__summary">([^]*?)<\/summary>/g)].map((m) => m[1]!);
    expect(summaries[0]).toMatch(/data-glyph="code"/);
    expect(summaries[1]).toMatch(/data-glyph="caution"/);
  });

  it('puts Safety Constraints in a panel and leaves the next section alone', async () => {
    const html = await render('skills/mutate/SKILL.md');
    expect(html).toMatch(/<div class="skill-safety">[^]*<div class="skill-safety__body"><ul>[^]*<code>mutation<\/code>/);
    expect(html).toMatch(/<h2 id="composition-patterns">[^]*<p>after<\/p>/);
  });

  it('leaves a composed skill untouched', async () => {
    const html = await render('skills/debug-workflow/SKILL.md');
    expect(html).not.toMatch(/skill-steps|skill-fence|skill-example|skill-safety/);
    expect(html).toMatch(/<h3 id="example-1-happy-path">/);
  });
});
