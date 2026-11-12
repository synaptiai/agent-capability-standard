// Data for the Standard's figures from §1 to §5.17 that SpecFigure draws
// beyond chapters 4 and 5's first sections (visual spec 3.9): where the
// requirement keywords are (F-S0), the safety ordering (F-S1), the safety
// defaults by capability (F-S6), operator precedence (F-S11), the §5.8.3
// static checks, extensions (F-S12), triggers (F-S13), the recovery loop
// (F-S14), a wait on a timeline (F-S15), recovering a silent source (F-S16),
// approval (F-S17), delegation (F-S19), a quorum (F-S20), trust classes
// (F-S21) and the sender filter (F-S22). Each reads the Standard's own
// section and the data it describes, and throws when the two disagree. The
// captions are written here, so the page and its Markdown copy match.
import type { List, ListItem } from 'mdast';
import { toString } from 'mdast-util-to-string';
import { parse } from 'yaml';
import { loadDiagnostics, type Diagnostic } from '../data/diagnostics';
import { loadOntology, type Capability, type EdgeType, type Ontology } from '../data/ontology';
import { loadCatalogEnums, loadIdentitySchema, loadTrustModel, loadWorldStateSchema } from '../data/spec-sources';
import { chapterKey } from '../pixel/keys';
import { sectionBlocks, sectionFence, sectionTable, tableCodes, tableRows } from './md-sections';
import { contractRows, tableOrder, type SchemaRow } from './views';

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
const list = (xs: string[]) => (xs.length < 2 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs.at(-1)}`);
type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);

// ---------------------------------------------- F-S0 where the requirements are

export const KEYWORD_GROUPS = [
  { id: 'must', label: 'MUST', words: ['MUST', 'SHALL', 'REQUIRED'] },
  { id: 'should', label: 'SHOULD', words: ['SHOULD'] },
  { id: 'may', label: 'MAY', words: ['MAY'] },
] as const;

export interface ChapterKeywords {
  n: number;
  title: string;
  glyph: string;
  counts: Record<(typeof KEYWORD_GROUPS)[number]['id'], number>;
}

/**
 * The requirement keywords of each numbered chapter, as uppercase whole
 * words outside code fences. "MUST NOT" counts as one MUST. §1.2, which
 * defines the keywords, is left out.
 */
export function chapterKeywords(text: string): ChapterKeywords[] {
  const lines = text.split(/\r?\n/);
  const out: ChapterKeywords[] = [];
  let cur: ChapterKeywords | null = null;
  let fence = false;
  let skip = false;
  for (const line of lines) {
    if (/^(```|~~~)/.test(line)) {
      fence = !fence;
      continue;
    }
    if (fence) continue;
    const h2 = /^## (\d+)\. (.+)$/.exec(line);
    if (h2) {
      const key = chapterKey(`${h2[1]}. ${h2[2]}`);
      if (!key) throw new Error(`spec figures: chapter "${h2[2]}" has no glyph key`);
      cur = { n: Number(h2[1]), title: h2[2]!.trim(), glyph: key, counts: { must: 0, should: 0, may: 0 } };
      out.push(cur);
      skip = false;
      continue;
    }
    if (/^## /.test(line)) {
      cur = null;
      continue;
    }
    if (/^### /.test(line)) skip = /^### 1\.2 /.test(line);
    if (!cur || skip) continue;
    for (const g of KEYWORD_GROUPS) {
      for (const w of g.words) cur.counts[g.id] += (line.match(new RegExp(`(?<![A-Za-z0-9_])${w}(?![A-Za-z0-9_])`, 'g')) ?? []).length;
    }
  }
  if (out.length === 0) throw new Error('spec figures: the Standard has no "## N." chapters');
  return out;
}

export function keywordsCaption(rows: ChapterKeywords[]): string {
  const total = (id: keyof ChapterKeywords['counts']) => rows.reduce((a, r) => a + r.counts[id], 0);
  const top = [...rows].sort((a, b) => b.counts.must - a.counts.must)[0]!;
  return `The chapters hold ${total('must')} MUST, ${total('should')} SHOULD and ${total('may')} MAY requirements, counted as capitalised words outside code and §1.2; chapter ${top.n}, ${top.title}, has the most MUSTs (${top.counts.must}).`;
}

// ------------------------------------------------------- F-S1 safety ordering

export const ORDER_SOURCES = ['checkpoint', 'plan', 'constrain'] as const;
export const ORDER_TYPES: readonly EdgeType[] = ['requires', 'precedes', 'soft_requires'];

export interface OrderGroup {
  source: string;
  edges: { type: EdgeType; targets: string[] }[];
}

/** For each source of §3.3's rules, its requires, precedes and soft_requires targets in the ontology. */
export function safetyOrder(o: Ontology = loadOntology()): OrderGroup[] {
  return ORDER_SOURCES.map((source) => ({
    source,
    edges: ORDER_TYPES.map((type) => ({ type, targets: o.edges.filter((e) => e.from === source && e.type === type).map((e) => e.to) })).filter((e) => e.targets.length > 0),
  }));
}

