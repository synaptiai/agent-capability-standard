// Data for the Standard's figures of the host protocol and its runs (STANDARD
// v1.2): a run between an executor and its host (§2), overlap decisions of a
// schedule trigger (§5.10.2), the run record each end leaves (§5.19.8) and
// the runtime fixtures by script entry (§10.5). Each reads the Standard's own
// section and the data it describes (schemas/host_protocol.schema.json, the
// trigger vectors, the runtime fixtures and their schema), and throws when
// the two disagree. The captions are written here, so the page and its
// Markdown copy match.
import type { List, ListItem, RootContent, Table } from 'mdast';
import { toString } from 'mdast-util-to-string';
import { loadCatalogEnums, RUNTIME_FIXTURE_DIR } from '../data/spec-sources';
import { readRepoFile, trackedIn } from './repo';
import { sectionBlocks, sectionTable, tableCodes, tableRows } from './md-sections';
import { andList, plural } from './words';

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);

export const HOST_PROTOCOL_SCHEMA = 'schemas/host_protocol.schema.json';
export const OVERLAP_VECTORS = 'tests/conformance/triggers/overlap.json';
export const FIXTURE_SCHEMA = `${RUNTIME_FIXTURE_DIR}/schema/fixture.schema.json`;

/** The `$defs` names a `$defs` entry's `oneOf` refers to, in order. */
function oneOfNames(doc: unknown, def: string, file: string): string[] {
  const defs = isObj(doc) && isObj(doc.$defs) ? doc.$defs : null;
  const d = defs?.[def];
  if (!isObj(d) || !Array.isArray(d.oneOf)) throw new Error(`${file}: $defs.${def} has no oneOf`);
  return d.oneOf.map((x) => {
    const ref = isObj(x) && typeof x.$ref === 'string' ? x.$ref : '';
    const m = /^#\/\$defs\/(.+)$/.exec(ref);
    if (!m) throw new Error(`${file}: $defs.${def}.oneOf holds ${JSON.stringify(x)}, not a $defs reference`);
    return m[1]!;
  });
}

/** The first inline code of each item of a list. */
function itemCodes(list: List): string[] {
  return list.children.map((item: ListItem) => {
    let found = '';
    const walk = (n: { type: string; value?: string; children?: unknown[] }) => {
      if (found) return;
      if (n.type === 'inlineCode' && typeof n.value === 'string') found = n.value;
      for (const c of (n.children ?? []) as (typeof n)[]) walk(c);
    };
    walk(item as never);
    return found;
  });
}

const lists = (blocks: RootContent[]): List[] => blocks.filter((b): b is List => b.type === 'list');

// ------------------------------------------------ §2 a run between an executor and its host

/** The terms of §2 the figure draws. */
export const RUN_TERMS = ['Executor', 'Host', 'Run', 'Action', 'Audit record'] as const;

export interface HostLoop {
  /** The actions that ask the host for something, in the schema's order. */
  requests: string[];
  /** The action that only lets time pass (its row: "none: the host gives the run the time"). */
  waits: string[];
  /** The terminal actions (their row: the host does "none"). */
  terminal: string[];
  /** The responses, in the schema's order. */
  responses: string[];
}

/**
 * The actions and responses of `schemas/host_protocol.schema.json`, sorted
 * by §5.19.1's action table into requests, waits and terminal actions; §2's
 * table must define each of RUN_TERMS, and the table's actions and the
 * responses it names must be the schema's.
 */
