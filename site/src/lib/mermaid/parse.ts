// A parser for the part of Mermaid's flowchart syntax the site draws: nodes
// with a shape and a label, links (solid, thick, dotted; with or without an
// arrowhead; with or without a label), subgraphs, and the directions TB, TD and
// LR. Anything else throws a MermaidError with the line it found it on, so an
// author learns at build time that the site cannot draw it, rather than seeing
// a picture that differs from GitHub's.
//
// Line numbers are 1-based within the fence body; the remark plugin turns them
// into lines of the source file.

export type Direction = 'TB' | 'LR';
export type Shape = 'rect' | 'round' | 'stadium' | 'subroutine' | 'cylinder' | 'circle' | 'decision' | 'hexagon';
export type LinkStyle = 'solid' | 'thick' | 'dotted';

export interface MermaidNode {
  id: string;
  label: string;
  shape: Shape;
  /** The subgraph the node first appears in, or null at the top level. */
  group: string | null;
  line: number;
}

export interface MermaidEdge {
  from: string;
  to: string;
  label: string | null;
  style: LinkStyle;
  /** False for a link with no arrowhead (`---`). */
  arrow: boolean;
  line: number;
}

export interface MermaidGroup {
  id: string;
  label: string;
  parent: string | null;
  line: number;
}

export interface Diagram {
  direction: Direction;
  /** From the `title:` frontmatter or an `accTitle:` line. */
  title: string | null;
  /** From an `accDescr:` line. */
  description: string | null;
  nodes: MermaidNode[];
  edges: MermaidEdge[];
  groups: MermaidGroup[];
}

export class MermaidError extends Error {
  constructor(
    readonly line: number,
    message: string,
  ) {
    super(message);
    this.name = 'MermaidError';
  }
}

/** Openers in the order they must be tried (longest first), with their closer and shape. */
const SHAPES: readonly [string, string, Shape][] = [
  ['([', '])', 'stadium'],
  ['[[', ']]', 'subroutine'],
  ['[(', ')]', 'cylinder'],
  ['((', '))', 'circle'],
  ['{{', '}}', 'hexagon'],
  ['[', ']', 'rect'],
  ['(', ')', 'round'],
  ['{', '}', 'decision'],
];