/** Every capability id backticked in §3.3 must be in the drawing. Throws naming the ones that are not. */
export function checkSafetyOrder(text: string, where: string, groups: OrderGroup[]): void {
  const caps = new Set(loadOntology().capabilities.map((c) => c.id));
  const codes = new Set<string>();
  for (const b of sectionBlocks(text, '3.3 ', where)) {
    const walk = (n: { type: string; value?: string; children?: unknown[] }) => {
      if (n.type === 'inlineCode' && n.value) codes.add(n.value);
      for (const c of (n.children ?? []) as (typeof n)[]) walk(c);
    };
    walk(b as never);
  }
  const drawn = new Set(groups.flatMap((g) => [g.source, ...g.edges.flatMap((e) => e.targets)]));
  const missing = [...codes].filter((c) => caps.has(c) && !drawn.has(c));
  if (missing.length > 0) throw new Error(`${where}: §3.3 names ${list(missing)}, which the safety ordering figure does not draw`);
}

export function safetyOrderCaption(groups: OrderGroup[]): string {
  const of = (src: string, type: EdgeType) => groups.find((g) => g.source === src)?.edges.find((e) => e.type === type)?.targets ?? [];
  const req = of('checkpoint', 'requires');
  const soft = of('constrain', 'soft_requires');
  const prec = groups.flatMap((g) => g.edges.filter((e) => e.type === 'precedes')).reduce((a, e) => a + e.targets.length, 0);
  return `checkpoint is required before ${list(req)}; ${plural(prec, 'precedes edge orders', 'precedes edges order')} checkpoint, plan and constrain before their targets when both are present; constrain is recommended before ${list(soft)}.`;
}

/** An edge group of F-S1 drawn as a lane: a source, an edge type and its targets. */
export interface OrderLane {
  source: string;
  type: EdgeType;
  targets: string[];
  y: number;
  /** x of the drop from the source to the lane. */
  sx: number;
  /** x of each drop from the lane to a target, in `targets` order. */
  tx: number[];
}

export interface OrderLayout {
  width: number;
  height: number;
  sources: { id: string; x: number }[];
  targets: { id: string; x: number; incoming: { source: string; type: EdgeType }[] }[];
  lanes: OrderLane[];
  /** Tops of the source tiles, the target ports and the target tiles. */
  sourceTop: number;
  portY: number;
  targetTop: number;
  /** The x span of each target's port bar. */
  ports: { id: string; from: number; to: number }[];
}

/** F-S1 geometry (visual spec 3.9 and 2.4): a gutter for the lane marks, one 80px column per target. */
export const ORDER_GEOM = { gutter: 24, col: 104, gap: 16, tile: 32, label: 18, laneGap: 20, chevron: { requires: 20, other: 10 }, slotGap: 2 } as const;

/**
 * Sources on top and targets below, joined by one horizontal lane per
 * (source, edge type): a drop from the source to its lane, the lane, and a
 * drop from the lane to each target, ending in the type's chevron on the
 * target's port bar. Targets are in table order; sources sit over columns
 * spread evenly across them. A target's drops sit side by side on its port,
 * requires first, each as wide as its chevron.
 */
export function safetyOrderLayout(groups: OrderGroup[], o: Ontology = loadOntology()): OrderLayout {
  const g = ORDER_GEOM;
  const order = tableOrder(o);
  const targetIds = [...new Set(groups.flatMap((x) => x.edges.flatMap((e) => e.targets)))].sort((a, b) => order.indexOf(a) - order.indexOf(b));
  const cx = (i: number) => g.gutter + i * (g.col + g.gap) + g.col / 2;
  const width = g.gutter + targetIds.length * g.col + (targetIds.length - 1) * g.gap;
  const span = Math.max(1, targetIds.length - 1);
  const sourceCols = groups.map((_, j) => (groups.length === 1 ? 0 : Math.round((j * span) / (groups.length - 1))));
  const sourceTop = g.label;
  const laneTop = sourceTop + g.tile + 14;
  const raw = groups.flatMap((grp, j) => grp.edges.map((e, k) => ({ source: grp.source, type: e.type, targets: e.targets, j, k, n: grp.edges.length })));
  const lanes: OrderLane[] = raw.map((l, i) => ({
    source: l.source,
    type: l.type,
    targets: l.targets,
    y: laneTop + i * g.laneGap,
    sx: cx(sourceCols[l.j]!) + (l.n === 1 ? 0 : (l.k - (l.n - 1) / 2) * 16),
    tx: [],
  }));
  const portY = laneTop + (lanes.length - 1) * g.laneGap + 18;
  const ports: OrderLayout['ports'] = [];
  const targets = targetIds.map((id, i) => {
    const incoming = lanes.filter((l) => l.targets.includes(id)).sort((a, b) => Number(b.type === 'requires') - Number(a.type === 'requires'));
    const w = (t: EdgeType) => (t === 'requires' ? g.chevron.requires : g.chevron.other);
    const total = incoming.reduce((a, l) => a + w(l.type), 0) + (incoming.length - 1) * g.slotGap;
    if (total > g.col) throw new Error(`safety ordering: ${id} has ${incoming.length} incoming edges, wider than its ${g.col}px column`);
    let x = cx(i) - total / 2;
    for (const l of incoming) {
      l.tx[l.targets.indexOf(id)] = x + w(l.type) / 2;
      x += w(l.type) + g.slotGap;
    }
    ports.push({ id, from: cx(i) - Math.max(total, g.tile) / 2, to: cx(i) + Math.max(total, g.tile) / 2 });
    return { id, x: cx(i), incoming: incoming.map((l) => ({ source: l.source, type: l.type })) };
  });
  const targetTop = portY + 6;
  return {
    width,
    height: targetTop + g.tile + g.label + 2,
    sources: groups.map((grp, j) => ({ id: grp.source, x: cx(sourceCols[j]!) })),
    targets,
    lanes,
    sourceTop,
    portY,
    targetTop,
    ports,
  };
}

