// Checks that the design system covers the data, run before every build:
// - every ontology layer has a --layer-<ID> token in the light and the dark
//   block of tokens.css and a glyph in src/pixel/glyphs.ts, with nothing extra
//   on any side;
// - every grid (layer glyphs, UI glyphs, the mark, the letters) parses and is
//   rectangular, at the size its kind needs;
// - every status value the sources use, and every RFC status
//   spec/GOVERNANCE.md allows, has a badge style in src/lib/status.ts;
// - no count is typed by hand into the site source: a number (in digits, in
//   words up to forty, or as a JSX expression such as {36}) before a noun the
//   data counts (capabilities, layers, workflows, profiles, edges, domains,
//   diagnostic codes), or a CSS repeat() of the layer or capability count.
//
// Run: node scripts/check-design-data.mjs
import { execFileSync } from 'node:child_process';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse } from 'yaml';
import { ruleDeclarations } from './check-contrast.mjs';
import { LAYER_GLYPHS, LETTERS, MARK, UI_GLYPHS } from '../src/pixel/glyphs.ts';
import { parseGrid } from '../src/pixel/grid.ts';
import { governanceStatuses } from '../src/lib/governance.ts';
import { STATUS_STYLES } from '../src/lib/status.ts';

const SITE = fileURLToPath(new URL('..', import.meta.url));
const REPO = path.resolve(SITE, '..');

/** Layer ids in the ontology, in order. */
export function ontologyLayers(yamlText) {
  const doc = parse(yamlText);
  return Object.keys(doc?.layers ?? {});
}

/** Problems with layer coverage across the ontology, the token blocks and the glyphs. */
export function checkLayers(layers, tokensCss, glyphNames) {
  const problems = [];
  const same = (label, have) => {
    for (const l of layers) if (!have.includes(l)) problems.push(`layer ${l} has no ${label}`);
    for (const h of have) if (!layers.includes(h)) problems.push(`${label} ${h} is not an ontology layer`);
  };
  for (const [label, selector] of [
    ['light token', ':root'],
    ['dark token', ':root[data-theme="dark"]'],
    ['dark media-query token', ':root:not([data-theme="light"])'],
  ]) {
    const decl = ruleDeclarations(tokensCss, selector) ?? {};
    same(label, Object.keys(decl).filter((k) => k.startsWith('--layer-')).map((k) => k.slice('--layer-'.length)));
  }
  same('glyph', glyphNames);
  if (layers.length === 0) problems.push('the ontology has no layers');
  return problems;
}

/** Problems with the grids: each must parse, at the size its kind uses. */
export function checkGrids(sets) {
  const problems = [];
  for (const { label, grids, size } of sets) {
    for (const [name, rows] of Object.entries(grids)) {
      try {
        const g = parseGrid(name, rows);
        if (size && (g.w !== size[0] || g.h !== size[1]) && !(size.allow ?? []).includes(name)) {
          problems.push(`${label} ${name} is ${g.w}x${g.h}, expected ${size[0]}x${size[1]}`);
        }
      } catch (err) {
        problems.push(`${label}: ${err.message}`);
      }
    }
  }
  return problems;
}

export { governanceStatuses };

/**
 * Status values the site shows a badge for, from the sources:
 * - every `**Document Status**:` value;
 * - the `**Status:**` value of each RFC and proposal;
 * - the first clause of each Standard's `**Status:**` line.
 */
export function sourceStatuses(files) {
  const out = new Map();
  const add = (value, where) => {
    if (!out.has(value)) out.set(value, where);
  };
  for (const { path: p, text } of files) {
    for (const m of text.matchAll(/^\*\*Document Status\*\*:\s*(.+)$/gm)) add(m[1].trim(), p);
    const status = /^\*\*Status:\*\*\s*(.+)$/m.exec(text)?.[1];
    if (!status) continue;
    if (/^spec\/RFC-\d{4}-/.test(p) || p.startsWith('docs/proposals/')) add(status.trim(), p);
    if (/^spec\/STANDARD-v\d+\.\d+\.\d+\.md$/.test(p)) add(status.split(/\s+[—–-]\s+|;/)[0].trim(), p); // as versions.ts reads it
  }
  return out;
}

export function checkStatuses(values, styles) {
  return [...values].filter(([v]) => !(v in styles)).map(([v, where]) => `status "${v}" (${where}) has no badge style in src/lib/status.ts`);
}

