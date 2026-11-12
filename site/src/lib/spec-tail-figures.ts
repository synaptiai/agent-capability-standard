// Data for the Standard's figures in chapters 6 to 12 (visual spec 3.9):
// the schema shelf (F-S23), world-state fields (F-S24), merge thresholds
// (F-S24b), decay with a floor (F-S25), the diagnostic families (F-S26),
// where codes are raised (F-S27), what each conformance level checks
// (F-S28), the conformance suite (F-S29), which change bumps which number
// (F-S30), the checkpoint decision tree (F-S31) and the pattern strips
// (F-S32). Each reads the Standard's own section and the files it names,
// and throws when the two disagree. Captions are written here, so the page
// and its Markdown copy match.
import type { List, ListItem, Paragraph } from 'mdast';
import { toString } from 'mdast-util-to-string';
import { parse } from 'yaml';
import { loadDiagnostics, type Diagnostic } from '../data/diagnostics';
import { loadOntology } from '../data/ontology';
import { loadIdentityPolicy, loadTrustModel, RUNTIME_FIXTURE_DIR } from '../data/spec-sources';
import { parseCatalog, type Workflow } from '../data/workflows';
import { readRepoFile, trackedUnder } from './repo';
import { sectionBlocks, sectionFence, sectionParagraphs, sectionTable, tableCodes, tableRows } from './md-sections';
import { schemaListing } from './views';

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
const list = (xs: string[]) => (xs.length < 2 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs.at(-1)}`);

// ---------------------------------------------- F-S23 the schema shelf

export function schemaShelf(text: string, where: string): { name: string; purpose: string; source: string }[] {
  const t = sectionTable(text, '6.1 ', 0, where);
  const rows = tableRows(t).slice(1);
  const codes = tableCodes(t).slice(1);
  const listing = new Map(schemaListing(text).map((e) => [e.name, e]));
  return rows.map((r, i) => {
    const name = codes[i]![0]?.[0] ?? r[0]!;
    const e = listing.get(name);
    if (!e) throw new Error(`${where}: §6.1 names ${name}, which the schema listing does not have`);
    return { name, purpose: r[1]!, source: e.source };
  });
}

export function shelfCaption(files: { name: string }[]): string {
  return `The ${plural(files.length, 'schema file', 'schema files')} every implementation must provide; each links to the file in the repository.`;
}

// ---------------------------------------------- F-S24 world-state fields

export interface FieldRow {
  name: string;
  type: string;
  required: boolean;
  description: string;
}

/** A §6.x field table ("Field | Type | Required | Description") as rows. */
export function fieldRows(text: string, section: string, where: string): FieldRow[] {
  const t = sectionTable(text, section, 0, where);
  const rows = tableRows(t);
  const head = rows[0]!.join('|');
  if (head !== 'Field|Type|Required|Description') throw new Error(`${where}: §${section.trim()}'s table is not "Field | Type | Required | Description"`);
  return rows.slice(1).map((r) => {
    if (r[2] !== 'Yes' && r[2] !== 'No') throw new Error(`${where}: §${section.trim()} row ${r[0]} has Required "${r[2]}", not Yes or No`);
    return { name: r[0]!, type: r[1]!, required: r[2] === 'Yes', description: r[3]! };
  });
}

/** Rows grouped by their dotted prefix ("meta." first), in table order. */
export function fieldGroups(rows: FieldRow[]): { prefix: string | null; rows: FieldRow[] }[] {
  const out: { prefix: string | null; rows: FieldRow[] }[] = [];
  for (const r of rows) {
    const prefix = r.name.includes('.') ? r.name.slice(0, r.name.indexOf('.')) : null;
    const g = out.find((x) => x.prefix === prefix);
    if (g) g.rows.push(r);
    else out.push({ prefix, rows: [r] });
  }
  return out;
}