export function hostLoop(text: string, where: string): HostLoop {
  // §2 may hold its terms in more than one table.
  const terms = sectionBlocks(text, '2. ', where)
    .filter((n): n is Table => n.type === 'table')
    .flatMap((t) => tableRows(t).slice(1).map((r) => r[0]!));
  const missing = RUN_TERMS.filter((t) => !terms.includes(t));
  if (missing.length > 0) throw new Error(`${where}: §2 defines no ${andList(missing)}`);
  const doc: unknown = JSON.parse(readRepoFile(HOST_PROTOCOL_SCHEMA));
  const actions = oneOfNames(doc, 'action', HOST_PROTOCOL_SCHEMA);
  const responses = oneOfNames(doc, 'response', HOST_PROTOCOL_SCHEMA);
  const t = sectionTable(text, '5.19.1 ', 0, where);
  const rows = tableRows(t);
  const codes = tableCodes(t);
  if (rows[0]?.join('|') !== 'Action|The host|Responses') throw new Error(`${where}: §5.19.1's first table is not headed Action, The host, Responses`);
  // A response is named by its kind (`Output`); the cell also names its members (`value`).
  const byKind = new Map(rows.slice(1).map((r, i) => [codes[i + 1]![0]![0] ?? r[0]!, { host: r[1]!, answers: r[2]!, named: codes[i + 1]![2]!.filter((c) => /^[A-Z][a-z]\w*$/.test(c)) }]));
  const problems = [
    ...actions.filter((a) => !byKind.has(a)).map((a) => `the schema's action ${a} has no row`),
    ...[...byKind.keys()].filter((a) => !actions.includes(a)).map((a) => `the row ${a} is not an action of the schema`),
    ...[...byKind.values()].flatMap((v) => v.named.filter((n) => !responses.includes(n)).map((n) => `${n} is not a response of the schema`)),
    ...responses.filter((r) => ![...byKind.values()].some((v) => v.named.includes(r))).map((r) => `the schema's response ${r} answers no action`),
  ];
  if (problems.length > 0) throw new Error(`${where}: §5.19.1's action table and ${HOST_PROTOCOL_SCHEMA} disagree: ${problems.join('; ')}`);
  const terminal = actions.filter((a) => byKind.get(a)!.host.startsWith('none'));
  const waits = actions.filter((a) => !terminal.includes(a) && byKind.get(a)!.named.length === 0);
  return { requests: actions.filter((a) => !terminal.includes(a) && !waits.includes(a)), waits, terminal, responses };
}

export function hostLoopCaption(l: HostLoop): string {
  return `A run is a loop: the executor issues one action at a time, one of ${plural(l.requests.length, 'request', 'requests')} or a ${l.waits.join(' or a ')}; its host performs it and answers with one of ${plural(l.responses.length, 'response', 'responses')}, or gives the run the time; ${l.terminal.join(' or ')} ends the run with its action records, the audit records of its steps.`;
}

/** The caption of §5.19.1's action table, enriched with the codes its answers lead to. */
export function protocolActionsCaption(l: HostLoop): string {
  const all = l.requests.length + l.waits.length + l.terminal.length;
  return `${plural(all, 'action', 'actions')} in all: ${l.requests.length} ask the host for something and take ${l.responses.length} kinds of response between them, ${andList(l.waits)} only lets time pass, and ${andList(l.terminal)} end the run; a tile marks the code an answer leads to.`;
}

// ------------------------------------------------ §5.10.2 overlap decisions

export interface OverlapEvent {
  event: 'fire' | 'end';
  outcome: string;
}

export interface OverlapRow {
  policy: string;
  isDefault: boolean;
  /** The vector case drawn. */
  name: string;
  events: OverlapEvent[];
}

/** How each overlap decision reads, by event and outcome. */
export function overlapWords(e: OverlapEvent): string {
  if (e.event === 'end') return e.outcome === 'start' ? 'the waiting run starts' : 'nothing starts';
  return { start: 'a run starts', skipped: 'skipped', buffered: 'waits' }[e.outcome] ?? e.outcome;
}

/**
 * For each `overlap` policy of the catalog schema, the first case of the
 * overlap vectors (§10.3) that runs it on fire times and run ends only, with
 * two fire times or more. §5.10.2's overlap list must name the schema's
 * policies and mark the vectors' default.
 */
