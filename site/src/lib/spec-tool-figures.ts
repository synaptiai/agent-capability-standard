// Data for the figures of §5.18.3 (Classification) of the current Standard:
// the classification table with the capabilities it names drawn as tiles,
// how a layer classifies a call of a shell-like tool, and what runs inside
// and outside an operating-system boundary. Each reads the section's own
// table, list and sentences, and throws when the text no longer says what
// the figure draws. The captions are written here, so the page and its
// Markdown copy match.
import type { List, Table } from 'mdast';
import { toString } from 'mdast-util-to-string';
import { loadOntology } from '../data/ontology';
import { sectionBlocks, sectionTable, tableCodes, tableRows } from './md-sections';
import { andList, plural } from './words';

const SECTION = '5.18.3 ';

/** The figures' names; the page and the Markdown copy add ", from §5.18.3". */
export const CLASSIFICATION_TITLE = 'Classification by effect';
export const SHELL_TITLE = 'How a call of a shell-like tool is classified';
export const BOUNDARY_TITLE = 'Inside and outside an operating-system boundary';
const squash = (s: string) => s.replace(/\s+/g, ' ').trim();

/** The section's prose, whitespace collapsed, for the phrase checks. */
function sectionProse(text: string, where: string): string {
  return squash(
    sectionBlocks(text, SECTION, where)
      .filter((b) => b.type === 'paragraph')
      .map((b) => toString(b))
      .join(' '),
  );
}

/** Throws unless §5.18.3 states each phrase (whitespace collapsed, code spans as plain text). */
function expectPhrases(prose: string, phrases: readonly string[], figure: string, where: string): void {
  for (const p of phrases) {
    if (!prose.includes(p)) throw new Error(`${where}: §5.18.3 no longer says "${p}", which the figure "${figure}" draws`);
  }
}

// ---------------------------------------------- the classification table

export interface ClassRow {
  /** The "What the call does" cell. */
  effect: string;
  /** The capabilities its Capability cell names, in order; none for a cell that negates one ("Not a `send`"). */
  caps: string[];
}

/**
 * The first table of §5.18.3 ("What the call does | Capability"), each row
 * with the capability ids its Capability cell names as code spans. A cell
 * that starts "Not" names a capability only to rule it out, so it gets none.
 */
export function classificationRows(text: string, where: string): ClassRow[] {
  const t = sectionTable(text, SECTION, 0, where);
  const rows = tableRows(t);
  if (rows[0]?.join('|') !== 'What the call does|Capability') throw new Error(`${where}: §5.18.3's first table is not "What the call does | Capability"`);
  const ids = new Set(loadOntology().capabilities.map((c) => c.id));
  const codes = tableCodes(t);
  const out = rows.slice(1).map((r, i) => ({
    effect: r[0]!,
    caps: /^Not\b/.test(r[1]!) ? [] : [...new Set(codes[i + 1]![1]!.filter((c) => ids.has(c)))],
  }));
  if (!out.some((r) => r.caps.length > 0)) throw new Error(`${where}: §5.18.3's first table names no capability`);
  return out;
}

export function classificationCaption(rows: ClassRow[]): string {
  const named = rows.filter((r) => r.caps.length > 0);
  const caps = new Set(named.flatMap((r) => r.caps));
  const none = rows.length - named.length;
  return `${plural(named.length, 'row names', 'rows name')} ${plural(caps.size, 'capability', 'capabilities')}, each drawn as a tile that links to its page${none > 0 ? `; ${none === 1 ? 'the other row names' : `the other ${none} rows name`} no single capability` : ''}.`;
}

// ---------------------------------------------- a call of a shell-like tool

export interface ShellFlow {
  /** The cases the section lists in which the boundary is unverified for a call. */
  unverified: number;
}

const SHELL_PHRASES = [
  "A layer MUST give every call of a shell-like tool the tool's worst case unless its conformance statement declares an operating-system boundary for the tool (§10.4)",
  "before the call runs, the layer has verified, by code (§5.18.10) from the effective host configuration and the call's arguments, that the boundary holds for that call",
  'Any classification other than the worst case relaxes the call',
  "A layer leaves out send only where every host on the boundary's allowlist is one that every destination policy in force allows",
] as const;

/**
 * How §5.18.3 classifies a call of a shell-like tool: two checks, each of
 * which gives the tool's worst case when it does not pass, read from the
 * "Shell-like tools." paragraph, the list of cases in which the boundary is
 * unverified (its last case: a failed verification is the worst case, not
 * R407) and the paragraph on relaxing.
 */