export function fieldGroupsCaption(rows: FieldRow[], what: string): string {
  const req = rows.filter((r) => r.required).length;
  const groups = fieldGroups(rows).filter((g) => g.prefix);
  return `${what} has ${plural(rows.length, 'field', 'fields')}, ${req} required${groups.length > 0 ? `; ${list(groups.map((g) => `${plural(g.rows.length, 'sits', 'sit')} under ${g.prefix}`))}` : ''}.`;
}

// ---------------------------------------------- F-S24b merge thresholds

export function thresholdsCaption(): string {
  const p = loadIdentityPolicy();
  const t = p.thresholds;
  return `${plural(t.length, 'threshold', 'thresholds')} on the ${p.range[0]} to ${p.range[1]} alias-confidence scale of identity_resolution_policy.yaml, from ${t[0]!.name} at ${t[0]!.value} down to ${t.at(-1)!.name} at ${t.at(-1)!.value}.`;
}

// ---------------------------------------------- F-S25 decay with a floor

export interface DecayColumn {
  /** Age in half-lives. */
  halfLives: number;
  days: number;
  value: number;
  floored: boolean;
}

/**
 * Columns every half a half-life from 0 to 4 half-lives, each the decay
 * factor max(0.5 ** k, min_trust). Throws unless §8.1 still states the
 * half-life formula and min_trust as a floor on the decay factor.
 */
export function decayColumns(text: string, where: string): { columns: DecayColumn[]; minTrust: number; halfLife: string } {
  const prose = sectionParagraphs(text, '8.1 ', where).join(' ').replace(/\s+/g, ' ');
  if (!prose.includes('0.5 ** (age / half_life)')) throw new Error(`${where}: §8.1 no longer states 0.5 ** (age / half_life)`);
  if (!/min_trust, when present, is a floor on the decay factor/.test(prose)) throw new Error(`${where}: §8.1 no longer makes min_trust a floor on the decay factor`);
  const m = loadTrustModel();
  const columns = Array.from({ length: 9 }, (_, i) => {
    const k = i / 2;
    const raw = 0.5 ** k;
    return { halfLives: k, days: k * m.halfLifeDays, value: Math.max(raw, m.minTrust), floored: raw < m.minTrust };
  });
  return { columns, minTrust: m.minTrust, halfLife: m.halfLife };
}

export function decayCaption(d: { columns: DecayColumn[]; minTrust: number; halfLife: string }): string {
  const first = d.columns.find((c) => c.value <= d.minTrust)!;
  return `With the reference half_life of ${d.halfLife} (${first.days / first.halfLives} days) the decay factor halves every half-life and reaches the min_trust floor of ${d.minTrust} at ${first.halfLives} half-lives (${first.days} days); older observations keep that weight.`;
}

// ---------------------------------------------- F-S26 diagnostic families

export interface Family {
  prefix: string;
  name: string;
  range: string;
  severity: string;
  codes: Diagnostic[];
}

/** §9.1's families in table order, each with its codes from the loader. */
export function diagnosticFamilies(text: string, where: string): Family[] {
  const rows = tableRows(sectionTable(text, '9.1 ', 0, where)).slice(1);
  const all = loadDiagnostics();
  return rows.map((r) => {
    const m = /^([A-Z])\dxx$/.exec(r[1]!);
    if (!m) throw new Error(`${where}: §9.1 range "${r[1]}" is not a letter, a digit and xx`);
    const codes = all.filter((d) => d.code.startsWith(m[1]!) && d.code[1] === r[1]![1]);
    if (codes.length === 0) throw new Error(`${where}: §9.1 family ${r[0]} has no codes in §9.2 to §9.7`);
    return { prefix: m[1]!, name: r[0]!, range: r[1]!, severity: r[2]!, codes };
  });
}

export function familiesCaption(f: Family[]): string {
  const total = f.reduce((a, x) => a + x.codes.length, 0);
  const big = [...f].sort((a, b) => b.codes.length - a.codes.length)[0]!;
  const errors = f.filter((x) => x.severity === 'error').reduce((a, x) => a + x.codes.length, 0);
  return `${plural(total, 'code', 'codes')} in ${plural(f.length, 'family', 'families')}: ${errors} errors and ${total - errors} warnings; ${big.name} is the largest family, with ${big.codes.length}.`;
}