export function overlapRows(text: string, where: string): OverlapRow[] {
  const policies = loadCatalogEnums().overlap;
  const list = lists(sectionBlocks(text, '5.10.2 ', where)).find((l) => itemCodes(l).some((c) => policies.includes(c)));
  if (!list) throw new Error(`${where}: §5.10.2 has no list of overlap policies`);
  const named = itemCodes(list);
  if (named.join() !== policies.join()) throw new Error(`${where}: §5.10.2's overlap list names ${named.join(', ')}, the schema ${policies.join(', ')}`);
  const def = list.children.flatMap((item, i) => (toString(item).includes('(default)') ? [named[i]!] : []));
  if (def.length !== 1) throw new Error(`${where}: §5.10.2's overlap list marks ${def.length} defaults, expected one`);
  const doc: unknown = JSON.parse(readRepoFile(OVERLAP_VECTORS));
  const desc = isObj(doc) && typeof doc.description === 'string' ? doc.description : '';
  if (!desc.includes(`null is the default, ${def[0]}`)) throw new Error(`${OVERLAP_VECTORS}: its description does not make ${def[0]} the default, as §5.10.2 does`);
  const cases = isObj(doc) && isObj(doc.cases) ? doc.cases : {};
  return policies.map((policy) => {
    const hit = Object.entries(cases).find(([, c]) => {
      if (!isObj(c) || c.overlap !== policy || !Array.isArray(c.events) || !Array.isArray(c.expect)) return false;
      const ev = c.events as unknown[];
      return ev.every((e) => e === 'fire' || e === 'end') && ev.filter((e) => e === 'fire').length >= 2 && c.expect.length === ev.length;
    });
    if (!hit) throw new Error(`${OVERLAP_VECTORS}: no case runs ${policy} on two fire times or more`);
    const c = hit[1] as { events: ('fire' | 'end')[]; expect: string[] };
    return { policy, isDefault: policy === def[0], name: hit[0], events: c.events.map((event, i) => ({ event, outcome: c.expect[i]! })) };
  });
}

export function overlapCaption(rows: OverlapRow[]): string {
  const second = (r: OverlapRow) => r.events.filter((e) => e.event === 'fire')[1]!.outcome;
  const says = (r: OverlapRow) => {
    const p = `${r.policy}${r.isDefault ? ' (the default)' : ''}`;
    const o = second(r);
    return o === 'skipped' ? `${p} starts none` : o === 'buffered' ? `${p} holds one until it ends` : `${p} starts each`;
  };
  return `Each row is a case of the overlap vectors (§10.3); for a fire time while a run the trigger started is in progress, ${andList(rows.map(says))}.`;
}

// ------------------------------------------------ §5.19.8 the run record each end leaves

export interface RunEnd {
  fixture: string;
  /** The terminal action's kind. */
  kind: string;
  outcome: string | null;
  code: string | null;
  status: string;
  /** details.records, when the fixture pins it. */
  records: number | null;
}

/** The run record's status for a terminal action, as §5.19.8's status row gives it. */
function statusOf(kind: string, outcome: string | null, code: string | null): string {
  if (kind === 'Completed') return outcome === 'deferred' ? 'planned' : 'executed';
  return code === 'R408' ? 'cancelled' : 'failed';
}

/**
 * For each status of §5.19.8's status row, the first runtime fixture (by
 * name) whose pinned run record has it, with the end it is derived from.
 * Every fixture's pinned status must be the one the row gives its end.
 */
export function runRecordRows(text: string, where: string): RunEnd[] {
  const t = sectionTable(text, '5.19.8 ', 0, where);
  const row = tableRows(t).find((r) => r[0] === 'status');
  if (!row) throw new Error(`${where}: §5.19.8's table has no status row`);
  // "executed for Completed, except planned when its outcome is deferred ...; cancelled for Failed ...".
  const order = [...row[1]!.matchAll(/\b([a-z]+) (?:for|when) /g)].map((m) => m[1]!);
  if (order.length === 0) throw new Error(`${where}: §5.19.8's status row names no status`);
  const all = trackedIn(RUNTIME_FIXTURE_DIR, '.json').flatMap((file): RunEnd[] => {
    const f: unknown = JSON.parse(readRepoFile(file));
    if (!isObj(f) || !isObj(f.run_record) || typeof f.run_record.status !== 'string' || !isObj(f.end)) return [];
    const kind = String(f.end.kind);
    const outcome = typeof f.end.outcome === 'string' ? f.end.outcome : null;
    const code = typeof f.end.code === 'string' ? f.end.code : null;
    const details = isObj(f.run_record.details) ? f.run_record.details : {};
    const status = f.run_record.status;
    if (status !== statusOf(kind, outcome, code)) throw new Error(`${file}: its run record is ${status}, but §5.19.8 gives ${statusOf(kind, outcome, code)} for its end`);
    return [{ fixture: file.slice(RUNTIME_FIXTURE_DIR.length + 1, -'.json'.length), kind, outcome, code, status, records: typeof details.records === 'number' ? details.records : null }];
  });
  const out = order.flatMap((s) => all.filter((r) => r.status === s).slice(0, 1));
  const unseen = order.filter((s) => !out.some((r) => r.status === s));
  if (unseen.length > 0) throw new Error(`${RUNTIME_FIXTURE_DIR}: no fixture pins a run record that is ${andList(unseen)}`);
  return out;
}

