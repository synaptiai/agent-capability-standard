// Tests on the stylesheets against the design rules. Expected values come
// from the design notes (design-system section 3, the typography table, and
// the WorkflowDiagram recipe) and from the plan's Phase 5 accessibility rules.
import { readdirSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// figures-mermaid.css holds the Mermaid figure styles in a file of their own;
// it is listed so every rule here (display font, opacity, tokens) covers it too.
const STYLES = ['tokens.css', 'base.css', 'components.css', 'motion.css', 'figures-mermaid.css'].map((f) => ({
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
    // beside each node is in the display font (Jersey 10 since the user's
    // decision of 2026-11-11, replacing Pixelify Sans).
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

  it('sets the display font at weight 400 with no synthesized bold (Jersey 10 has one weight)', () => {
    const display = rules().filter((r) => /font-family:\s*var\(--font-display\)/.test(r.body));
    expect(display.length).toBeGreaterThan(0);
    for (const r of display) {
      expect(r.body, r.selectors.join(',')).toMatch(/font-weight:\s*400\b/);
      expect(r.body, r.selectors.join(',')).toMatch(/font-synthesis:\s*none/);
    }
  });

  it('keeps a heading hierarchy by size alone: h1 > h2 > h3 > h4', () => {
    // With one display weight, size is the only signal left between levels.
    const size = (sel: string) => {
      const r = rules().find((x) => x.file === 'base.css' && x.selectors.length === 1 && x.selectors[0] === sel && /font-size/.test(x.body));
      return Number(/font-size:\s*(\d+)px/.exec(r?.body ?? '')?.[1]);
    };
    const [h1, h2, h3] = [size('h1'), size('h2'), size('h3')];
    const h4 = Number(/font-size:\s*(\d+)px/.exec(rules().find((x) => x.file === 'base.css' && x.selectors.includes('h4') && /font-size/.test(x.body))!.body)?.[1]);
    expect(h1).toBeGreaterThan(h2);
    expect(h2).toBeGreaterThan(h3);
    expect(h3).toBeGreaterThan(h4);
  });
});

describe('tables', () => {
  it('sets every table header in capitals and never turns that off (plan, Phase 5 accessibility rules)', () => {
    const all = rules();
    const upper = all.filter((r) => r.selectors.includes('thead th') && /text-transform:\s*uppercase/.test(r.body));
    expect(upper.length).toBeGreaterThan(0);
    const off = all
      .filter((r) => /text-transform:\s*none/.test(r.body))
      .flatMap((r) => r.selectors)
      .filter((s) => /\bth\b/.test(s) && !/\bcode$/.test(s));
    expect(off).toEqual([]);
  });

  it('never sets a table to display: block, which drops its table semantics in some screen readers', () => {
    const block = rules()
      .filter((r) => /display:\s*block/.test(r.body))
      .flatMap((r) => r.selectors)
      .filter((s) => /(^|[\s>])table\b(?![\w-])/.test(s.replace(/:not\([^)]*\)/g, '')));
    expect(block).toEqual([]);
  });
});

describe('menu without JavaScript', () => {
  it('hides the menu button and shows the section links until the head script has set .js', () => {
    const all = rules();
    const has = (sel: string, decl: RegExp) => all.some((r) => r.selectors.includes(sel) && decl.test(r.body));
    expect(has(':root:not(.js) .menu-button', /display:\s*none/)).toBe(true);
    expect(has(':root:not(.js) .site-nav', /display:\s*block/)).toBe(true);
  });

  it('hides both copy buttons, which need JavaScript, until the head script has set .js', () => {
    const all = rules();
    const has = (sel: string) => all.some((r) => r.selectors.includes(sel) && /display:\s*none/.test(r.body));
    expect(has(':root:not(.js) .copy-block__button')).toBe(true);
    expect(has(':root:not(.js) [data-copy-markdown]')).toBe(true);
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
        // The plan's Phase 5 recipe names shadows of 3, 5 and 7px; the 7px one is defined before any component uses it.
        t !== '--shadow-3' &&
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

describe('dimmed text', () => {
  it('never fades with opacity between 0 and 1, which check-contrast cannot see', () => {
    // Plan Phase 5: text meets 4.5:1. Opacity 0 (hidden) and 1 are fine; a
    // fraction blends text into its background by an amount no token states.
    const faded = rules()
      .filter((r) => /(^|;|\s)opacity:\s*(0?\.\d*[1-9]\d*|0\.\d+)\s*(;|$)/.test(r.body))
      .map((r) => `${r.file}: ${r.selectors.join(', ')}`);
    expect(faded).toEqual([]);
  });

  it('dims story steps other than the current one with --ink-3, a checked text colour', () => {
    const all = rules();
    expect(all.some((r) => r.selectors.includes('.story[data-live] .story__step') && /color:\s*var\(--ink-3\)/.test(r.body))).toBe(true);
  });
});

describe('contents list', () => {
  it('shows a chevron that turns when the list is open, since the browser marker is hidden', () => {
    const all = rules();
    expect(all.some((r) => r.selectors.includes('.toc__title::-webkit-details-marker') && /display:\s*none/.test(r.body))).toBe(true);
    expect(all.some((r) => r.selectors.includes('.toc[open] .toc__chevron') && /transform:\s*rotate\(90deg\)/.test(r.body))).toBe(true);
  });
});


describe('description lists', () => {
  it('styles the terms of every description list a page renders', () => {
    // Expected set: every class given to a <dl> in the page sources, read by
    // walking src/ here. A <dl> with no dt rule renders terms and values in the
    // same plain text, which was found on the RFC and compliance pages.
    const walk = (dir: string): string[] =>
      readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
        e.isDirectory() ? walk(`${dir}/${e.name}`) : /\.(astro|ts)$/.test(e.name) ? [`${dir}/${e.name}`] : [],
      );
    const classes = new Set<string>();
    for (const f of walk('src')) {
      for (const m of readFileSync(f, 'utf8').matchAll(/<dl class="([^"]+)"/g)) classes.add(m[1]!.split(/\s+/)[0]!);
    }
    expect(classes.size).toBeGreaterThan(0);
    // Whole selector texts, unsplit, so that `:is(.a, .b) dt` stays one entry.
    const selectorTexts = STYLES.flatMap(({ css }) => [...css.matchAll(/([^{}]+)\{[^{}]*\}/g)].map((m) => m[1]!));
    const missing = [...classes].filter(
      (c) => !selectorTexts.some((t) => new RegExp(`\\.${c}(?![\\w-])`).test(t) && /\bdt\s*$/.test(t.trim())),
    );
    expect(missing).toEqual([]);
  });
});

describe('scrollable code blocks', () => {
  it('makes every hand-written <pre> keyboard-focusable', () => {
    // Markdown code blocks get tabindex="0" from Shiki; components write their
    // own <pre>, which scrolls sideways when a line is long and must then be
    // reachable by keyboard (axe rule scrollable-region-focusable).
    const walk = (dir: string): string[] =>
      readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
        e.isDirectory() ? walk(`${dir}/${e.name}`) : e.name.endsWith('.astro') ? [`${dir}/${e.name}`] : [],
      );
    const pres = walk('src').flatMap((f) => [...readFileSync(f, 'utf8').matchAll(/<pre\b[^>]*>/g)].map((m) => `${f}: ${m[0]}`));
    expect(pres.length).toBeGreaterThan(0);
    expect(pres.filter((p) => !/tabindex="0"/.test(p))).toEqual([]);
  });
});