/** The codes of one §9.2 to §9.7 table, from the loader, checked against the table's own rows. */
export function sectionCodes(text: string, section: string, where: string): { heading: string; codes: Diagnostic[] } {
  const rows = tableRows(sectionTable(text, `${section} `, 0, where)).slice(1).map((r) => r[0]!);
  const codes = loadDiagnostics().filter((d) => d.section === section);
  if (rows.join() !== codes.map((d) => d.code).join()) throw new Error(`${where}: §${section}'s table lists ${rows.join(', ')}, the diagnostics loader ${codes.map((d) => d.code).join(', ')}`);
  return { heading: codes[0]!.category, codes };
}

export function sectionCodesCaption(s: { heading: string; codes: Diagnostic[] }): string {
  const errors = s.codes.filter((d) => d.severity === 'error').length;
  const sev = errors === s.codes.length ? 'all errors, drawn with a solid border' : errors === 0 ? 'all warnings, drawn with a dashed border' : `${errors} errors and ${s.codes.length - errors} warnings`;
  return `${plural(s.codes.length, 'code', 'codes')} of ${s.heading.toLowerCase()}, ${sev}; each tile links to the code's entry on the diagnostics page.`;
}

/** F-X1, the diagnostics page's code grid. */
export function codeGridCaption(f: Family[]): string {
  const sizes = [...f].sort((a, b) => b.codes.length - a.codes.length);
  return `${sizes[0]!.name} is the largest family, with ${sizes[0]!.codes.length} codes, and ${sizes.at(-1)!.name} the smallest, with ${sizes.at(-1)!.codes.length}; each tile links to its row below.`;
}

export function familyTableCaption(f: Family): string {
  return `${plural(f.codes.length, 'code', 'codes')} in ${f.range}, every one ${f.severity === 'error' ? 'an error' : 'a warning'}; the Section column names where the Standard defines it.`;
}

/**
 * A Standard's own error categories (its §9.1 table) with the number of codes
 * its §9.x tables list for each, read from the text alone (for 1.0.0, whose
 * codes the diagnostics loader does not hold).
 */
export function categoryCounts(text: string, where: string): { name: string; range: string; prefix: string; count: number }[] {
  const rows = tableRows(sectionTable(text, '9.1 ', 0, where)).slice(1);
  const codes = [...text.matchAll(/^\| ([A-Z]\d{3}) \|/gm)].map((m) => m[1]!);
  return rows.map((r) => {
    const m = /^([A-Z]\d)xx$/.exec(r[1]!);
    if (!m) throw new Error(`${where}: §9.1 range "${r[1]}" is not a letter, a digit and xx`);
    const count = new Set(codes.filter((c) => c.startsWith(m[1]!))).size;
    if (count === 0) throw new Error(`${where}: §9.1 category ${r[0]} has no code in a §9 table`);
    return { name: r[0]!, range: r[1]!, prefix: m[1]![0]!, count };
  });
}

export function categoryCaption(c: { name: string; count: number }[]): string {
  const max = Math.max(...c.map((x) => x.count));
  const top = c.filter((x) => x.count === max).map((x) => x.name);
  return `${plural(c.reduce((a, x) => a + x.count, 0), 'code', 'codes')} in ${plural(c.length, 'category', 'categories')}; ${list(top)} ${top.length === 1 ? 'has' : 'have'} the most, ${max}${top.length === 1 ? '' : ' each'}.`;
}

// ---------------------------------------------- F-S27 where codes are raised