export function shellFlow(text: string, where: string): ShellFlow {
  expectPhrases(sectionProse(text, where), SHELL_PHRASES, SHELL_TITLE, where);
  const lists = sectionBlocks(text, SECTION, where).filter((b): b is List => b.type === 'list');
  const list = lists[0];
  if (!list || lists.length !== 1) throw new Error(`${where}: §5.18.3 has ${lists.length} lists, expected one (the cases in which the boundary is unverified)`);
  const items = list.children.map((li) => squash(toString(li)));
  if (!items[0]!.startsWith('a source is one the layer can neither read nor supply itself')) throw new Error(`${where}: §5.18.3's list no longer starts with the unreadable source case`);
  if (!items.at(-1)!.includes('the call gets the worst case, not R407')) throw new Error(`${where}: §5.18.3's list no longer ends with "the call gets the worst case, not R407"`);
  return { unverified: items.length };
}

/**
 * The flow's words, shared by the page and the Markdown copy: code in
 * backticks, section references as §n (the page links them).
 */
export function shellSteps(f: ShellFlow): { start: string; checks: { question: string; no: string[] }[]; end: { lead: string; text: string } } {
  return {
    start: 'A call of a shell-like tool',
    checks: [
      { question: "Does the layer's conformance statement declare an operating-system boundary for the tool (§10.4)?", no: ["No: the tool's worst case"] },
      {
        question: "Before the call runs, has the layer verified by code (§5.18.10), from the effective host configuration and the call's arguments, that the boundary holds for this call?",
        no: [`No, as in each of the ${f.unverified} cases listed above: the tool's worst case`, 'A verification that fails or cannot be completed is the last of them: the worst case, not `R407`'],
      },
    ],
    end: {
      lead: 'Yes:',
      text: "the layer may classify the call from its arguments, and any classification other than the worst case relaxes the call. The layer leaves out `send` only when every destination policy in force allows every host on the boundary's allowlist.",
    },
  };
}

export function shellFlowCaption(f: ShellFlow): string {
  return (
    `A call of a shell-like tool gets the tool's worst case unless both checks pass. ` +
    `The boundary is unverified in each of the ${plural(f.unverified, 'case', 'cases')} listed above, the last of which is a verification that fails or cannot be completed: that call gets the worst case, not R407.`
  );
}

// ---------------------------------------------- inside and outside the boundary

export interface Boundary {
  /** The properties of the boundary's table, in order. */
  properties: string[];
}

const BOUNDARY_PHRASES = [
  "every process that runs the call's program, whether the call starts it or it was already running (an interpreter, a REPL, a kernel), runs, as the operating system enforces it, with each of these properties",
  "The layer's own decision code (a hook, a callback) and a tool server the host starts outside the boundary are not confined by it",
] as const;

/**
 * The operating-system boundary of §5.18.3: the properties of its table
 * ("Property | What holds"), checked with the sentences that say what runs
 * inside it and what runs outside, and with the one route out the table
 * allows (the boundary's network proxy).
 */
export function boundary(text: string, where: string): Boundary {
  expectPhrases(sectionProse(text, where), BOUNDARY_PHRASES, BOUNDARY_TITLE, where);
  const t: Table = sectionTable(text, SECTION, 1, where);
  const rows = tableRows(t);
  if (rows[0]?.join('|') !== 'Property|What holds') throw new Error(`${where}: §5.18.3's second table is not "Property | What holds"`);
  const route = rows.find((r) => r[0] === 'No route outside the boundary');
  if (!route || !squash(route[1]!).includes("except the boundary's own network proxy, which carries only the connections the Network property allows")) {
    throw new Error(`${where}: §5.18.3's boundary table no longer makes the network proxy the one route out`);
  }
  if (!rows.some((r) => r[0] === 'Network' && /allowlist/.test(r[1]!))) throw new Error(`${where}: §5.18.3's boundary table has no Network property with an allowlist`);
  return { properties: rows.slice(1).map((r) => r[0]!) };
}

export function boundaryCaption(b: Boundary): string {
  return (
    `Every process of the call runs inside the boundary with the ${plural(b.properties.length, 'property', 'properties')} of the table (${andList(b.properties.map((p) => p.toLowerCase()))}); ` +
    `the layer's decision code and a tool server the host starts outside are not confined by it, and the boundary's network proxy is the one process outside that a process inside may use, for connections to hosts on the allowlist.`
  );
}

/**
 * The words of the boundary's panel, shared by the page and the Markdown
 * copy: what runs inside, what runs outside, and the one process outside
 * that a process inside may use.
 */
export function boundarySides(): { inside: string[]; insideNote: string; outside: string[]; outsideNote: string; route: string } {
  return {
    inside: ["Every process that runs the call's program, whether the call starts it or it was already running (an interpreter, a REPL, a kernel)"],
    insideNote: 'Each runs with every property of the table',
    outside: [
      "The layer's own decision code (a hook, a callback), not confined by the boundary",
      'A tool server the host starts outside the boundary, not confined by it',
      "The boundary's own network proxy",
    ],
    outsideNote: 'The statement names the decision code and the tool servers, and no file such code runs or reads as configuration is writable from inside the boundary.',
    route: "The one process outside that a process inside may use: the boundary's network proxy, for connections to hosts on the allowlist",
  };
}
