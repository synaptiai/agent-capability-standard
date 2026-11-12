// The capability skill step (rehype-capability-skill), run through the build
// pipeline on a hand-written SKILL.md. The fixture is rendered at the path of
// a capability skill (mutate) and at the path of a composed skill
// (debug-workflow), which the step must leave alone. Expected values are
// read off the fixture below.
import { describe, expect, it } from 'vitest';
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
    expect(section).toMatch(/<table[^>]*data-enriched="3"[^>]*data-info-figure="enriched-table"/);
  });

  it('adds an "In the contract" column to Field Definitions from the ontology', async () => {
    const html = await render('skills/mutate/SKILL.md');
    const section = html.slice(html.indexOf('id="field-definitions"'), html.indexOf('id="examples"'));
    expect(section).toContain('<th>In the contract</th>');
    // Expected from mutate's output_schema in schemas/capability_ontology.yaml:
    // success is a required boolean, new_state an optional any, and
    // rollback_command is not in the contract.
    const cells = [...section.matchAll(/<td class="skill-fd__contract" data-in-contract="(yes|no)">([^]*?)<\/td>/g)].map((m) => [
      m[1],
      m[2]!.replace(/<svg[^]*?<\/svg>/g, '').trim(),
    ]);
    expect(cells).toEqual([
      ['yes', 'Yes: <code>boolean</code>, required'],
      ['yes', 'Yes: <code>any</code>, optional'],
      ['no', "No, the skill's own"],
    ]);
    // Three rows carry a glyph, so it counts as an information figure (visual spec 4.2).
    expect(section).toMatch(/<table[^>]*data-enriched="3"[^>]*data-info-figure="enriched-table"/);
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