/** The §5.1 to §5.17 sections: number and the text up to the next §5.x heading (subsections included). */
function chapter5Sections(text: string): { n: string; title: string; body: string }[] {
  const lines = text.split('\n');
  const out: { n: string; title: string; body: string }[] = [];
  let cur: { n: string; title: string; body: string } | null = null;
  let in5 = false;
  for (const l of lines) {
    const h2 = /^## (\d+)\./.exec(l);
    if (h2) {
      in5 = h2[1] === '5';
      cur = null;
      continue;
    }
    const h3 = /^### (5\.\d+) (.+)$/.exec(l);
    if (in5 && h3) {
      cur = { n: h3[1]!, title: h3[2]!.trim(), body: '' };
      out.push(cur);
      continue;
    }
    if (in5 && cur) cur.body += `${l}\n`;
  }
  return out;
}

export interface CodeHeat {
  families: { prefix: string; name: string }[];
  sections: { n: string; title: string }[];
  /** counts[family][section]: distinct codes of the family the section names. */
  counts: number[][];
  max: number;
}

export function codeHeat(text: string, where: string): CodeHeat {
  const fams = diagnosticFamilies(text, where);
  const secs = chapter5Sections(text);
  if (secs.length === 0) throw new Error(`${where}: no §5.x sections to count codes in`);
  const named = (body: string) => new Set([...body.matchAll(/\b([A-Z]\d{3})\b/g)].map((m) => m[1]!));
  const counts = fams.map((f) => secs.map((s) => [...named(s.body)].filter((c) => f.codes.some((d) => d.code === c)).length));
  return {
    families: fams.map((f) => ({ prefix: f.prefix, name: f.name })),
    sections: secs.map((s) => ({ n: s.n, title: s.title })),
    counts,
    max: Math.max(1, ...counts.flat()),
  };
}

export function heatCaption(h: CodeHeat): string {
  const per = h.sections.map((s, j) => ({ s, n: h.counts.reduce((a, row) => a + row[j]!, 0) }));
  const top = [...per].sort((a, b) => b.n - a.n)[0]!;
  const fam = h.families.map((f, i) => ({ f, n: h.counts[i]!.filter((c) => c > 0).length })).sort((a, b) => b.n - a.n)[0]!;
  return `§${top.s.n} ${top.s.title} names the most codes (${top.n}); ${fam.f.name} codes are named in the most sections of chapter 5 (${fam.n} of ${h.sections.length}).`;
}

// ---------------------------------------------- F-S28 conformance levels

export interface LevelColumn {
  level: string;
  name: string;
  items: { text: string; sections: string[]; codes: string[] }[];
}

/** §10.2's lists: a "**Ln (Name)**" paragraph and the list after it. */
export function conformanceLevels(text: string, where: string): LevelColumn[] {
  const blocks = sectionBlocks(text, '10.2 ', where);
  const out: LevelColumn[] = [];
  blocks.forEach((b, i) => {
    if (b.type !== 'paragraph') return;
    const m = /^(L\d) \((.+)\)$/.exec(toString(b as Paragraph).trim());
    if (!m) return;
    const next = blocks[i + 1];
    if (next?.type !== 'list') throw new Error(`${where}: §10.2's ${m[1]} has no list after it`);
    const items = (next as List).children.map((li: ListItem) => {
      const t = toString(li).replace(/\s+/g, ' ').trim();
      return { text: t, sections: [...t.matchAll(/§(\d+(?:\.\d+)*)/g)].map((x) => x[1]!), codes: [...t.matchAll(/\b([A-Z]\d{3})\b/g)].map((x) => x[1]!) };
    });
    out.push({ level: m[1]!, name: m[2]!, items });
  });
  const table = tableRows(sectionTable(text, '10.1 ', 0, where)).slice(1).map((r) => r[0]!);
  if (table.join() !== out.map((c) => c.level).join()) throw new Error(`${where}: §10.1 lists ${table.join(', ')}, §10.2 ${out.map((c) => c.level).join(', ')}`);
  return out;
}

export function levelsCaption(cols: LevelColumn[]): string {
  return `${list(cols.map((c) => `${c.level} lists ${c.items.length}`))} requirements; §10.2 states each level's list on its own.`;
}

// ---------------------------------------------- F-S29 the conformance suite

export interface SuitePart {
  label: string;
  count: number;
  dir: string;
}