// ------------------------------------------------ F-S6 safety defaults

export const FLAG_ROWS = [
  { id: 'mutation', label: 'Changes state', glyph: 'pencil', off: 'does not change state' },
  { id: 'requires_checkpoint', label: 'Needs checkpoint', glyph: 'flag', off: 'needs no checkpoint' },
  { id: 'requires_approval', label: 'Needs approval', glyph: 'stamp', off: 'needs no approval' },
] as const;

export function safetyDefaults(o: Ontology = loadOntology()): { layer: string; caps: Capability[] }[] {
  const order = tableOrder(o);
  return o.layers.map((l) => ({ layer: l.id, caps: order.filter((id) => o.byId.get(id)!.layer === l.id).map((id) => o.byId.get(id)!) }));
}

export function flagWords(c: Capability): string {
  return [`${c.risk} risk`, ...FLAG_ROWS.map((f) => (c[f.id] ? f.label.toLowerCase() : f.off))].join(', ');
}

export function safetyDefaultsCaption(o: Ontology = loadOntology()): string {
  const n = (f: (c: Capability) => boolean) => o.capabilities.filter(f).length;
  return `Of ${o.capabilities.length} capabilities, ${n((c) => c.risk === 'high')} are high risk, ${n((c) => c.mutation)} change state, ${n((c) => c.requires_checkpoint)} need a checkpoint and ${n((c) => c.requires_approval)} need approval; a step may raise any of these, and a weaker value is ignored with W602.`;
}

// ------------------------------------------------ F-S11 operator precedence

export interface Rung {
  rule: string;
  operators: string[];
  note: string | null;
}

/** The EBNF rules of a fence: name -> { body, comment }. */
export function ebnfRules(fence: string): Map<string, { body: string; comment: string }> {
  const out = new Map<string, { body: string; comment: string }>();
  for (const line of fence.split('\n')) {
    const m = /^\s*([a-z_]+)\s*=\s*(.*?)\s*;\s*(?:\(\*\s*(.*?)\s*\*\))?\s*$/.exec(line);
    if (m) out.set(m[1]!, { body: m[2]!, comment: m[3] ?? '' });
  }
  return out;
}

