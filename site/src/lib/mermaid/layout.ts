// Lays out a parsed flowchart with ELK's layered algorithm (elkjs, which runs
// in Node; no browser is needed at build time) and snaps the result to the
// pixel grid: every coordinate and size is an even number of pixels, and every
// edge is a chain of horizontal and vertical segments.
//
// Labels are set in the site's mono font, so their width is known without a
// browser: Atkinson Hyperlegible Mono advances 0.632em per character
// (8.848px at 14px, measured in Chromium with canvas measureText on
// 2026-11-12). The fallback mono fonts are narrower, so a label never
// outgrows its box.
import ELK from 'elkjs/lib/elk.bundled.js';
import type { Diagram, Direction, LinkStyle, Shape } from './parse';

/** Characters advance this many ems in the mono font. */
export const CHAR_EM = 0.632;
/** Label sizes: 14px on the page, 12px (the floor for figure text) in the phone layout. */
export const FONT_WIDE = 14;
export const FONT_NARROW = 12;

export interface Font {
  size: number;
  lineH: number;
  charW: number;
}

export function font(size: number): Font {
  return { size, lineH: size + 4, charW: CHAR_EM * size };
}
/** Widest drawing on a desktop page: the 46rem column less the figure's padding and border. */
export const WIDE_BUDGET = 684;
/** Widest drawing at a 360px viewport: 328px of content less 8px padding and 2px border each side. */
export const NARROW_BUDGET = 308;

/** Characters per label line, for the authored layout and the phone layout. */
export const WRAP_WIDE = 22;
export const WRAP_NARROW = 10;

/** Space inside boxes and between them: the page layout, and the tighter phone layout. */
const SPACING = {
  roomy: { padX: 12, padY: 8, nodeNode: 24, layers: 36, edgeNode: 16, edgeEdge: 12, edgeLayers: 16, minW: 48, groupPad: 16 },
  compact: { padX: 6, padY: 6, nodeNode: 12, layers: 24, edgeNode: 8, edgeEdge: 8, edgeLayers: 8, minW: 40, groupPad: 8 },
} as const;
const BORDER = 2;

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Point {
  x: number;
  y: number;
}

export interface PlacedNode extends Box {
  id: string;
  shape: Shape;
  lines: string[];
  /** The layer of the capability the box names, or null. */
  layer: string | null;
  /**
   * The symbol chip drawn left of the label of a box that names a
   * capability, in the page layout only: the phone layout has no room for
   * it, and there the outline's colour comes with the capability's name.
   */
  chip: (Box & { symbol: string }) | null;
}

export interface PlacedGroup extends Box {
  id: string;
  lines: string[];
}

export interface PlacedEdge {
  from: string;
  to: string;
  style: LinkStyle;
  arrow: boolean;
  points: Point[];
  label: (Box & { lines: string[] }) | null;
}

export interface Layout {
  direction: Direction;
  font: Font;
  width: number;
  height: number;
  nodes: PlacedNode[];
  groups: PlacedGroup[];
  edges: PlacedEdge[];
}

/**
 * A word longer than a line is broken after "(", ",", "/" or "-" where it
 * can be. An identifier such as recovery_point or max_attempts is never
 * split: a word with no such place gets a line of its own.
 */
function pieces(word: string, max: number): string[] {
  if (word.length <= max) return [word];
  const out: string[] = [];
  let rest = word;
  while (rest.length > max) {
    let cut = -1;
    for (let i = Math.min(max, rest.length - 1); i > 0; i--) {
      if ('(,/-'.includes(rest[i - 1]!)) {
        cut = i;
        break;
      }
    }
    if (cut === -1) break;
    out.push(rest.slice(0, cut));
    rest = rest.slice(cut);
  }
  out.push(rest);
  return out;
}

/**
 * Greedy word wrap. A long word is broken after punctuation (see pieces);
 * a word with no such place gets a line of its own.
 */
export function wrap(text: string, max: number): string[] {
  const lines: string[] = [];
  let cur = '';
  for (const word of text.split(' ').flatMap((w) => pieces(w, max))) {
    if (cur === '') cur = word;
    else if (cur.length + 1 + word.length <= max) cur += ` ${word}`;
    else {
      lines.push(cur);
      cur = word;
    }
  }
  if (cur !== '') lines.push(cur);
  return lines;
}

