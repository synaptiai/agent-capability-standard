// Checks the colour pairs the design system relies on, in both themes, from
// src/styles/tokens.css. Contrast is the WCAG 2.x ratio of relative
// luminances; higher is better. Text needs 4.5:1. Edges, glyphs and the
// current-item marker need 3:1. The pairs and their exceptions follow the
// design notes (design-system section 4, as amended by the review):
// - the light accent on the page (2.14) is never used as an edge: the 2px
//   line around an accent fill is its edge, so an accent fill passes when
//   either the fill or its line reaches 3:1 against the page;
// - --rule is decorative and never the only edge of a control;
// - a dark tile border against its own tint is not checked, because the
//   tile's frame sits against the page.
// It also fails when the two dark blocks (media query and data-theme) differ.
//
// Run: node scripts/check-contrast.mjs [path/to/tokens.css]
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { isMain } from './is-main.mjs';

export const TEXT_MIN = 4.5;
export const EDGE_MIN = 3;

const SELECTORS = {
  light: ':root',
  darkMedia: ':root:not([data-theme="light"])',
  dark: ':root[data-theme="dark"]',
};

/** The declarations of the first rule whose selector is exactly `selector`. */
export function ruleDeclarations(css, selector) {
  const text = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const re = /([^{};]+)\{/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    if (m[1].trim() !== selector) continue;
    let depth = 1;
    let i = re.lastIndex;
    for (; i < text.length && depth > 0; i++) {
      if (text[i] === '{') depth++;
      else if (text[i] === '}') depth--;
    }
    const body = text.slice(re.lastIndex, i - 1);
    const out = {};
    for (const d of body.matchAll(/(--[A-Za-z0-9-]+)\s*:\s*([^;]+);/g)) out[d[1]] = d[2].trim();
    return out;
  }
  return null;
}

/** Light and dark token maps. Dark is light overlaid with the dark block. */
export function parseTokens(css) {
  const light = ruleDeclarations(css, SELECTORS.light);
  const darkMedia = ruleDeclarations(css, SELECTORS.darkMedia);
  const dark = ruleDeclarations(css, SELECTORS.dark);
  const problems = [];
  if (!light) problems.push(`no ${SELECTORS.light} block`);
  if (!darkMedia) problems.push(`no ${SELECTORS.darkMedia} block inside the dark media query`);
  if (!dark) problems.push(`no ${SELECTORS.dark} block`);
  if (darkMedia && dark) {
    for (const k of new Set([...Object.keys(darkMedia), ...Object.keys(dark)])) {
      if (darkMedia[k] !== dark[k]) problems.push(`dark blocks differ on ${k}: ${darkMedia[k] ?? '(missing)'} vs ${dark[k] ?? '(missing)'}`);
    }
  }
  return { light: light ?? {}, dark: { ...(light ?? {}), ...(dark ?? {}) }, problems };
}

function hexToRgb(hex) {
  const h = hex.replace('#', '');
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  if (!/^[0-9a-fA-F]{6}$/.test(full)) throw new Error(`not a hex colour: ${hex}`);
  return [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16));
}

/** Split on commas that are not inside parentheses. */
function splitTop(s) {
  const parts = [];
  let depth = 0;
  let cur = '';
  for (const ch of s) {
    if (ch === '(') depth++;
    if (ch === ')') depth--;
    if (ch === ',' && depth === 0) {
      parts.push(cur.trim());
      cur = '';
    } else cur += ch;
  }
  parts.push(cur.trim());
  return parts;
}

/**
 * Resolve a CSS colour expression to [r, g, b] (0-255) using a token map.
 * Supports hex, var(--x) and color-mix(in srgb, A P%, B).
 */
export function resolveColor(expr, tokens, seen = new Set()) {
  const e = expr.trim();
  if (e.startsWith('#')) return hexToRgb(e);
  const v = /^var\((--[A-Za-z0-9-]+)\)$/.exec(e);
  if (v) {
    const name = v[1];
    if (seen.has(name)) throw new Error(`token cycle at ${name}`);
    if (!(name in tokens)) throw new Error(`unknown token ${name}`);
    return resolveColor(tokens[name], tokens, new Set([...seen, name]));
  }
  const mix = /^color-mix\(\s*in srgb\s*,([\s\S]*)\)$/.exec(e);
  if (mix) {
    const [a, b] = splitTop(mix[1]);
    const am = /^(.*?)\s+(var\(--[A-Za-z0-9-]+\)|[\d.]+%)$/.exec(a);
    if (!am || !b) throw new Error(`unsupported color-mix: ${e}`);
    const pct = resolvePercent(am[2], tokens);
    const ca = resolveColor(am[1], tokens, seen);
    const cb = resolveColor(b, tokens, seen);
    return ca.map((x, i) => Math.round(x * pct + cb[i] * (1 - pct)));
  }
  throw new Error(`unsupported colour expression: ${e}`);
}

function resolvePercent(expr, tokens) {
  const v = /^var\((--[A-Za-z0-9-]+)\)$/.exec(expr);
  const raw = v ? tokens[v[1]] : expr;
  const m = /^([\d.]+)%$/.exec(raw ?? '');
  if (!m) throw new Error(`not a percentage: ${expr}`);
  return Number(m[1]) / 100;
}

