// The contrast check on the real tokens and on fixtures. Expected ratios are
// the ones the design notes computed by hand for the frozen palette
// (design-system section 4), rounded to two places, plus the WCAG end points.
import { readdirSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { checkContrast, contrast, FIGURE_COLOUR_EXCEPTIONS, pairRatio, pairs, parseTokens, resolveColor } from '../scripts/check-contrast.mjs';

const css = readFileSync('src/styles/tokens.css', 'utf8');
const { light, dark } = parseTokens(css);
const ratio = (fg: string, bg: string, tokens: Record<string, string>) =>
  Number(pairRatio({ kind: 'text', label: '', fg, bg }, tokens).toFixed(2));
const tint = (c: string, amount = 'var(--tint-amount)') => `color-mix(in srgb, ${c} ${amount}, var(--bg))`;

describe('contrast arithmetic', () => {
  it('gives 21:1 for black on white and 1:1 for a colour on itself', () => {
    expect(contrast([0, 0, 0], [255, 255, 255])).toBeCloseTo(21, 5);
    expect(contrast([56, 189, 248], [56, 189, 248])).toBe(1);
  });

  it('mixes in sRGB by channel and rounds to 8 bits, which reproduces the ratios in the design notes', () => {
    // 50% of #000000 into #ffffff is 127.5 per channel, rounded to 128.
    expect(resolveColor('color-mix(in srgb, #000000 50%, #ffffff)', {})).toEqual([128, 128, 128]);
  });
});

describe('the ratios the design notes list', () => {
  it('matches the light values', () => {
    expect(ratio('var(--ink)', 'var(--bg)', light)).toBe(18.22);
    expect(ratio('var(--link)', 'var(--bg)', light)).toBe(5.93);
    expect(ratio('var(--accent)', 'var(--bg)', light)).toBe(2.14);
    expect(ratio('var(--control)', 'var(--bg)', light)).toBe(4.76);
    expect(ratio('var(--code-token-constant)', 'var(--code-background)', light)).toBe(4.55);
    expect(ratio('var(--layer-PERCEIVE)', tint('var(--layer-PERCEIVE)'), light)).toBe(4.98);
    expect(ratio('var(--layer-EXECUTE)', tint('var(--layer-EXECUTE)'), light)).toBe(4.25);
    expect(ratio('var(--risk-medium)', tint('var(--risk-medium)'), light)).toBe(4.7);
    expect(ratio('var(--risk-high)', 'var(--bg)', light)).toBe(6.47);
  });

  it('matches the dark values', () => {
    expect(ratio('var(--ink)', 'var(--bg)', dark)).toBe(16.79);
    expect(ratio('var(--line)', 'var(--bg)', dark)).toBe(4.4);
    expect(ratio('var(--line)', 'var(--bg-mut)', dark)).toBe(3.59);
    expect(ratio('var(--line)', 'var(--accent)', dark)).toBe(2);
    expect(ratio('var(--ink-3)', tint('var(--layer-REMEMBER)'), dark)).toBe(4.55);
    expect(ratio('var(--risk-high)', 'var(--bg)', dark)).toBe(6.82);
  });
});

describe('checkContrast', () => {
  it('passes the real tokens', () => {
    const r = checkContrast(css);
    expect(r.problems).toEqual([]);
    expect(r.failures).toEqual([]);
  });

  it('fails when a muted text colour drops below 4.5:1', () => {
    const bad = css.replace('--ink-3: #566479;', '--ink-3: #9aa5b4;');
    expect(checkContrast(bad).failures.some((f) => f.startsWith('light: --ink-3 on --bg '))).toBe(true);
  });

  it('fails when the accent fill has no visible edge', () => {
    // Light accent on white is 2.14; a pale line around it leaves no 3:1 edge.
    const bad = css.replace('--line: #0d1526;', '--line: #7dd3fc;');
    expect(checkContrast(bad).failures.some((f) => f.includes('accent fill edge'))).toBe(true);
  });

  it('fails when the two dark blocks disagree', () => {
    const i = css.lastIndexOf('--ink-2: #c6d0dd;');
    const bad = `${css.slice(0, i)}--ink-2: #c6d0de;${css.slice(i + '--ink-2: #c6d0dd;'.length)}`;
    expect(checkContrast(bad).problems).toEqual(['dark blocks differ on --ink-2: #c6d0dd vs #c6d0de']);
  });
});

// Visual spec 6.2: every colour a figure uses is checked or named as an
// exception. The expected token list is read from the figure stylesheets
// and components here, not from the script.
describe('figure colours', () => {
  const sources = [
    ...readdirSync('src/styles').filter((f) => f.startsWith('figures')).map((f) => `src/styles/${f}`),
    ...readdirSync('src/components/fig').map((f) => `src/components/fig/${f}`),
    ...readdirSync('src/lib').filter((f) => f.endsWith('-figures.ts')).map((f) => `src/lib/${f}`),
    ...readdirSync('src/lib/mermaid').map((f) => `src/lib/mermaid/${f}`),
  ];
  const used = new Set<string>();
  for (const f of sources) {
    const text = readFileSync(f, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
    for (const m of text.matchAll(/(?:^|[\s;{"'`])(?:color|fill|stroke|background(?:-color)?|border(?:-[a-z]+)?|box-shadow|outline(?:-color)?)\s*:\s*([^;"'`}]*)/g)) {
      for (const t of m[1]!.matchAll(/var\((--[a-z0-9-]+)\)/g)) used.add(t[1]!);
    }
    // Tokens a component picks at run time, as in var(${...'--heat-line'}).
    for (const t of text.matchAll(/'(--(?:heat|on-heat|risk|layer|ink|bg|line|rule|indicator|accent|ok)[a-z0-9-]*)'/g)) used.add(t[1]!);
  }
  // Theme-independent sizes and the per-element context variables.
  const notColours = (t: string) => /^--(px|space-|shadow-\d|font-|step-|radius|pip|header-|sidebar-|toc-|content-|frame-)/.test(t) || t === '--border';
  // --layer and --tint are set per element from --layer-<ID>; the script checks every layer.
  // The others are set per element too, each only from tokens the script checks:
  // --c, the RFC index tile's status colour (figures-indexes.css): --ink-2,
  // --ok or a risk colour on --bg-sub; --cell and --cell-ink, a heat cell's
  // fill and count (UsageMatrix, RiskByLayer): --heat-N and --on-heat-N.
  const context: Record<string, RegExp> = {
    '--layer': /--layer-/,
    '--tint': /--layer-.*--tint-amount/,
    '--c': /var\(--(risk-(low|medium|high)|ok)\)/,
    '--cell': /var\(--heat-\d\)/,
    '--cell-ink': /var\(--on-heat-\d\)/,
  };

  it('checks every colour token the figures use, in light and dark, or names it as an exception', () => {
    const covered = (t: string, tokens: Record<string, string>) =>
      pairs(tokens).some((p) =>
        [p.fg, p.bg, ...(p.anyOf ?? []).flatMap((a) => [a.fg, a.bg])].some((c) => c !== undefined && (context[t] ? context[t]!.test(c) : c.includes(`var(${t})`))),
      );
    const colours = [...used].filter((t) => !notColours(t));
    expect(colours.length).toBeGreaterThan(10);
    const unchecked = colours.filter((t) => !(t in FIGURE_COLOUR_EXCEPTIONS) && (!covered(t, light) || !covered(t, dark)));
    expect(unchecked).toEqual([]);
  });

  it('fails a heat border that blends into its step, as --line would in dark', () => {
    const bad = css.replaceAll('--heat-line: var(--bg);', '--heat-line: var(--line);');
    expect(checkContrast(bad).failures.filter((f) => f.startsWith('dark: --heat-line border on --heat-')).length).toBeGreaterThan(0);
  });

  it('fails a safety "yes" fill strong enough to bury the text', () => {
    const bad = css.replaceAll('--safety-on-amount: 8%;', '--safety-on-amount: 70%;');
    expect(checkContrast(bad).failures.some((f) => /^dark: figure: --ink on \w+ safety "yes" cell/.test(f))).toBe(true);
  });
});