const even = (v: number): number => Math.round(v / 2) * 2;
const up4 = (v: number): number => Math.ceil(v / 4) * 4;

/** A capability chip: the two-letter symbol in a box one text line tall, and the gap after it. */
export function chipSize(f: Font): { w: number; h: number; gap: number } {
  return { w: even(2 * f.charW + 12), h: even(f.lineH + 4), gap: 8 };
}

/** Extra width each side for shapes whose ends step inward. */
export function shapeInset(shape: Shape): number {
  return { rect: 0, round: 2, stadium: 4, subroutine: 6, cylinder: 0, circle: 6, decision: 8, hexagon: 8 }[shape];
}

function textWidth(lines: string[], f: Font): number {
  return Math.max(...lines.map((l) => l.length)) * f.charW;
}

export interface LayoutOptions {
  direction?: Direction;
  wrapAt?: number;
  fontSize?: number;
  /** Tighter padding and spacing, for the phone layout. */
  compact?: boolean;
}

interface ElkNode {
  id: string;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  children?: ElkNode[];
  layoutOptions?: Record<string, string>;
  edges?: ElkEdge[];
}

interface ElkEdge {
  id: string;
  sources: string[];
  targets: string[];
  labels?: { text: string; width: number; height: number; x?: number; y?: number; layoutOptions?: Record<string, string> }[];
  sections?: { startPoint: Point; endPoint: Point; bendPoints?: Point[] }[];
}

const elk = new ELK();

/** Remove repeated and collinear points, and split any diagonal step into two straight ones. */
export function orthogonal(points: Point[]): Point[] {
  const out: Point[] = [];
  for (const p of points) {
    const last = out.at(-1);
    if (last && last.x === p.x && last.y === p.y) continue;
    if (last && last.x !== p.x && last.y !== p.y) out.push({ x: p.x, y: last.y });
    out.push(p);
  }
  return out.filter((p, i) => {
    const a = out[i - 1];
    const b = out[i + 1];
    return !(a && b && ((a.x === p.x && p.x === b.x) || (a.y === p.y && p.y === b.y)));
  });
}