function luminance([r, g, b]) {
  const ch = (c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b);
}

export function contrast(a, b) {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

const tint = (c, amount = 'var(--tint-amount)') => `color-mix(in srgb, ${c} ${amount}, var(--bg))`;

/**
 * Every pair to check. `kind` is text (4.5:1) or edge (3:1). `anyOf` passes
 * when any of its pairs passes (an accent fill and the line around it).
 */
export function pairs(tokens) {
  const layers = Object.keys(tokens).filter((k) => k.startsWith('--layer-')).map((k) => k.slice('--layer-'.length));
  const surfaces = ['--bg', '--bg-sub', '--bg-mut', '--bg-code'];
  const out = [];
  const add = (kind, label, fg, bg) => out.push({ kind, label, fg, bg });

  for (const t of ['--ink', '--ink-2', '--ink-3', '--link']) for (const s of surfaces) add('text', `${t} on ${s}`, `var(${t})`, `var(${s})`);
  add('text', '--on-accent on --accent', 'var(--on-accent)', 'var(--accent)');
  add('text', '--ink on --accent-soft', 'var(--ink)', 'var(--accent-soft)');
  add('text', '--bg on --ink (solid Normative badge)', 'var(--bg)', 'var(--ink)');

  for (const l of layers) {
    const c = `var(--layer-${l})`;
    add('text', `${l} on --bg`, c, 'var(--bg)');
    add('text', `${l} on --bg-sub`, c, 'var(--bg-sub)');
    add('text', `--ink on ${l} tint`, 'var(--ink)', tint(c));
    add('text', `--ink-3 on ${l} tint`, 'var(--ink-3)', tint(c));
    add('edge', `${l} glyph on ${l} tint`, c, tint(c));
  }

  for (const r of ['--risk-low', '--risk-medium', '--risk-high', '--ok']) {
    add('text', `${r} on --bg`, `var(${r})`, 'var(--bg)');
    add('text', `${r} on its tint`, `var(${r})`, tint(`var(${r})`));
  }
  add('text', '--on-risk-high on --risk-high', 'var(--on-risk-high)', 'var(--risk-high)');

  for (const c of ['--link', '--ok', '--risk-medium', '--risk-high', '--kw-must', '--kw-should', '--kw-may']) {
    const fill = tint(`var(${c})`, 'var(--callout-amount)');
    add('text', `${c} label on its callout`, `var(${c})`, fill);
    for (const t of ['--ink', '--ink-2', '--link']) add('text', `${t} on ${c} callout`, `var(${t})`, fill);
  }

  const code = Object.keys(tokens).filter((k) => k.startsWith('--code-token-') || k === '--code-foreground');
  for (const k of code) add('text', `${k} on --code-background`, `var(${k})`, 'var(--code-background)');

  for (const e of ['--line', '--control', '--indicator', '--ink']) {
    for (const s of ['--bg', '--bg-sub', '--bg-mut']) add('edge', `${e} on ${s}`, `var(${e})`, `var(${s})`);
  }
  // Heat cells (visual spec 1.2, 6.2): the printed count on each step, the
  // cell's --heat-line border against the step it frames, and the cell's
  // edge against the figure panel, which passes when the fill or its border
  // reaches 3:1 against --bg-sub (a light step can be fainter than 3:1
  // against the panel, as with the accent fill).
  for (const h of Object.keys(tokens).filter((k) => /^--heat-\d$/.test(k))) {
    add('text', `--on-${h.slice(2)} count on ${h}`, `var(--on-${h.slice(2)})`, `var(${h})`);
    add('edge', `--heat-line border on ${h}`, 'var(--heat-line)', `var(${h})`);
    out.push({
      kind: 'edge',
      label: `${h} cell edge on --bg-sub (the fill itself or its --heat-line border)`,
      anyOf: [
        { fg: `var(${h})`, bg: 'var(--bg-sub)' },
        { fg: 'var(--heat-line)', bg: 'var(--bg-sub)' },
      ],
    });
  }
  out.push(...figurePairs(tokens, layers));
  out.push({
    kind: 'edge',
    label: 'accent fill edge on --bg (the fill itself or its --line border)',
    anyOf: [
      { fg: 'var(--accent)', bg: 'var(--bg)' },
      { fg: 'var(--line)', bg: 'var(--accent)' },
    ],
  });
  return out;
}

/**
 * Colours the figures use (visual spec 6.2), beyond the site-wide pairs
 * above. Figure panels are --bg-sub; cells, chips and boxes inside them are
 * --bg, --bg-sub or --bg-mut.
 */
function figurePairs(tokens, layers) {
  const out = [];
  const add = (kind, label, fg, bg) => out.push({ kind, label, fg, bg });
  const panels = ['--bg-sub', '--bg-mut'];
  // Risk words, pips and policy bars in figures (safety panel, spine risk
  // lane, approval ladder, checkpoint strip), and the ok colour.
  for (const r of ['--risk-low', '--risk-medium', '--risk-high', '--ok']) for (const s of panels) add('text', `figure: ${r} on ${s}`, `var(${r})`, `var(${s})`);
  for (const l of layers) {
    const c = `var(--layer-${l})`;
    // Secondary text in tiles and chips on the layer tint (F-C3, MiniTile, Mermaid chips).
    add('text', `figure: --ink-2 on ${l} tint`, 'var(--ink-2)', tint(c));
    // The layer glyph and the current bar of the layer-bars figure on a --bg-mut track.
    add('edge', `figure: ${l} glyph or bar on --bg-mut`, c, 'var(--bg-mut)');
    // A "yes" cell of a safety panel: --ink text on its fill, and its border
    // (layer-coloured in dark, --line in light) against the fill.
    const on = tint(c, 'var(--safety-on-amount)');
    add('text', `figure: --ink on ${l} safety "yes" cell`, 'var(--ink)', on);
    add('text', `figure: --ink-2 on ${l} safety "yes" cell`, 'var(--ink-2)', on);
    add('edge', `figure: ${l} safety "yes" border on its fill`, `color-mix(in srgb, ${c} var(--safety-on-edge), var(--line))`, on);
    // The home story's marked steps: --ink labels on the layer mixed 22% into
    // --bg (.story__on in components.css).
    add('text', `figure: --ink on ${l} home-story step`, 'var(--ink)', tint(c, '22%'));
  }
  // Recessive bars (the other layers in the layer-bars figure) on their track,
  // and the --indicator bar of PixelBar on its track (also in the site pairs).
  add('edge', 'figure: --ink-3 bar on --bg-mut track', 'var(--ink-3)', 'var(--bg-mut)');
  add('edge', 'figure: --indicator bar on --bg-mut track', 'var(--indicator)', 'var(--bg-mut)');
  // Toolbar toggles and chips: --ink-2 on --accent-soft and dashed --ink-2 slots.
  add('text', 'figure: --ink-2 on --accent-soft', 'var(--ink-2)', 'var(--accent-soft)');
  // Mermaid figures: box outline on the panel, group outline on its group
  // fill and on the panel, and links on both.
  add('edge', 'figure: Mermaid box outline --line on --bg-sub', 'var(--line)', 'var(--bg-sub)');
  add('edge', 'figure: Mermaid box outline --line on its --bg fill', 'var(--line)', 'var(--bg)');
  add('edge', 'figure: Mermaid group outline --ink-3 on --bg-mut', 'var(--ink-3)', 'var(--bg-mut)');
  add('edge', 'figure: Mermaid link --ink-2 on --bg-mut', 'var(--ink-2)', 'var(--bg-mut)');
  add('text', 'figure: Mermaid group label --ink-2 on --bg-mut', 'var(--ink-2)', 'var(--bg-mut)');
  return out;
}

/**
 * Figure colours that are not checked, with the reason (visual spec 6.2).
 * test/contrast.test.ts fails on a colour token a figure stylesheet uses that
 * is neither in a pair nor here.
 */
export const FIGURE_COLOUR_EXCEPTIONS = {
  '--rule': 'decorative: grid-paper dots, dividers, PixelBar ticks and empty matrix cells; never the only edge of anything',
  '--shadow': 'decorative: the hard offset shadow under panels',
  'glyph at 35%': 'decorative: the faded glyph of an "off" safety cell; the word "No" states the state',
};

/** Ratio of a pair, the best ratio of an anyOf pair. */
export function pairRatio(pair, tokens) {
  const options = pair.anyOf ?? [pair];
  return Math.max(...options.map((p) => contrast(resolveColor(p.fg, tokens), resolveColor(p.bg, tokens))));
}

/** Check tokens.css text. Returns { checked, failures, problems }. */
export function checkContrast(css) {
  const { light, dark, problems } = parseTokens(css);
  const failures = [];
  let checked = 0;
  for (const [theme, tokens] of [['light', light], ['dark', dark]]) {
    if (Object.keys(tokens).length === 0) continue;
    for (const p of pairs(tokens)) {
      let ratio;
      try {
        ratio = pairRatio(p, tokens);
      } catch (err) {
        problems.push(`${theme}: ${p.label}: ${err.message}`);
        continue;
      }
      checked += 1;
      const min = p.kind === 'text' ? TEXT_MIN : EDGE_MIN;
      if (ratio < min) failures.push(`${theme}: ${p.label} is ${ratio.toFixed(2)}:1, below ${min}:1 for ${p.kind}`);
    }
  }
  return { checked, failures, problems };
}

if (isMain(import.meta.url)) {
  const file = process.argv[2] ?? fileURLToPath(new URL('../src/styles/tokens.css', import.meta.url));
  const { checked, failures, problems } = checkContrast(readFileSync(file, 'utf8'));
  for (const p of [...problems, ...failures]) console.error(`check-contrast: ${p}`);
  if (problems.length > 0 || failures.length > 0) process.exit(1);
  console.log(`check-contrast: ${checked} pairs in light and dark meet 4.5:1 (text) and 3:1 (edges)`);
}