export function runRecordCaption(rows: RunEnd[]): string {
  const none = rows.find((r) => r.records === 0);
  return `The runtime fixtures pin a run record for each way a run can end: ${andList(rows.map((r) => `${r.status} after ${endWords(r)}`))}${none ? `; a run that ${none.status} before any step wrote a record still leaves one` : ''}.`;
}

/** "0 action records", "1 action record". */
export function recordsWords(n: number): string {
  return plural(n, 'action record', 'action records');
}

/** "Completed (deferred)", "Failed R408". */
export function endWords(r: RunEnd): string {
  return r.code ? `${r.kind} ${r.code}` : `${r.kind} (${r.outcome})`;
}

// ------------------------------------------------ §10.5 runtime fixtures by script entry

export interface EntryCount {
  /** The entry's key, as §10.5 writes it ("expect", "tick", ...). */
  key: string;
  /** Fixtures with at least one entry of this kind. */
  count: number;
}

/**
 * The script entries §10.5 lists (each item's first code, `{"key": ...}`),
 * which must be the entries `fixture.schema.json` allows, and for each the
 * number of runtime fixtures whose script has one.
 */
export function fixtureEntries(text: string, where: string): { entries: EntryCount[]; fixtures: number } {
  const list = lists(sectionBlocks(text, '10.5 ', where)).find((l) => itemCodes(l)[0]?.startsWith('{"expect"'));
  if (!list) throw new Error(`${where}: §10.5 has no list of script entries`);
  const keys = itemCodes(list).map((c) => /^\{"(\w+)"/.exec(c)?.[1] ?? '');
  const schema: unknown = JSON.parse(readRepoFile(FIXTURE_SCHEMA));
  const defs = isObj(schema) && isObj(schema.$defs) ? schema.$defs : {};
  const allowed = oneOfNames(schema, 'entry', FIXTURE_SCHEMA).map((d) => {
    const req = isObj(defs[d]) ? (defs[d] as Obj).required : null;
    return Array.isArray(req) && typeof req[0] === 'string' ? req[0] : '';
  });
  if (keys.join() !== allowed.join()) throw new Error(`${where}: §10.5 lists the entries ${keys.join(', ')}, ${FIXTURE_SCHEMA} allows ${allowed.join(', ')}`);
  const files = trackedIn(RUNTIME_FIXTURE_DIR, '.json');
  const scripts = files.map((file) => {
    const f: unknown = JSON.parse(readRepoFile(file));
    if (!isObj(f) || !Array.isArray(f.script)) throw new Error(`${file}: no script`);
    return f.script as unknown[];
  });
  return { entries: keys.map((key) => ({ key, count: scripts.filter((s) => s.some((e) => isObj(e) && key in e)).length })), fixtures: files.length };
}

/** What a fixture with each kind of entry does, for the caption. */
const ENTRY_WORDS: Readonly<Record<string, string>> = {
  tick: 'give the run a time with no response',
  wake_at: "check the run's wake-up time",
  cancel: 'cancel the run',
  resume: 'resume a deferred run',
};

export function fixtureEntriesCaption(f: { entries: EntryCount[]; fixtures: number }): string {
  const [first, ...rest] = f.entries;
  return `Of the ${plural(f.fixtures, 'runtime fixture', 'runtime fixtures')}, ${first!.count} expect actions, and ${andList(rest.map((e) => `${e.count} ${ENTRY_WORDS[e.key] ?? `use ${e.key}`}`))}.`;
}
