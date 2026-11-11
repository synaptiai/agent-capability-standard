// The contrast check on the real tokens and on fixtures. Expected ratios are
// the ones the design notes computed by hand for the frozen palette
// (design-system section 4), rounded to two places, plus the WCAG end points.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { checkContrast, contrast, pairRatio, parseTokens, resolveColor } from '../scripts/check-contrast.mjs';

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
