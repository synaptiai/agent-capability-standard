// Tests on the stylesheets against the design rules. Expected values come
// from the design notes (design-system section 3, the typography table, and
// the WorkflowDiagram recipe) and from the plan's Phase 5 accessibility rules.
import { readdirSync, readFileSync } from 'node:fs';
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

describe('definitions', () => {
  // Tokens are used through var(); the contrast check also names palette
  // tokens directly. Shiki's css-variables theme reads the --astro-code-*
  // names, and --layer-<ID> is read through --layer on each .has-layer element.
  const tokensCss = STYLES.find((s) => s.file === 'tokens.css')!.css;
  const sources = [
    ...STYLES.map((s) => s.css),
    readFileSync('scripts/check-contrast.mjs', 'utf8'),
    ...listFiles('src').filter((f) => /\.(astro|ts)$/.test(f)).map((f) => readFileSync(f, 'utf8')),
  ].join('\n');

  it('uses every custom property tokens.css defines', () => {
    const defined = [...new Set([...tokensCss.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((m) => m[1]!))];
    const unused = defined.filter(
      (t) =>
        !t.startsWith('--astro-code-') &&
        !t.startsWith('--layer-') &&
        !sources.includes(`var(${t})`) &&
        !sources.includes(`var(${t},`) &&
        !sources.includes(`'${t}'`),
    );
    expect(unused).toEqual([]);
  });

  it('uses every class components.css defines on a single class selector', () => {
    const css = STYLES.find((s) => s.file === 'components.css')!.css;
    const markup = listFiles('src').filter((f) => /\.(astro|ts)$/.test(f)).map((f) => readFileSync(f, 'utf8')).join('\n');
    const lone = rules()
      .filter((r) => r.file === 'components.css')
      .flatMap((r) => r.selectors)
      .filter((s) => /^\.[a-z][\w-]*$/.test(s))
      .map((s) => s.slice(1));
    // A modifier such as callout--tip is used when the markup builds it from a value: `callout--${type}`.
    const used = (c: string) => markup.includes(c) || (c.includes('--') && markup.includes(`${c.split('--')[0]}--\${`));
    expect(css.length).toBeGreaterThan(0);
    expect([...new Set(lone)].filter((c) => !used(c))).toEqual([]);
  });
});

function listFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? listFiles(`${dir}/${e.name}`) : [`${dir}/${e.name}`],
  );
}