export async function layoutDiagram(d: Diagram, options: LayoutOptions = {}): Promise<Layout> {
  const direction = options.direction ?? d.direction;
  const wrapAt = options.wrapAt ?? WRAP_WIDE;
  const f = font(options.fontSize ?? FONT_WIDE);
  const sp = SPACING[options.compact ? 'compact' : 'roomy'];
  const nodeLines = new Map(d.nodes.map((n) => [n.id, wrap(n.label, wrapAt)]));
  const groupLines = new Map(d.groups.map((g) => [g.id, wrap(g.label, wrapAt)]));

  const elkNodes = new Map<string, ElkNode>();
  for (const n of d.nodes) {
    const lines = nodeLines.get(n.id)!;
    // A decision box's sides slant one 2px step per 2px row, so its top and
    // bottom text lines sit half the text's height in from the widest point.
    const inset = n.shape === 'decision' ? Math.max(shapeInset(n.shape), Math.ceil((lines.length * f.lineH) / 2)) : shapeInset(n.shape);
    const chip = n.capability && !options.compact ? chipSize(f) : null;
    const content = textWidth(lines, f) + (chip ? chip.w + chip.gap : 0);
    const w = up4(Math.max(sp.minW, content + 2 * (sp.padX + BORDER + inset)));
    const h0 = up4(Math.max(lines.length * f.lineH, chip ? chip.h : 0) + 2 * (sp.padY + BORDER) + (n.shape === 'cylinder' ? 6 : 0));
    // Left to right, a box with several edges on one side is tall enough to
    // give each its own 16px of that side, so edges that fan out from it
    // (or into it) leave and arrive apart and can be traced.
    const fan = direction === 'LR' ? Math.max(d.edges.filter((e) => e.from === n.id).length, d.edges.filter((e) => e.to === n.id).length) : 0;
    const h = fan > 2 ? Math.max(h0, up4(fan * 16 + 8)) : h0;
    elkNodes.set(n.id, { id: n.id, width: w, height: h });
  }
  for (const g of d.groups) {
    const head = groupLines.get(g.id)!.length * f.lineH + 8;
    elkNodes.set(g.id, {
      id: g.id,
      children: [],
      layoutOptions: { 'elk.padding': `[top=${up4(head + sp.groupPad)},left=${sp.groupPad},bottom=${sp.groupPad},right=${sp.groupPad}]` },
    });
  }
  const root: ElkNode = {
    id: '__root',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': direction === 'LR' ? 'RIGHT' : 'DOWN',
      'elk.edgeRouting': 'ORTHOGONAL',
      'elk.hierarchyHandling': 'INCLUDE_CHILDREN',
      'elk.json.shapeCoords': 'ROOT',
      'elk.json.edgeCoords': 'ROOT',
      'elk.padding': '[top=4,left=4,bottom=4,right=4]',
      'elk.spacing.nodeNode': String(sp.nodeNode),
      'elk.layered.spacing.nodeNodeBetweenLayers': String(sp.layers),
      'elk.spacing.edgeNode': String(sp.edgeNode),
      'elk.spacing.edgeEdge': String(sp.edgeEdge),
      'elk.spacing.edgeLabel': '4',
      'elk.layered.spacing.edgeNodeBetweenLayers': String(sp.edgeLayers),
      'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
      'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
    },
    children: [],
    edges: [],
  };
  const parentOf = (group: string | null) => (group === null ? root : elkNodes.get(group)!);
  for (const g of d.groups) parentOf(g.parent).children!.push(elkNodes.get(g.id)!);
  for (const n of d.nodes) parentOf(n.group).children!.push(elkNodes.get(n.id)!);
  d.edges.forEach((e, i) => {
    const edge: ElkEdge = { id: `e${i}`, sources: [e.from], targets: [e.to] };
    if (e.label) {
      const lines = wrap(e.label, wrapAt);
      edge.labels = [{ layoutOptions: { 'elk.edgeLabels.inline': 'true' }, text: e.label, width: up4(textWidth(lines, f) + 8), height: lines.length * f.lineH + 4 }];
    }
    root.edges!.push(edge);
  });

  const out = (await elk.layout(root as never)) as unknown as ElkNode;

  const placed = new Map<string, Box>();
  const walk = (n: ElkNode) => {
    for (const c of n.children ?? []) {
      placed.set(c.id, { x: even(c.x!), y: even(c.y!), w: even(c.width!), h: even(c.height!) });
      walk(c);
    }
  };
  walk(out);

  const edges: PlacedEdge[] = (out.edges ?? []).map((e, i) => {
    const src = d.edges[i]!;
    const s = e.sections?.[0];
    if (!s || (e.sections?.length ?? 0) > 1) throw new Error(`mermaid: ELK gave edge ${src.from} -> ${src.to} ${e.sections?.length ?? 0} sections`);
    const raw = [s.startPoint, ...(s.bendPoints ?? []), s.endPoint].map((p) => ({ x: even(p.x), y: even(p.y) }));
    const l = e.labels?.[0];
    return {
      from: src.from,
      to: src.to,
      style: src.style,
      arrow: src.arrow,
      points: orthogonal(raw),
      label:
        l && src.label
          ? { x: even(l.x!), y: even(l.y!), w: even(l.width), h: even(l.height), lines: wrap(src.label, wrapAt) }
          : null,
    };
  });

  return {
    direction,
    font: f,
    width: even(out.width!),
    height: even(out.height!),
    nodes: d.nodes.map((n) => {
      const box = placed.get(n.id)!;
      const lines = nodeLines.get(n.id)!;
      let chip: PlacedNode['chip'] = null;
      if (n.capability && !options.compact) {
        // The chip and the text are centred together as one row.
        const c = chipSize(f);
        const left = even(box.x + (box.w - (c.w + c.gap + textWidth(lines, f))) / 2);
        chip = { x: left, y: even(box.y + (box.h - c.h) / 2), w: c.w, h: c.h, symbol: n.capability.symbol };
      }
      return { id: n.id, shape: n.shape, lines, layer: n.capability?.layer ?? null, chip, ...box };
    }),
    groups: d.groups.map((g) => ({ id: g.id, lines: groupLines.get(g.id)!, ...placed.get(g.id)! })),
    edges,
  };
}