export function conformanceSuite(text: string, where: string): SuitePart[] {
  const prose = sectionBlocks(text, '10.3 ', where).map((b) => toString(b)).join(' ');
  for (const k of ['Positive fixtures', 'Negative fixtures', 'Patch fixtures', 'Expression fixtures', 'Runtime fixtures']) {
    if (!prose.includes(k)) throw new Error(`${where}: §10.3 no longer names ${k}`);
  }
  const fixtures = trackedUnder('tests/fixtures').map((p) => p.slice('tests/fixtures/'.length)).filter((p) => !p.includes('/'));
  const count = (prefix: string) => fixtures.filter((f) => f.startsWith(prefix)).length;
  const exprCases = ['eval', 'check'].reduce((a, f) => {
    const doc = JSON.parse(readRepoFile(`tests/conformance/expressions/${f}.json`)) as { cases?: unknown[] };
    if (!Array.isArray(doc.cases)) throw new Error(`tests/conformance/expressions/${f}.json has no cases list`);
    return a + doc.cases.length;
  }, 0);
  const runtime = trackedUnder(RUNTIME_FIXTURE_DIR, '.json').length;
  return [
    { label: 'Positive fixtures (pass_)', count: count('pass_'), dir: 'tests/fixtures' },
    { label: 'Negative fixtures (fail_)', count: count('fail_'), dir: 'tests/fixtures' },
    { label: 'Patch fixtures (patch_)', count: count('patch_'), dir: 'tests/fixtures' },
    { label: 'Expression cases', count: exprCases, dir: 'tests/conformance/expressions' },
    { label: 'Runtime fixtures', count: runtime, dir: RUNTIME_FIXTURE_DIR },
  ];
}

export function suiteCaption(parts: SuitePart[]): string {
  const top = [...parts].sort((a, b) => b.count - a.count)[0]!;
  const name = (p: SuitePart) => {
    const words = p.label.replace(/ \(.+\)$/, '').toLowerCase();
    return p.count === 1 ? words.replace(/s$/, '') : words;
  };
  return `The repository's conformance suite: ${list(parts.map((p) => `${p.count} ${name(p)}`))}; ${name(top)} are the largest part.`;
}

// ---------------------------------------------- F-S30 which change bumps which number

export function versionBumps(text: string, where: string): { bump: string; change: string; example: string; changes: string[] }[] {
  const semver = tableRows(sectionTable(text, '11.1 ', 0, where)).slice(1);
  const evo = tableRows(sectionTable(text, '11.4 ', 0, where)).slice(1);
  const by: Record<string, string> = { Breaking: 'MAJOR', Compatible: 'MINOR' };
  for (const r of evo) if (!(r[1]! in by)) throw new Error(`${where}: §11.4 row "${r[0]}" is "${r[1]}", neither Breaking nor Compatible`);
  return semver.map((r) => ({ change: r[0]!, bump: r[1]!, example: r[2]!, changes: evo.filter((e) => by[e[1]!] === r[1]).map((e) => e[0]!) }));
}

export function bumpsCaption(b: { bump: string; changes: string[] }[]): string {
  return `Of the ${plural(b.reduce((a, x) => a + x.changes.length, 0), 'schema change', 'schema changes')} §11.4 lists, ${list(b.filter((x) => x.changes.length > 0).map((x) => `${x.changes.length} need a ${x.bump} release`))}.`;
}

// ---------------------------------------------- F-S31 checkpoint decision tree

export interface TreeNode {
  /** The question, or the outcome at a leaf. */
  text: string;
  /** Branches: the answer and the node it leads to. */
  branches: { answer: string; node: TreeNode }[];
}

