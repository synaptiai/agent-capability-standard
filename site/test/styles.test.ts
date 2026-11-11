// Tests on the stylesheets against the design rules. Expected values come
// from the design notes (design-system section 3, the typography table, and
// the WorkflowDiagram recipe) and from the plan's Phase 5 accessibility rules.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const STYLES = ['tokens.css', 'base.css', 'components.css', 'motion.css'].map((f) => ({
  file: f,
  css: readFileSync(`src/styles/${f}`, 'utf8').replace(/\/\*[\s\S]*?\*\//g, ''),
}));

/** Every innermost rule in the stylesheets, with its selectors split. */
function rules(): { file: string; selectors: string[]; body: string }[] {
  const out = [];
  for (const { file, css } of STYLES) {
    for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      out.push({ file, selectors: m[1]!.split(',').map((s) => s.trim().replace(/\s+/g, ' ')), body: m[2]! });
    }
  }
  return out;
}

describe('typography', () => {
  it('uses the pixel display font only where the design lists it', () => {
    // Typography table: h1-h3, hero headline, wordmark, primary buttons,
    // prev/next titles, tile symbols. WorkflowDiagram recipe: the step number
    // beside each node is Pixelify 16px.
    const allowed = new Set([
      'h1',
      'h2',
      'h3',
      '.site-header__home', // the wordmark
      '.btn', // primary buttons; .btn--quiet switches back to the body font
      '.prev-next__title',
      '.capability-tile__symbol',
      '.wf-step__number',
    ]);
    const display = rules()
      .filter((r) => /font-family:\s*var\(--font-display\)/.test(r.body))
      .flatMap((r) => r.selectors);
    expect(display.filter((s) => !allowed.has(s))).toEqual([]);
  });
});

describe('accessible names', () => {
  it('never hides with display: none the only text of a control that has no aria-label', () => {
    // The GitHub link and the menu button have no aria-label: their words may
    // be hidden visually below a width, but must stay in the accessibility tree.
    const hidden = rules()
      .filter((r) => /display:\s*none/.test(r.body))
      .flatMap((r) => r.selectors)
      .filter((s) => /site-header__github|menu-button__text|wordmark\b(?!__)|version-chip__word/.test(s));
    expect(hidden).toEqual([]);
  });
});
