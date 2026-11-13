// Checks that the design system covers the data, run before every build:
// - every ontology layer has a --layer-<ID> token in the light and the dark
//   block of tokens.css and a glyph in src/pixel/glyphs.ts, with nothing extra
//   on any side;
// - every grid (layer glyphs, UI glyphs, the mark, the letters) parses and is
//   rectangular, at the size its kind needs;
// - every status value the sources use, and every RFC status
//   spec/GOVERNANCE.md allows, has a badge style in src/lib/status.ts;
// - every glyph key the figures look up from data has a grid (visual spec
//   2.2, 2.3): each H2 of each Standard (appendices aside), each domain
//   profile, each trust-source type, each design principle of the current
//   Standard, each gate and failure action of the catalog schema, and each
//   ontology edge type; every reuse alias points at a grid;
// - no figure component types a hex colour;
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
import { CONCEPT_GLYPHS, GLYPH_ALIASES, LAYER_GLYPHS, LETTERS, MARK, UI_GLYPHS } from '../src/pixel/glyphs.ts';
import { ALL_GRIDS, chapterKey, principleKey, resolveGlyphKey } from '../src/pixel/keys.ts';
import { parseGrid } from '../src/pixel/grid.ts';
import { governanceStatuses } from '../src/lib/governance.ts';
import { PROPOSED_WORKFLOW_STATUS, STATUS_STYLES, statusClause } from '../src/lib/status.ts';
import { isMain } from './is-main.mjs';

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

/**
 * `text` with the lines of its fenced code blocks blanked (the line count is
 * kept), so a "## " line inside a fence is not read as a heading. A fence
 * opens with three or more backticks or tildes and closes with a run of the
 * same character at least as long.
 */