/** §12.1's decision tree fence: the root question, then `├──`/`└──` lines of "answer → next". */
export function decisionTree(text: string, where: string): TreeNode {
  const lines = sectionFence(text, '12.1 ', 0, where).value.split('\n').filter((l) => l.trim() !== '');
  const root: TreeNode = { text: lines[0]!.trim(), branches: [] };
  const stack: { depth: number; node: TreeNode }[] = [{ depth: -1, node: root }];
  for (const l of lines.slice(1)) {
    const m = /^([│ ]*)[├└]── (.+)$/.exec(l);
    if (!m) throw new Error(`${where}: §12.1 tree line "${l}" is not a ├── or └── branch`);
    const depth = m[1]!.length / 4;
    const arrow = m[2]!.split(' → ');
    if (arrow.length !== 2) throw new Error(`${where}: §12.1 tree branch "${m[2]}" has no →`);
    while (stack.at(-1)!.depth >= depth) stack.pop();
    const node: TreeNode = { text: arrow[1]!.trim(), branches: [] };
    stack.at(-1)!.node.branches.push({ answer: arrow[0]!.trim(), node });
    stack.push({ depth, node });
  }
  return root;
}

export function treeCaption(t: TreeNode): string {
  const leaves: string[] = [];
  const walk = (n: TreeNode) => (n.branches.length === 0 ? leaves.push(n.text) : n.branches.forEach((b) => walk(b.node)));
  walk(t);
  const questions = (n: TreeNode): number => (n.branches.length === 0 ? 0 : 1 + n.branches.reduce((a, b) => a + questions(b.node), 0));
  return `${plural(questions(t), 'question leads', 'questions lead')} to ${plural(leaves.length, 'outcome', 'outcomes')}: ${list(leaves.map((x) => x.toLowerCase()))}.`;
}

// ---------------------------------------------- F-S32 pattern strips

export interface PatternStrip {
  name: string;
  wf: Workflow;
}

/** A fence's steps read line by line: each `- capability:` starts a step; its store_as and its references are kept. */
export function stepsByLine(fence: string): { capability: string; store_as?: string; input_bindings: Record<string, string> }[] {
  const out: { capability: string; store_as?: string; input_bindings: Record<string, string> }[] = [];
  for (const line of fence.split('\n')) {
    const cap = /^- capability:\s*(\S+)/.exec(line);
    if (cap) {
      out.push({ capability: cap[1]!, input_bindings: {} });
      continue;
    }
    const cur = out.at(-1);
    if (!cur) continue;
    const store = /^\s+store_as:\s*(\S+)/.exec(line);
    if (store) cur.store_as = store[1]!;
    for (const m of line.matchAll(/\$\{[^}]+\}/g)) cur.input_bindings[`ref${Object.keys(cur.input_bindings).length}`] = m[0];
  }
  return out;
}

/** Each §12.5 fence with `capability:` steps, as a workflow, named by the bold "Pattern: …" before it. */
export function patternStrips(text: string, where: string): PatternStrip[] {
  const blocks = sectionBlocks(text, '12.5 ', where);
  const out: PatternStrip[] = [];
  let name: string | null = null;
  for (const b of blocks) {
    if (b.type === 'paragraph') {
      const m = /^Pattern: (.+)$/.exec(toString(b).trim());
      if (m) name = m[1]!;
      continue;
    }
    if (b.type !== 'code') continue;
    if (!name) throw new Error(`${where}: a §12.5 fence has no "Pattern:" name before it`);
    let steps: unknown;
    try {
      steps = parse(b.value);
    } catch {
      // A fence that is not valid YAML (1.0.0 writes an unquoted [${a}, ${b}]):
      // read its steps line by line, keeping what the strip draws.
      steps = stepsByLine(b.value);
    }
    if (!Array.isArray(steps)) throw new Error(`${where}: §12.5's ${name} fence is not a list of steps`);
    const wf = parseCatalog(where, JSON.stringify({ [name]: { goal: name, risk: 'low', steps } }), 'core', loadOntology())[0]!;
    out.push({ name, wf });
    name = null;
  }
  return out;
}

export function patternCaption(p: PatternStrip): string {
  const reads = p.wf.steps.filter((s) => s.consumes.length > 0).length;
  return `${p.name}: ${plural(p.wf.steps.length, 'step', 'steps')} in order, ${reads} of them reading an earlier step's output.`;
}
