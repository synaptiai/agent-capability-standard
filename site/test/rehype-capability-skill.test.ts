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