const quoted = (s: string) => [...s.matchAll(/"([^"]+)"/g)].map((m) => m[1]!);
const names = (s: string) => [...s.replace(/"[^"]*"|'[^']*'/g, ' ').matchAll(/\b([a-z_]+)\b/g)].map((m) => m[1]!);

/**
 * The precedence ladder of §5.8.1's grammar, loosest first: from `expr`,
 * each rule's operators (quoted strings, or a rule made only of quoted
 * alternatives, such as cmp_op) and the next tighter rule, down to the
 * rule whose operands are no other operator rule (primary).
 */
export function precedenceLadder(text: string, where: string): Rung[] {
  const rules = ebnfRules(sectionFence(text, '5.8.1 ', 0, where).value);
  const start = rules.get('expr');
  if (!start) throw new Error(`${where}: §5.8.1's grammar has no expr rule`);
  const onlyOps = (r: string) => {
    const b = rules.get(r)?.body ?? '';
    return quoted(b).length > 0 && names(b).length === 0;
  };
  const rungs: Rung[] = [];
  let cur: string | undefined = names(start.body)[0];
  const seen = new Set<string>();
  while (cur && !seen.has(cur)) {
    seen.add(cur);
    const r = rules.get(cur);
    if (!r) throw new Error(`${where}: §5.8.1's grammar has no rule ${cur}`);
    const refs = names(r.body);
    if (refs.includes('expr')) {
      // The operand rule (primary): what operators apply to, a parenthesised expr among them.
      rungs.push({ rule: cur, operators: [...refs.filter((x) => x !== 'expr'), ...(quoted(r.body).includes('(') ? ['( expr )'] : [])], note: null });
      break;
    }
    const opRules = refs.filter((x) => x !== cur && onlyOps(x));
    const ops = [...quoted(r.body), ...opRules.flatMap((x) => quoted(rules.get(x)!.body))];
    const next = refs.find((x) => x !== cur && !opRules.includes(x) && rules.has(x) && !seen.has(x));
    if (ops.length === 0 || !next) throw new Error(`${where}: §5.8.1's rule ${cur} is neither an operator level nor the operand rule`);
    rungs.push({ rule: cur, operators: ops, note: r.comment.trim() || null });
    cur = next;
  }
  if (rungs.length < 2) throw new Error(`${where}: §5.8.1's grammar gives no precedence ladder`);
  return rungs;
}

export function precedenceCaption(rungs: Rung[]): string {
  const ops = rungs.slice(0, -1);
  const na = ops.filter((r) => /non-associative/.test(r.note ?? '')).map((r) => r.rule);
  return `${plural(ops.length, 'operator level', 'operator levels')} from the loosest, ${ops[0]!.rule}, to the tightest, ${ops.at(-1)!.rule}, above the operands of ${rungs.at(-1)!.rule}${na.length > 0 ? `; ${list(na)} does not chain` : ''}.`;
}

// ------------------------------------------------ §5.8.3 static checks

/** The diagnostic codes of §5.8.3's table, in row order, each once. */
export function staticCheckCodes(text: string, where: string): Diagnostic[] {
  const t = sectionTable(text, '5.8.3 ', 0, where);
  const byCode = new Map(loadDiagnostics().map((d) => [d.code, d]));
  const codes = [...new Set(tableRows(t).slice(1).flatMap((r) => [...(r[1] ?? '').matchAll(/\b[A-Z]\d{3}\b/g)].map((m) => m[0])))];
  return codes.map((c) => {
    const d = byCode.get(c);
    if (!d) throw new Error(`${where}: §5.8.3 names ${c}, which is not a diagnostic code`);
    return d;
  });
}

export function staticChecksCaption(text: string, where: string): string {
  const rows = tableRows(sectionTable(text, '5.8.3 ', 0, where)).length - 1;
  const ds = staticCheckCodes(text, where);
  const errors = ds.filter((d) => d.severity === 'error').length;
  return `${plural(rows, 'static check', 'static checks')} raise ${plural(ds.length, 'code', 'codes')}: ${plural(errors, 'error', 'errors')} and ${plural(ds.length - errors, 'warning', 'warnings')}; each code links to its entry on the diagnostics page.`;
}

// ------------------------------------------------ F-S12 extensions

export interface ExtensionTile {
  id: string;
  /** Section numbers the §5.9 table row names. */
  sections: string[];
}

export function extensionTiles(text: string, where: string): ExtensionTile[] {
  const t = sectionTable(text, '5.9 ', 0, where);
  const rows = tableRows(t).slice(1);
  const codes = tableCodes(t).slice(1);
  const fromTable = new Map(rows.map((r, i) => [codes[i]![0]?.[0] ?? r[0]!, [...(r[1] ?? '').matchAll(/§(\d+(?:\.\d+)*)/g)].map((m) => m[1]!)]));
  const enums = loadCatalogEnums().extensions;
  const problems = [
    ...enums.filter((e) => !fromTable.has(e)).map((e) => `the schema's ${e} has no row`),
    ...[...fromTable.keys()].filter((e) => !enums.includes(e)).map((e) => `the row ${e} is not in the schema's enum`),
  ];
  if (problems.length > 0) throw new Error(`${where}: §5.9 extension table and workflow_catalog.schema.json disagree: ${problems.join('; ')}`);
  return enums.map((id) => ({ id, sections: fromTable.get(id)! }));
}

export function extensionsCaption(tiles: ExtensionTile[]): string {
  const secs = new Set(tiles.flatMap((t) => t.sections));
  return `The schema's ${plural(tiles.length, 'extension', 'extensions')} are the table's, and each governs the fields of its own section, ${plural(secs.size, 'section', 'sections')} in all; a workflow that uses those fields must declare it.`;
}

// ------------------------------------------------ F-S13 triggers

export interface TriggerTile {
  kind: string;
  attendance: string;
}

/** Each trigger kind with the default attendance §5.10's `attendance` row gives it. */
export function triggerTiles(text: string, where: string): { tiles: TriggerTile[]; overlap: string[]; overlapDefault: string | null } {
  const t = sectionTable(text, '5.10 ', 0, where);
  const rows = tableRows(t);
  const att = rows.find((r) => r[0] === 'attendance');
  if (!att) throw new Error(`${where}: §5.10's table has no attendance row`);
  const def = /Default:\s*(.+)$/.exec(att[1]!)?.[1];
  if (!def) throw new Error(`${where}: §5.10's attendance row gives no "Default:"`);
  const map = new Map<string, string>();
  for (const part of def.split(/,\s*/)) {
    const m = /^(.+?)\s*→\s*(.+)$/.exec(part.trim());
    if (!m) continue;
    for (const k of m[1]!.split('/')) map.set(k.trim(), m[2]!.trim());
  }
  const e = loadCatalogEnums();
  const missing = e.triggerKinds.filter((k) => !map.has(k));
  if (missing.length > 0) throw new Error(`${where}: §5.10's attendance row gives no default for ${list(missing)}`);
  const sched = rows.find((r) => r[0] === 'schedule')?.[1] ?? '';
  const overlapDefault = e.overlap.find((o) => new RegExp(`${o} \\(default\\)`).test(sched)) ?? null;
  return { tiles: e.triggerKinds.map((kind) => ({ kind, attendance: map.get(kind)! })), overlap: e.overlap, overlapDefault };
}

export function triggersCaption(tiles: TriggerTile[]): string {
  const un = tiles.filter((t) => t.attendance === 'unattended').map((t) => t.kind);
  return `A run starts in one of ${plural(tiles.length, 'way', 'ways')}; ${list(un)} runs are unattended unless a trigger says otherwise, so no one is there to approve a step.`;
}

// ------------------------------------------------ F-S14 recovery loop

/** The rows of §5.12's "Recovery / Outcome" table, each with the codes its outcome names. */
export function recoveryRows(text: string, where: string): { recovery: string; outcome: string; codes: string[] }[] {
  const t = sectionTable(text, '5.12 ', 1, where);
  const rows = tableRows(t);
  if (rows[0]?.[0] !== 'Recovery') throw new Error(`${where}: §5.12's second table is not headed "Recovery"`);
  return rows.slice(1).map((r) => ({ recovery: r[0]!, outcome: r[1]!, codes: [...r[1]!.matchAll(/\b[A-Z]\d{3}\b/g)].map((m) => m[0]) }));
}

/** §5.12's range and default for max_loops ("`max_loops` (integer from 1 to 1000, default 1, ..."). */
export function maxLoopsRange(text: string, where: string): { min: number; max: number; def: number } {
  const prose = sectionBlocks(text, '5.12 ', where).map((b) => toString(b).replace(/\s+/g, ' ')).join(' ');
  const m = /max_loops \(integer from (\d+) to (\d+), default (\d+)/.exec(prose);
  if (!m) throw new Error(`${where}: §5.12 no longer gives max_loops as "integer from N to M, default D"`);
  return { min: Number(m[1]), max: Number(m[2]), def: Number(m[3]) };
}

export function recoveryCaption(rows: { recovery: string; codes: string[] }[]): string {
  const codes = [...new Set(rows.flatMap((r) => r.codes))];
  return `A fired failure mode loops back, runs its on_exhausted handler once the loops run out, or ends the run; ${plural(rows.length, 'branch', 'branches')} in all, ending with ${list(codes)} where no handler takes over.`;
}

// ------------------------------------------------ F-S15 a wait on a timeline

const UNIT_MIN: Record<string, number> = { s: 1 / 60, m: 1, h: 60, d: 1440 };

export function minutes(d: string): number {
  const m = /^(\d+)(ms|s|m|h|d)$/.exec(d.trim());
  if (!m) throw new Error(`spec figures: "${d}" is not a short duration`);
  return m[2] === 'ms' ? Number(m[1]) / 60000 : Number(m[1]) * UNIT_MIN[m[2]!]!;
}

export interface WaitTimeline {
  timeout: string;
  timeoutMin: number;
  interval: string;
  intervalMin: number;
  threshold: number;
  mode: string;
  modes: string[];
  /** Minutes at which a silent source has missed `threshold` probes. */
  lostAt: number;
}

export function waitTimeline(text: string, where: string): WaitTimeline {
  const doc = parse(sectionFence(text, '5.13 ', 0, where).value);
  const step = Array.isArray(doc) ? doc[0] : null;
  if (!isObj(step) || typeof step.timeout !== 'string' || !isObj(step.wait) || !isObj(step.wait.liveness)) throw new Error(`${where}: §5.13's first fence is not a step with timeout and wait.liveness`);
  const l = step.wait.liveness;
  const mode = String(l.mode);
  const modes = loadCatalogEnums().livenessModes;
  if (!modes.includes(mode)) throw new Error(`${where}: §5.13's liveness mode ${mode} is not in the schema`);
  const threshold = typeof l.failure_threshold === 'number' ? l.failure_threshold : 3;
  const timeoutMin = minutes(step.timeout);
  const intervalMin = minutes(String(l.interval));
  if (!(intervalMin * threshold < timeoutMin)) throw new Error(`${where}: §5.13's example breaks its own rule: interval × failure_threshold must be less than the timeout`);
  return { timeout: step.timeout, timeoutMin, interval: String(l.interval), intervalMin, threshold, mode, modes, lostAt: intervalMin * threshold };
}

export function fmtMinutes(m: number): string {
  if (m === 0) return '0';
  if (m % 60 === 0) return `${m / 60}h`;
  if (m > 60) return `${Math.floor(m / 60)}h${String(m % 60).padStart(2, '0')}`;
  return `${m}m`;
}

export function waitCaption(w: WaitTimeline): string {
  return `The example probes every ${w.interval}; a source silent from the start has missed ${w.threshold} probes at ${fmtMinutes(w.lostAt)}, which ends the wait with R406 long before the ${w.timeout} timeout would end it with R401.`;
}

// ------------------------------------------------ F-S16 recovering a silent source

export interface SilentMode {
  code: string;
  action: string;
  goto: string;
  maxLoops: number | null;
  onExhausted: string | null;
}

export function silentSource(text: string, where: string): { wait: string; handler: string; modes: SilentMode[] } {
  const doc = parse(sectionFence(text, '5.13 ', 1, where).value);
  const fms = isObj(doc) && Array.isArray(doc.failure_modes) ? doc.failure_modes : null;
  if (!fms) throw new Error(`${where}: §5.13's second fence has no failure_modes list`);
  const modes = fms.map((fm, i) => {
    if (!isObj(fm) || typeof fm.on_error !== 'string' || typeof fm.action !== 'string' || !isObj(fm.recovery) || typeof fm.recovery.goto_step !== 'string') {
      throw new Error(`${where}: §5.13's failure mode ${i + 1} needs on_error, action and recovery.goto_step`);
    }
    const ex = isObj(fm.recovery.on_exhausted) && typeof fm.recovery.on_exhausted.goto_step === 'string' ? fm.recovery.on_exhausted.goto_step : null;
    return { code: fm.on_error, action: fm.action, goto: fm.recovery.goto_step, maxLoops: typeof fm.recovery.max_loops === 'number' ? fm.recovery.max_loops : null, onExhausted: ex };
  });
  // The paragraph before the fence names the wait's and the handler's store_as.
  const lead = sectionBlocks(text, '5.13 ', where).map((b) => toString(b)).find((p) => /^For a wait stored as/.test(p));
  const m = lead ? /stored as (\S+) and a handler\s+stored as (\S+?):/.exec(lead.replace(/\s+/g, ' ')) : null;
  if (!m) throw new Error(`${where}: §5.13 has no "For a wait stored as … and a handler stored as …:" lead-in`);
  const [wait, handler] = [m[1]!, m[2]!];
  for (const md of modes) {
    if (md.goto !== wait && md.goto !== handler) throw new Error(`${where}: §5.13's failure mode on ${md.code} goes to ${md.goto}, neither the wait nor the handler`);
  }
  return { wait, handler, modes };
}

export function silentCaption(s: { wait: string; handler: string; modes: SilentMode[] }): string {
  const parts = s.modes.map((m) =>
    m.goto === s.wait
      ? `${m.code} loops back to ${s.wait} up to ${plural(m.maxLoops ?? 1, 'time', 'times')}${m.onExhausted ? `, then goes to ${m.onExhausted}` : ''}`
      : `${m.code} escalates to ${m.goto} at once`,
  );
  return `A silent source and a lapsed wait are handled apart: ${list(parts)}.`;
}

// ------------------------------------------------ F-S17 approval

export interface ApprovalPlan {
  plan: string;
  result: string;
  isDefault: boolean;
}

/** §5.14's list of `when_unattended` plans ("`fail` (default) → F502."), checked against the schema enum. */
export function approvalPlans(text: string, where: string): ApprovalPlan[] {
  const lists = sectionBlocks(text, '5.14 ', where).filter((n): n is List => n.type === 'list');
  const items = (lists[0]?.children ?? []).map((i: ListItem) => toString(i).replace(/\s+/g, ' ').trim());
  const plans = items.map((s) => {
    const m = /^(\w+)( \(default\))? → (.+?)\.?$/.exec(s);
    if (!m) throw new Error(`${where}: §5.14's plan "${s}" does not read "plan → result"`);
    return { plan: m[1]!, isDefault: Boolean(m[2]), result: m[3]! };
  });
  const e = loadCatalogEnums().whenUnattended;
  const names = plans.map((p) => p.plan);
  if (e.length !== names.length || e.some((x) => !names.includes(x))) throw new Error(`${where}: §5.14 lists the plans ${list(names)}, the schema ${list(e)}`);
  return plans;
}

/** Whether an approver kind is asked in a run of the given attendance, as §5.14's prose states it. */
export function approverAsked(text: string, where: string): { kind: string; attended: boolean; unattended: boolean }[] {
  const prose = sectionBlocks(text, '5.14 ', where).map((b) => toString(b).replace(/\s+/g, ' ')).join(' ');
  const kinds = loadCatalogEnums().approverKinds;
  const rule: Record<string, boolean> = {};
  if (/A standing_mandate approver needs no one present, so it is asked in an unattended run too/.test(prose)) rule.standing_mandate = true;
  if (/A human approver is not asked in an unattended run/.test(prose)) rule.human = false;
  const missing = kinds.filter((k) => !(k in rule));
  if (missing.length > 0) throw new Error(`${where}: §5.14 no longer says whether ${list(missing)} is asked in an unattended run`);
  return kinds.map((kind) => ({ kind, attended: true, unattended: rule[kind]! }));
}

export function approvalCaption(plans: ApprovalPlan[]): string {
  const d = loadWorldStateSchema().approvalDecisions;
  const def = plans.find((p) => p.isDefault);
  return `The world-state schema records an approval decision as one of ${d.slice(0, -1).join(', ')} or ${d.at(-1)}; when no one can be asked in an unattended run the step follows one of ${plural(plans.length, 'plan', 'plans')}${def ? `, ${def.plan} by default` : ''}.`;
}

// ------------------------------------------------ F-S19 what a delegate binds

export interface DelegateGroup {
  /** The extension a binding needs, or null for the base inputs. */
  extension: string | null;
  rows: SchemaRow[];
}

/** The fields of a §5.9 row's "Fields it governs" that are inputs of a capability. */
function governed(text: string, where: string, ext: string, cap: Capability): string[] {
  const t = sectionTable(text, '5.9 ', 0, where);
  const i = tableCodes(t).findIndex((r) => r[0]?.[0] === ext);
  if (i === -1) throw new Error(`${where}: §5.9 has no ${ext} row`);
  const props = Object.keys((cap.input_schema.properties as Obj) ?? {});
  const out: string[] = [];
  for (const c of tableCodes(t)[i]![1] ?? []) {
    const name = c.startsWith(`${cap.id}.`) ? c.slice(cap.id.length + 1) : c.startsWith('.') ? c.slice(1) : c;
    if (props.includes(name) && !out.includes(name)) out.push(name);
  }
  return out;
}

export function delegateGroups(text: string, where: string): { inputs: DelegateGroup[]; outputs: SchemaRow[] } {
  const cap = loadOntology().byId.get('delegate');
  if (!cap) throw new Error('spec figures: the ontology has no delegate capability');
  const rows = contractRows(cap.input_schema as Obj).filter((r) => r.depth === 0);
  const ext = ['delegation@1', 'identity@1'].map((e) => ({ extension: e, names: governed(text, where, e, cap) }));
  const taken = new Set(ext.flatMap((e) => e.names));
  const inputs: DelegateGroup[] = [
    { extension: null, rows: rows.filter((r) => !taken.has(r.name)) },
    ...ext.map((e) => ({ extension: e.extension, rows: rows.filter((r) => e.names.includes(r.name)) })),
  ];
  if (inputs[1]!.rows.length === 0) throw new Error(`${where}: §5.9's delegation@1 row names no input of delegate`);
  const outputs = contractRows(cap.output_schema as Obj).filter((r) => r.path === 'effective' || r.path.startsWith('effective.'));
  if (outputs.length === 0) throw new Error('spec figures: delegate has no effective output');
  return { inputs, outputs };
}

export function delegateCaption(g: { inputs: DelegateGroup[]; outputs: SchemaRow[] }): string {
  const parts = g.inputs.filter((x) => x.extension).map((x) => `${plural(x.rows.length, 'input needs', 'inputs need')} ${x.extension}`);
  const eff = g.outputs.filter((r) => r.depth === 1).map((r) => r.name);
  return `delegate takes ${plural(g.inputs.reduce((a, x) => a + x.rows.length, 0), 'input', 'inputs')}: ${list(parts)}; the host reports what it used as effective (${list(eff)}).`;
}

// ------------------------------------------------ F-S20 a quorum tally

export interface QuorumExample {
  reviewers: string[];
  pass: string[];
  blocking: string[];
  other: string[];
  minPass: number;
  minFull: number | null;
  freshContext: boolean;
  families: string[];
}

export function quorumExample(text: string, where: string): QuorumExample {
  const doc = parse(sectionFence(text, '5.16 ', 0, where).value);
  const q = Array.isArray(doc) && isObj(doc[0]) && isObj(doc[0].quorum) ? doc[0].quorum : null;
  if (!q) throw new Error(`${where}: §5.16's fence is not a step with a quorum`);
  const arr = (k: string) => (Array.isArray(q[k]) ? (q[k] as unknown[]).map(String) : []);
  const vocab = arr('vocabulary');
  const pass = arr('pass_values');
  const blocking = arr('blocking_values');
  if (typeof q.min_pass !== 'number') throw new Error(`${where}: §5.16's quorum has no min_pass`);
  return {
    reviewers: arr('reviewers'),
    pass,
    blocking,
    other: vocab.filter((v) => !pass.includes(v) && !blocking.includes(v)),
    minPass: q.min_pass,
    minFull: typeof q.min_full === 'number' ? q.min_full : null,
    freshContext: q.require_fresh_context === true,
    families: arr('require_model_families'),
  };
}

export function quorumCaption(q: QuorumExample): string {
  return `${plural(q.reviewers.length, 'reviewer', 'reviewers')} vote; the step passes with ${plural(q.minPass, 'pass', 'passes')}${q.minFull ? `, ${q.minFull} of them full-scope,` : ''} and no ${list(q.blocking)}, while ${list(q.other)} counts for neither side.`;
}

/** The rows of §5.16's field table with the diagnostic codes each description names. */
export function quorumFieldCodes(text: string, where: string): { field: string; codes: string[] }[] {
  const t = sectionTable(text, '5.16 ', 0, where);
  const known = new Set(loadDiagnostics().map((d) => d.code));
  return tableRows(t)
    .slice(1)
    .map((r) => ({ field: r[0]!, codes: [...new Set([...(r[1] ?? '').matchAll(/\b[A-Z]\d{3}\b/g)].map((m) => m[0]))] }))
    .map((r) => {
      const bad = r.codes.filter((c) => !known.has(c));
      if (bad.length > 0) throw new Error(`${where}: §5.16's ${r.field} row names ${list(bad)}, not diagnostic codes`);
      return r;
    });
}

export function quorumFieldsCaption(rows: { field: string; codes: string[] }[]): string {
  const withCodes = rows.filter((r) => r.codes.length > 0);
  const codes = [...new Set(rows.flatMap((r) => r.codes))].sort();
  return `${withCodes.length} of the ${rows.length} quorum fields name the code their violation raises: ${list(codes)}; a missing required field is S304 and a malformed value S303.`;
}

// ------------------------------------------------ F-S21 trust classes

export interface TrustClassBar {
  cls: string;
  weight: number;
  accepted: boolean;
  alwaysAsk: boolean;
}

export function trustClassBars(text: string, where: string): TrustClassBar[] {
  const classes = loadIdentitySchema().trustClasses;
  const w = new Map(loadTrustModel().classWeights.map((x) => [x.cls, x.weight]));
  const problems = [...classes.filter((c) => !w.has(c)).map((c) => `${c} has no weight`), ...[...w.keys()].filter((c) => !classes.includes(c)).map((c) => `weight ${c} is not a trust class`)];
  if (problems.length > 0) throw new Error(`trust model and identity schema disagree: ${problems.join('; ')}`);
  const doc = parse(sectionFence(text, '5.17 ', 0, where).value);
  const ib = Array.isArray(doc) && isObj(doc[0]) && isObj(doc[0].input_bindings) ? doc[0].input_bindings : null;
  if (!ib) throw new Error(`${where}: §5.17's fence is not a step with input_bindings`);
  const arr = (k: string) => (Array.isArray(ib[k]) ? (ib[k] as unknown[]).map(String) : []);
  const acc = arr('accept_trust_classes');
  const ask = arr('always_ask_trust_classes');
  for (const c of [...acc, ...ask]) if (!classes.includes(c)) throw new Error(`${where}: §5.17's fence names ${c}, which is not a trust class`);
  return classes.map((cls) => ({ cls, weight: w.get(cls)!, accepted: acc.includes(cls), alwaysAsk: ask.includes(cls) })).sort((a, b) => b.weight - a.weight);
}

export function trustCaption(bars: TrustClassBar[]): string {
  const acc = bars.filter((b) => b.accepted).map((b) => b.cls);
  const ask = bars.filter((b) => b.alwaysAsk).map((b) => b.cls);
  return `${plural(bars.length, 'trust class', 'trust classes')} by default weight, from ${bars[0]!.cls} (${bars[0]!.weight}) to ${bars.at(-1)!.cls} (${bars.at(-1)!.weight}); the example keeps items from ${list(acc)} and always asks a person about ${list(ask)}.`;
}

// ------------------------------------------------ F-S22 the sender filter

export function senderFilter(text: string, where: string): { input: string; effect: string; drops: boolean }[] {
  const t = sectionTable(text, '5.17 ', 0, where);
  const rows = tableRows(t);
  if (rows[0]?.[0] !== 'Input') throw new Error(`${where}: §5.17's table is not headed "Input"`);
  return rows.slice(1).map((r) => ({ input: r[0]!, effect: r[1]!, drops: /^Kept only if/.test(r[1]!) }));
}

export function senderCaption(rows: { input: string; drops: boolean }[]): string {
  const drop = rows.filter((r) => r.drops).map((r) => r.input);
  const mark = rows.filter((r) => !r.drops).map((r) => r.input);
  return `An item passes ${plural(rows.length, 'check', 'checks')} in turn: ${list(drop)} can drop it, and ${list(mark)} keeps it but may mark it always-ask.`;
}