/** Node syntax Mermaid has and the site does not draw. */
const UNSUPPORTED_SHAPES: readonly [RegExp, string][] = [
  [/^\(\(\(/, 'the double-circle shape (((…)))'],
  [/^\[\//, 'the parallelogram and trapezoid shapes [/…/]'],
  [/^\[\\/, 'the parallelogram and trapezoid shapes [\\…\\]'],
  [/^>/, 'the asymmetric shape >…]'],
  [/^@\{/, 'the @{ shape: … } syntax'],
  [/^:::/, 'classes (:::)'],
];

const KEYWORDS: readonly [RegExp, string][] = [
  [/^classDef\b/, 'classDef'],
  [/^class\b/, 'class'],
  [/^style\b/, 'style'],
  [/^linkStyle\b/, 'linkStyle'],
  [/^click\b/, 'click (figures hold no links)'],
  [/^direction\b/, 'direction inside a subgraph'],
  [/^accDescr\s*\{/, 'a multi-line accDescr { … }'],
];

const ID = /^[A-Za-z0-9_]+/;

/** Links: inline-label forms first, then plain ones. Each yields [style, arrow, label]. */
const LINKS: readonly [RegExp, LinkStyle, ((m: RegExpExecArray) => boolean), number | null][] = [
  [/^--\s+(.+?)\s+(-{2,}>|-{3,})/, 'solid', (m) => m[2]!.endsWith('>'), 1],
  [/^==\s+(.+?)\s+(={2,}>|={3,})/, 'thick', (m) => m[2]!.endsWith('>'), 1],
  [/^-\.\s+(.+?)\s+(\.-+>|\.-+)(?![\w.])/, 'dotted', (m) => m[2]!.endsWith('>'), 1],
  [/^-\.+->/, 'dotted', () => true, null],
  [/^-\.+-/, 'dotted', () => false, null],
  [/^-{2,}>/, 'solid', () => true, null],
  [/^-{3,}/, 'solid', () => false, null],
  [/^={2,}>/, 'thick', () => true, null],
  [/^={3,}/, 'thick', () => false, null],
];

const UNSUPPORTED_LINKS: readonly [RegExp, string][] = [
  [/^<[-=.]/, 'two-headed links (<-->)'],
  [/^(-{2,}|={2,}|-\.+-)[ox](?=[\s|]|$)/, 'circle and cross link ends (--o, --x)'],
  [/^~~~/, 'invisible links (~~~)'],
  [/^@/, 'link ids (e1@-->)'],
];

function unquote(s: string): string {
  const t = s.trim();
  return t.length >= 2 && t.startsWith('"') && t.endsWith('"') ? t.slice(1, -1) : t;
}

function checkLabel(label: string, line: number): string {
  if (/<[A-Za-z/]/.test(label)) throw new MermaidError(line, `HTML in a label is not supported: ${label}`);
  if (/#\w+;/.test(label)) throw new MermaidError(line, `entity codes in a label are not supported: ${label}`);
  if (label.startsWith('`')) throw new MermaidError(line, `Markdown strings in a label are not supported: ${label}`);
  const t = label.trim();
  if (t === '') throw new MermaidError(line, 'a label is empty');
  return t.replace(/\s+/g, ' ');
}

interface Cursor {
  text: string;
  pos: number;
  line: number;
}

function skipSpace(c: Cursor): void {
  while (c.pos < c.text.length && /\s/.test(c.text[c.pos]!)) c.pos++;
}

function rest(c: Cursor): string {
  return c.text.slice(c.pos);
}

/** One node reference: an id, with an optional shape and label. */
function readNode(c: Cursor): { id: string; label: string | null; shape: Shape | null } {
  skipSpace(c);
  const m = ID.exec(rest(c));
  if (!m) throw new MermaidError(c.line, `expected a node id at "${rest(c).slice(0, 30)}"`);
  const id = m[0];
  if (id === 'end' || id === 'subgraph') throw new MermaidError(c.line, `"${id}" cannot be a node id`);
  c.pos += id.length;
  const after = rest(c);
  for (const [re, what] of UNSUPPORTED_SHAPES) {
    if (re.test(after)) throw new MermaidError(c.line, `${what} is not supported`);
  }
  for (const [open, close, shape] of SHAPES) {
    if (!after.startsWith(open)) continue;
    let body = after.slice(open.length);
    let label: string;
    if (body.trimStart().startsWith('"')) {
      const start = body.indexOf('"');
      const end = body.indexOf('"', start + 1);
      if (end === -1) throw new MermaidError(c.line, `unclosed quote in the label of ${id}`);
      label = body.slice(start + 1, end);
      body = body.slice(end + 1);
      const lead = /^\s*/.exec(body)![0].length;
      if (!body.slice(lead).startsWith(close)) throw new MermaidError(c.line, `expected "${close}" after the label of ${id}`);
      c.pos += open.length + start + 1 + label.length + 1 + lead + close.length;
    } else {
      const end = body.indexOf(close);
      if (end === -1) throw new MermaidError(c.line, `expected "${close}" to close the label of ${id}`);
      label = body.slice(0, end);
      if (/[[\](){}"|]/.test(label)) {
        throw new MermaidError(c.line, `the label of ${id} has a bracket or quote; put the label in double quotes`);
      }
      c.pos += open.length + end + close.length;
    }
    return { id, label: checkLabel(label, c.line), shape };
  }
  return { id, label: null, shape: null };
}

function readNodeGroup(c: Cursor): ReturnType<typeof readNode>[] {
  const out = [readNode(c)];
  for (;;) {
    skipSpace(c);
    if (!rest(c).startsWith('&')) return out;
    c.pos += 1;
    out.push(readNode(c));
  }
}

function readLink(c: Cursor): { style: LinkStyle; arrow: boolean; label: string | null } | null {
  skipSpace(c);
  const r = rest(c);
  if (r === '' || r === ';') return null;
  for (const [re, what] of UNSUPPORTED_LINKS) {
    if (re.test(r)) throw new MermaidError(c.line, `${what} are not supported`);
  }
  for (const [re, style, arrowOf, labelGroup] of LINKS) {
    const m = re.exec(r);
    if (!m) continue;
    c.pos += m[0].length;
    let label = labelGroup === null ? null : checkLabel(unquote(m[labelGroup]!), c.line);
    const pipe = /^\|([^|]*)\|/.exec(rest(c));
    if (pipe) {
      if (label !== null) throw new MermaidError(c.line, 'a link has two labels');
      label = checkLabel(unquote(pipe[1]!), c.line);
      c.pos += pipe[0].length;
    }
    return { style, arrow: arrowOf(m), label };
  }
  throw new MermaidError(c.line, `expected a link (-->, ---, -.->, ==>) at "${r.slice(0, 30)}"`);
}

/** Parse a Mermaid flowchart. Throws MermaidError on anything outside the supported subset. */
export function parseMermaid(source: string): Diagram {
  const lines = source.replace(/\r\n?/g, '\n').split('\n');
  let i = 0;
  let title: string | null = null;
  let description: string | null = null;

  const skipBlank = () => {
    while (i < lines.length && (lines[i]!.trim() === '' || /^\s*%%(?!\{)/.test(lines[i]!))) i++;
  };

  // Frontmatter: only a title.
  skipBlank();
  if (lines[i]?.trim() === '---') {
    const open = i + 1;
    i++;
    while (i < lines.length && lines[i]!.trim() !== '---') {
      const l = lines[i]!;
      const m = /^title:\s*(.+)$/.exec(l.trim());
      if (m) title = checkLabel(unquote(m[1]!), i + 1);
      else if (l.trim() !== '') throw new MermaidError(i + 1, `only "title:" is supported in the frontmatter, found "${l.trim()}"`);
      i++;
    }
    if (i >= lines.length) throw new MermaidError(open, 'the frontmatter is not closed with ---');
    i++;
  }

  skipBlank();
  if (i >= lines.length) throw new MermaidError(1, 'the diagram is empty');
  if (/^\s*%%\{/.test(lines[i]!)) throw new MermaidError(i + 1, 'directives (%%{ … }%%) are not supported');
  const header = /^\s*(flowchart|graph)\s+(\w+)\s*;?\s*$/.exec(lines[i]!);
  if (!header) {
    throw new MermaidError(i + 1, `only flowcharts are supported: the diagram must start with "flowchart TB", "flowchart TD" or "flowchart LR", found "${lines[i]!.trim()}"`);
  }
  const dir = header[2]!.toUpperCase();
  if (dir !== 'TB' && dir !== 'TD' && dir !== 'LR') {
    throw new MermaidError(i + 1, `direction ${header[2]} is not supported; use TB, TD or LR`);
  }
  const direction: Direction = dir === 'LR' ? 'LR' : 'TB';
  i++;

  const nodes = new Map<string, MermaidNode>();
  const edges: MermaidEdge[] = [];
  const groups: MermaidGroup[] = [];
  const stack: MermaidGroup[] = [];

  const defined = new Map<string, number>();

  const touch = (ref: ReturnType<typeof readNode>, line: number) => {
    const group = stack.at(-1)?.id ?? null;
    if (groups.some((g) => g.id === ref.id)) throw new MermaidError(line, `${ref.id} is a subgraph id, and links to subgraphs are not supported`);
    let known = nodes.get(ref.id);
    if (!known) {
      known = { id: ref.id, label: ref.id, shape: 'rect', group, line };
      nodes.set(ref.id, known);
    } else if (group !== null && known.group !== group) {
      throw new MermaidError(line, `${ref.id} first appears outside subgraph ${group} (line ${known.line}); GitHub and the site could place it differently`);
    }
    if (ref.label === null) return;
    const first = defined.get(ref.id);
    if (first !== undefined && (known.label !== ref.label || known.shape !== ref.shape)) {
      throw new MermaidError(line, `${ref.id} is defined twice with different labels or shapes (first on line ${first})`);
    }
    defined.set(ref.id, first ?? line);
    known.label = ref.label;
    known.shape = ref.shape!;
  };

  for (; i < lines.length; i++) {
    const line = i + 1;
    const raw = lines[i]!;
    const text = raw.trim().replace(/;$/, '').trim();
    if (text === '' || /^%%(?!\{)/.test(text)) continue;
    if (text.startsWith('%%{')) throw new MermaidError(line, 'directives (%%{ … }%%) are not supported');
    for (const [re, what] of KEYWORDS) {
      if (re.test(text)) throw new MermaidError(line, `${what} is not supported`);
    }
    let m = /^accTitle\s*:\s*(.+)$/.exec(text);
    if (m) {
      title = checkLabel(m[1]!, line);
      continue;
    }
    m = /^accDescr\s*:\s*(.+)$/.exec(text);
    if (m) {
      description = checkLabel(m[1]!, line);
      continue;
    }
    if (text === 'end') {
      if (stack.length === 0) throw new MermaidError(line, '"end" with no open subgraph');
      stack.pop();
      continue;
    }
    m = /^subgraph\s+(.+)$/.exec(text);
    if (m) {
      const spec = m[1]!.trim();
      const withLabel = /^([A-Za-z0-9_]+)\s*\[\s*(.+?)\s*\]$/.exec(spec);
      let id: string;
      let label: string;
      if (withLabel) {
        id = withLabel[1]!;
        label = checkLabel(unquote(withLabel[2]!), line);
      } else if (/^"[^"]+"$/.test(spec) || /^[A-Za-z0-9_ ]+$/.test(spec)) {
        label = checkLabel(unquote(spec), line);
        id = label;
      } else {
        throw new MermaidError(line, `cannot read the subgraph "${spec}"; write subgraph id [Label]`);
      }
      if (groups.some((g) => g.id === id) || nodes.has(id)) throw new MermaidError(line, `the id ${id} is used twice`);
      const g = { id, label, parent: stack.at(-1)?.id ?? null, line };
      groups.push(g);
      stack.push(g);
      continue;
    }
    // A statement: node groups joined by links.
    const c: Cursor = { text, pos: 0, line };
    let left = readNodeGroup(c);
    for (const n of left) touch(n, line);
    for (;;) {
      const link = readLink(c);
      if (link === null) break;
      const right = readNodeGroup(c);
      for (const n of right) touch(n, line);
      for (const a of left) {
        for (const b of right) edges.push({ from: a.id, to: b.id, label: link.label, style: link.style, arrow: link.arrow, line });
      }
      left = right;
    }
    skipSpace(c);
    if (rest(c) !== '') throw new MermaidError(line, `unexpected text "${rest(c).slice(0, 30)}"`);
  }
  if (stack.length > 0) throw new MermaidError(stack.at(-1)!.line, `subgraph ${stack.at(-1)!.id} is not closed with "end"`);
  if (nodes.size === 0) throw new MermaidError(1, 'the diagram has no nodes');
  return { direction, title, description, nodes: [...nodes.values()], edges, groups };
}