const UNITS = ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine'];
const TEENS = ['ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen'];
/** A count in digits, in words from one to forty-nine, or as a JSX expression such as {36}. */
const NUMBER = `(?:\\d+|\\{\\s*\\d+\\s*\\}|(?:twenty|thirty|forty)(?:-(?:${UNITS.join('|')}))?|${[...UNITS, ...TEENS].join('|')})`;
/** Nouns for the things the data counts. */
const COUNTED = '(?:capabilit\\w*|layers?|workflows?|profiles?|edges?|domains?|diagnostic\\s+codes?|diagnostics)\\b';

/**
 * Hand-typed counts in site source. `counts` are numbers that must not be
 * typed into CSS repeat() (the layer and capability counts).
 */
export function findHandTypedCounts(files, counts) {
  const problems = [];
  const nearNoun = new RegExp(
    `(?<![\\w-])${NUMBER}\\s+(?:(?:atomic|cognitive|reference|domain|core|composed|ontology)\\s+)?${COUNTED}`,
    'gi',
  );
  const repeat = /repeat\(\s*(\d+)\s*,/g;
  for (const { path: p, text } of files) {
    const lines = text.split('\n');
    lines.forEach((line, i) => {
      for (const m of line.matchAll(nearNoun)) problems.push(`${p}:${i + 1}: "${m[0]}" types a count by hand`);
      for (const m of line.matchAll(repeat)) {
        if (counts.includes(Number(m[1]))) problems.push(`${p}:${i + 1}: "${m[0]}" types a count by hand; set it from the data`);
      }
    });
  }
  return problems;
}

function sourceFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = path.join(dir, name);
    if (statSync(p).isDirectory()) out.push(...sourceFiles(p));
    else if (/\.(astro|ts|md|css|mjs)$/.test(name)) out.push(p);
  }
  return out;
}

const EXCLUDED = /^(_archive|analysis|tasks|docs\/reviews)\//;

function main() {
  const read = (p) => readFileSync(path.join(REPO, p), 'utf8');
  const tokensCss = readFileSync(path.join(SITE, 'src/styles/tokens.css'), 'utf8');
  const ontology = parse(read('schemas/capability_ontology.yaml'));
  const layers = Object.keys(ontology.layers ?? {});
  const capabilityCount = Array.isArray(ontology.nodes) ? ontology.nodes.length : Object.keys(ontology.nodes ?? {}).length;

  const problems = [
    ...checkLayers(layers, tokensCss, Object.keys(LAYER_GLYPHS)),
    ...checkGrids([
      { label: 'layer glyph', grids: LAYER_GLYPHS, size: [9, 9] },
      { label: 'UI glyph', grids: UI_GLYPHS, size: Object.assign([7, 7], { allow: ['pip'] }) },
      { label: 'mark', grids: { mark: MARK }, size: [12, 12] },
      { label: 'letter', grids: LETTERS, size: [5, 7] },
    ]),
  ];

  const tracked = execFileSync('git', ['ls-files', '*.md'], { cwd: REPO, encoding: 'utf8' })
    .split('\n')
    .filter((p) => p && !EXCLUDED.test(p));
  const statuses = sourceStatuses(tracked.map((p) => ({ path: p, text: read(p) })));
  for (const s of governanceStatuses(read('spec/GOVERNANCE.md'))) if (!statuses.has(s)) statuses.set(s, 'spec/GOVERNANCE.md');
  problems.push(...checkStatuses(statuses, STATUS_STYLES));

  const files = sourceFiles(path.join(SITE, 'src')).map((p) => ({ path: path.relative(SITE, p), text: readFileSync(p, 'utf8') }));
  problems.push(...findHandTypedCounts(files, [layers.length, capabilityCount]));

  for (const p of problems) console.error(`check-design-data: ${p}`);
  if (problems.length > 0) process.exit(1);
  console.log(
    `check-design-data: ${layers.length} layers have light and dark tokens and a glyph; ` +
      `${Object.keys(LAYER_GLYPHS).length + Object.keys(UI_GLYPHS).length + Object.keys(LETTERS).length + 1} grids parse; ` +
      `${statuses.size} status values have a style; no hand-typed counts in ${files.length} source files`,
  );
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) main();