export function withoutFences(text) {
  let open = null;
  return text
    .split('\n')
    .map((l) => {
      const f = /^ {0,3}(`{3,}|~{3,})/.exec(l)?.[1];
      if (open === null) {
        if (!f || (f[0] === '`' && l.slice(l.indexOf(f) + f.length).includes('`'))) return l;
        open = f;
        return '';
      }
      if (f && f[0] === open[0] && f.length >= open.length && l.trim() === f) open = null;
      return '';
    })
    .join('\n');
}

/**
 * Glyph keys the figures need, read from the sources, each with where it came
 * from. `standards` are the Standard files as { path, text }, the current one
 * first; `profiles` are { stem, doc } of the domain profiles.
 */
export function neededGlyphKeys({ standards, profiles, catalogSchema, edgeTypes }) {
  const out = [];
  standards = standards.map((s) => ({ ...s, text: withoutFences(s.text) }));
  for (const { path: p, text } of standards) {
    for (const m of text.matchAll(/^## (.+)$/gm)) {
      const key = chapterKey(m[1]);
      if (key) out.push({ key, from: `${p}: "## ${m[1].trim()}"` });
    }
  }
  const current = standards[0];
  if (current) {
    const start = current.text.search(/^## 3\. /m);
    const end = current.text.slice(start + 1).search(/^## /m);
    const section = current.text.slice(start, end === -1 ? undefined : start + 1 + end);
    for (const m of section.matchAll(/^### (.+)$/gm)) out.push({ key: principleKey(m[1]), from: `${current.path}: "### ${m[1].trim()}"` });
  }
  for (const { stem, doc } of profiles) {
    out.push({ key: `domain:${stem}`, from: `schemas/profiles/${stem}.yaml` });
    for (const src of Array.isArray(doc?.domain_sources) ? doc.domain_sources : []) {
      if (src && typeof src.type === 'string') out.push({ key: `source:${src.type}`, from: `schemas/profiles/${stem}.yaml domain_sources` });
    }
  }
  const defs = catalogSchema?.$defs ?? {};
  for (const a of defs.gate?.properties?.action?.enum ?? []) out.push({ key: `gate:${a}`, from: 'workflow_catalog.schema.json gate action' });
  for (const a of defs.failure_mode?.properties?.action?.enum ?? []) out.push({ key: `fail:${a}`, from: 'workflow_catalog.schema.json failure action' });
  for (const t of edgeTypes) out.push({ key: `mark:${t}`, from: 'capability_ontology.yaml edge types' });
  return out;
}

/** Problems with glyph keys: a needed key with no grid, an alias with no target, an alias that shadows a grid. */
export function checkGlyphKeys(needed, aliases = GLYPH_ALIASES, grids = ALL_GRIDS) {
  const problems = [];
  const seen = new Set();
  for (const { key, from } of needed) {
    if (seen.has(key)) continue;
    seen.add(key);
    if (resolveGlyphKey(key) === null) problems.push(`glyph ${key} (${from}) has no grid in src/pixel/glyphs.ts`);
  }
  for (const [key, target] of Object.entries(aliases)) {
    if (key in grids) problems.push(`glyph alias ${key} is also a grid`);
    if (resolveGlyphKey(target) === null) problems.push(`glyph alias ${key} points at ${target}, which has no grid`);
  }
  return problems;
}

/** Hex colours typed into figure components, which must paint with tokens. */
export function findHexColours(files) {
  const problems = [];
  for (const { path: p, text } of files) {
    text.split('\n').forEach((line, i) => {
      for (const m of line.matchAll(/#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b(?![-\w])/g)) problems.push(`${p}:${i + 1}: "${m[0]}" is a hex colour; use a token`);
    });
  }
  return problems;
}

export { governanceStatuses };

/**
 * Status values the site shows a badge for, from the sources:
 * - every `**Document Status**:` value;
 * - the first clause of every `**Status:**` (or `**Status**:`) line, as
 *   statusClause() reads it: an RFC's whole value, the Standard's
 *   "Candidate Standard", a compliance document's "Template".
 */
export function sourceStatuses(files) {
  const out = new Map();
  const add = (value, where) => {
    if (value && !out.has(value)) out.set(value, where);
  };
  for (const { path: p, text } of files) {
    for (const m of text.matchAll(/^\*\*Document Status\*\*:\s*(.+)$/gm)) add(m[1].trim(), p);
    for (const m of text.matchAll(/^\*\*Status(?::\*\*|\*\*:)\s*(.+)$/gm)) add(statusClause(m[1]), p);
  }
  return out;
}

/**
 * The status glyph each status value in use needs: `status:<style>` for its
 * badge style. Values with no style are left to checkStatuses().
 */
export function statusGlyphKeys(values, styles) {
  return [...values].filter(([v]) => v in styles).map(([v, where]) => ({ key: `status:${styles[v]}`, from: `status "${v}" (${where})` }));
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
      { label: 'concept glyph', grids: CONCEPT_GLYPHS, size: [9, 9] },
      { label: 'mark', grids: { mark: MARK }, size: [12, 12] },
      { label: 'letter', grids: LETTERS, size: [5, 7] },
    ]),
  ];

  const standardPaths = execFileSync('git', ['ls-files', 'spec/STANDARD-v*.md'], { cwd: REPO, encoding: 'utf8' })
    .split('\n')
    .filter(Boolean)
    .sort((a, b) => b.localeCompare(a, undefined, { numeric: true }));
  const profileStems = readdirSync(path.join(REPO, 'schemas/profiles'))
    .filter((f) => f.endsWith('.yaml') && f !== 'profile_schema.yaml')
    .map((f) => f.slice(0, -'.yaml'.length));
  const needed = neededGlyphKeys({
    standards: standardPaths.map((p) => ({ path: p, text: read(p) })),
    profiles: profileStems.map((stem) => ({ stem, doc: parse(read(`schemas/profiles/${stem}.yaml`)) })),
    catalogSchema: JSON.parse(read('schemas/workflow_catalog.schema.json')),
    edgeTypes: Object.keys(ontology.edge_types ?? {}),
  });
  problems.push(...checkGlyphKeys(needed));
  const components = sourceFiles(path.join(SITE, 'src/components/fig')).map((p) => ({ path: path.relative(SITE, p), text: readFileSync(p, 'utf8') }));
  problems.push(...findHexColours(components));

  const tracked = execFileSync('git', ['ls-files', '*.md'], { cwd: REPO, encoding: 'utf8' })
    .split('\n')
    .filter((p) => p && !EXCLUDED.test(p));
  const statuses = sourceStatuses(tracked.map((p) => ({ path: p, text: read(p) })));
  for (const s of governanceStatuses(read('spec/GOVERNANCE.md'))) if (!statuses.has(s)) statuses.set(s, 'spec/GOVERNANCE.md');
  problems.push(...checkStatuses(statuses, STATUS_STYLES));
  statuses.set(PROPOSED_WORKFLOW_STATUS, 'src/lib/status.ts');
  problems.push(...checkGlyphKeys(statusGlyphKeys(statuses, STATUS_STYLES), {}));

  const files = sourceFiles(path.join(SITE, 'src')).map((p) => ({ path: path.relative(SITE, p), text: readFileSync(p, 'utf8') }));
  problems.push(...findHandTypedCounts(files, [layers.length, capabilityCount]));

  for (const p of problems) console.error(`check-design-data: ${p}`);
  if (problems.length > 0) process.exit(1);
  console.log(
    `check-design-data: ${layers.length} layers have light and dark tokens and a glyph; ` +
      `${Object.keys(ALL_GRIDS).length + Object.keys(LETTERS).length + 1} grids parse; ` +
      `${new Set(needed.map((n) => n.key)).size} glyph keys from the data have a grid; ` +
      `${statuses.size} status values have a style; no hand-typed counts in ${files.length} source files`,
  );
}

if (isMain(import.meta.url)) main();
