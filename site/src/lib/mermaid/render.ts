// Draws a laid-out flowchart as pixel-style SVG and wraps it in a figure with
// its accessible name, a one-sentence caption and a text version.
// - Everything is a <rect> on even pixels: node outlines step at the corners
//   instead of curving, links are runs of rects, dotted links are 2px squares
//   with 4px gaps, and arrowheads are three-step chevrons. No path, no
//   stroke-dasharray, no colour value: the stylesheet colours the rects
//   through the classes below with the theme tokens.
// - The SVG is role="img", named by the visible title and described by the
//   text version, which lists every group, box and link in words.
import type { Element, ElementContent, Properties } from 'hast';
import { toRects } from '../../pixel/grid';
import type { Layout, PlacedEdge, PlacedNode, Point } from './layout';
import type { Font } from './layout';
import type { Diagram, Shape } from './parse';
import { describeDiagram, type TextVersion } from './text';

type Child = ElementContent;

// Properties are written as plain values (numbers for coordinates, a string
// for an id list); hast-util-to-html writes each as its attribute.
function h(tagName: string, properties: Record<string, string | number | string[]>, children: Child[] = []): Element {
  return { type: 'element', tagName, properties: properties as Properties, children };
}

function text(value: string): Child {
  return { type: 'text', value };
}

interface R {
  x: number;
  y: number;
  w: number;
  h: number;
}

function rect(r: R, cls: string): Element {
  return h('rect', { x: r.x, y: r.y, width: r.w, height: r.h, className: [cls] });
}

/** Inset in 2px cells of row `r` (of `rows`) for a shape whose corners step inward. */
function rowInset(shape: Shape, r: number, rows: number): number {
  const fromEdge = Math.min(r, rows - 1 - r);
  const steps = { rect: 0, round: 1, stadium: 2, subroutine: 0, cylinder: 1, circle: 3, hexagon: 4, decision: 0 }[shape];
  if (shape === 'decision') return Math.floor(Math.abs(r - (rows - 1) / 2));
  return Math.max(0, steps - fromEdge);
}

/** A node's outline ('#') and fill ('o') as rows of 2px cells, then as rects. */
export function shapeRects(shape: Shape, w: number, h: number): { line: R[]; fill: R[] } {
  const cols = w / 2;
  const rows = h / 2;
  const grid: string[] = [];
  for (let r = 0; r < rows; r++) {
    const inset = Math.min(rowInset(shape, r, rows), Math.floor((cols - 2) / 2));
    const span = cols - 2 * inset;
    const edgeRow = r === 0 || r === rows - 1;
    const next = r === 0 ? null : rowInset(shape, r - 1, rows);
    const after = r === rows - 1 ? null : rowInset(shape, r + 1, rows);
    let middle = 'o'.repeat(Math.max(0, span - 2));
    // A row is solid outline where it is the top or bottom, or where the rows
    // above or below are narrower (the steps of a stepped corner need a top).
    if (edgeRow) middle = '#'.repeat(Math.max(0, span - 2));
    else if (next !== null && next > inset) {
      const cut = next - inset;
      middle = '#'.repeat(cut - 1) + middle.slice(cut - 1, middle.length - (cut - 1)) + '#'.repeat(cut - 1);
    } else if (after !== null && after > inset) {
      const cut = after - inset;
      middle = '#'.repeat(cut - 1) + middle.slice(cut - 1, middle.length - (cut - 1)) + '#'.repeat(cut - 1);
    }
    let row = '.'.repeat(inset) + '#' + middle + '#' + '.'.repeat(inset);
    if (shape === 'subroutine' && !edgeRow) row = row.slice(0, 3) + '#' + row.slice(4, cols - 4) + '#' + row.slice(cols - 3);
    if (shape === 'cylinder' && r === 3) row = '.'.repeat(inset) + '#'.repeat(span) + '.'.repeat(inset);
    grid.push(row);
  }
  const rects = toRects({ id: 'node', w: cols, h: rows, rows: grid });
  const scale = (x: { x: number; y: number; w: number; h: number }): R => ({ x: x.x * 2, y: x.y * 2, w: x.w * 2, h: x.h * 2 });
  return {
    line: rects.filter((r) => r.paint === 'fg').map(scale),
    fill: rects.filter((r) => r.paint === 'bg').map(scale),
  };
}

const THICK = 4;
const THIN = 2;

type Heading = 'up' | 'down' | 'left' | 'right';

function heading(a: Point, b: Point): Heading {
  if (a.x === b.x) return b.y > a.y ? 'down' : 'up';
  return b.x > a.x ? 'right' : 'left';
}

/** The rect that draws the straight run from a to b, `t` pixels thick. */
function segment(a: Point, b: Point, t: number): R {
  const lo = t === THIN ? 0 : t / 2;
  const hi = t === THIN ? 2 : t / 2;
  if (a.x === b.x) return { x: a.x - lo, y: Math.min(a.y, b.y) - lo, w: lo + hi, h: Math.abs(a.y - b.y) + lo + hi };
  return { x: Math.min(a.x, b.x) - lo, y: a.y - lo, w: Math.abs(a.x - b.x) + lo + hi, h: lo + hi };
}

/** 2px squares every 6px (2 on, 4 off) along a run. */
function dots(a: Point, b: Point): R[] {
  const out: R[] = [];
  const len = Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
  const dx = Math.sign(b.x - a.x);
  const dy = Math.sign(b.y - a.y);
  for (let d = 0; d <= len - 2; d += 6) out.push({ x: a.x + dx * d - (dx < 0 ? 2 : 0), y: a.y + dy * d - (dy < 0 ? 2 : 0), w: 2, h: 2 });
  return out;
}

/** A three-step chevron whose tip ends at `tip`, pointing along `dir`, for a line `t` thick. */
function chevron(tip: Point, dir: Heading, t: number): R[] {
  const lo = t === THIN ? 0 : t / 2;
  const out: R[] = [];
  for (let step = 0; step < 3; step++) {
    const half = 2 * (step + 1); // how far the step reaches past the line on each side
    const depth = 2 * (step + 1); // how far back from the tip this step sits
    const across = t + 2 * half;
    switch (dir) {
      case 'down':
        out.push({ x: tip.x - lo - half, y: tip.y - depth, w: across, h: 2 });
        break;
      case 'up':
        out.push({ x: tip.x - lo - half, y: tip.y + depth - 2, w: across, h: 2 });
        break;
      case 'right':
        out.push({ x: tip.x - depth, y: tip.y - lo - half, w: 2, h: across });
        break;
      case 'left':
        out.push({ x: tip.x + depth - 2, y: tip.y - lo - half, w: 2, h: across });
        break;
    }
  }
  return out;
}

const ARROW = 6;

export function edgeRects(e: PlacedEdge): R[] {
  const t = e.style === 'thick' ? THICK : THIN;
  const pts = e.points.map((p) => ({ ...p }));
  const out: R[] = [];
  const n = pts.length;
  let dir: Heading | null = null;
  if (e.arrow && n >= 2) {
    dir = heading(pts[n - 2]!, pts[n - 1]!);
    const end = pts[n - 1]!;
    const back = { up: [0, ARROW], down: [0, -ARROW], left: [ARROW, 0], right: [-ARROW, 0] }[dir];
    pts[n - 1] = { x: end.x + back[0]!, y: end.y + back[1]! };
  }
  for (let i = 0; i + 1 < pts.length; i++) {
    const a = pts[i]!;
    const b = pts[i + 1]!;
    if (e.style === 'dotted') out.push(...dots(a, b));
    else out.push(segment(a, b, t));
  }
  if (dir) out.push(...chevron(e.points[n - 1]!, dir, t));
  return out;
}

function textLines(f: Font, lines: string[], cx: number, top: number, cls: string, anchor: 'middle' | 'start' = 'middle'): Element[] {
  return lines.map((l, i) =>
    h('text', { x: cx, y: top + i * f.lineH + Math.round(f.lineH / 2 + f.size * 0.35), className: [cls], textAnchor: anchor }, [text(l)]),
  );
}

function nodeElements(f: Font, n: PlacedNode): Element {
  const { line, fill } = shapeRects(n.shape, n.w, n.h);
  const off = (r: R): R => ({ ...r, x: r.x + n.x, y: r.y + n.y });
  const top = n.y + Math.round((n.h - n.lines.length * f.lineH) / 2) + (n.shape === 'cylinder' ? 3 : 0);
  return h('g', { className: ['mmd-node'], dataNode: n.id }, [
    ...fill.map((r) => rect(off(r), 'mmd-fill')),
    ...line.map((r) => rect(off(r), 'mmd-line')),
    ...textLines(f, n.lines, n.x + n.w / 2, top, 'mmd-label'),
  ]);
}

export function drawSvg(layout: Layout, ids: { title: string; text: string }, variant: 'wide' | 'narrow'): Element {
  const groups = layout.groups.map((g) => {
    const frame = shapeRects('rect', g.w, g.h);
    const off = (r: R): R => ({ ...r, x: r.x + g.x, y: r.y + g.y });
    return h('g', { className: ['mmd-group'] }, [
      ...frame.fill.map((r) => rect(off(r), 'mmd-group-fill')),
      ...frame.line.map((r) => rect(off(r), 'mmd-group-line')),
    ]);
  });
  // Group names go on a patch of the group's fill, drawn after the links, so
  // a link that passes under a name does not run through its letters.
  const groupNames = layout.groups.map((g) => {
    const f = layout.font;
    const patch = { x: g.x + 8, y: g.y + 6, w: Math.ceil((Math.max(...g.lines.map((l) => l.length)) * f.charW + 8) / 2) * 2, h: g.lines.length * f.lineH + 4 };
    return h('g', { className: ['mmd-group-name'] }, [
      rect(patch, 'mmd-group-fill'),
      ...textLines(f, g.lines, g.x + 12, g.y + 8, 'mmd-group-label', 'start'),
    ]);
  });
  const edges = layout.edges.map((e) =>
    h('g', { className: ['mmd-edge', `mmd-edge--${e.style}`] }, edgeRects(e).map((r) => rect(r, 'mmd-stroke'))),
  );
  const labels = layout.edges
    .filter((e) => e.label)
    .map((e) => {
      const l = e.label!;
      return h('g', { className: ['mmd-edge-label'] }, [rect(l, 'mmd-label-bg'), ...textLines(layout.font, l.lines, l.x + l.w / 2, l.y + 2, 'mmd-label')]);
    });
  return h(
    'svg',
    {
      className: ['fig-mermaid__svg', `fig-mermaid__svg--${variant}`],
      viewBox: `0 0 ${layout.width} ${layout.height}`,
      width: layout.width,
      height: layout.height,
      role: 'img',
      ariaLabelledBy: ids.title,
      ariaDescribedBy: ids.text,
      shapeRendering: 'crispEdges',
      fontSize: layout.font.size,
      focusable: 'false',
    },
    [...groups, ...edges, ...groupNames, ...layout.nodes.map((n) => nodeElements(layout.font, n)), ...labels],
  );
}

function textVersion(tv: TextVersion, id: string): Element {
  const items: Child[] = tv.items.map((i) => h('li', {}, [text(i)]));
  return h('details', { className: ['fig-mermaid__text'] }, [
    h('summary', {}, [text('Text version')]),
    h('ul', { id }, items),
  ]);
}

/** Width classes the stylesheet knows: the wide drawing shows once its box is at least this wide. */
export const FIT_STEPS = [350, 400, 450, 500, 550, 600, 650, 700] as const;

export function fitStep(width: number): number {
  const step = FIT_STEPS.find((s) => s >= width);
  if (step === undefined) throw new Error(`mermaid: a drawing ${width}px wide has no fit step`);
  return step;
}

/**
 * The whole figure. `narrow` is the phone layout, drawn top to bottom, when
 * the authored layout is wider than the phone budget.
 */
export function figureElement(d: Diagram, wide: Layout, narrow: Layout | null, opts: { id: string; fallbackTitle: string }): Element {
  const ids = { title: `${opts.id}-title`, text: `${opts.id}-text` };
  const tv = describeDiagram(d, opts.fallbackTitle);
  const svgs = [drawSvg(wide, ids, 'wide')];
  if (narrow) svgs.push(drawSvg(narrow, ids, 'narrow'));
  const draw = h('div', { className: ['fig-mermaid__draw', ...(narrow ? [`fig-mermaid__draw--fit-${fitStep(wide.width)}`] : [])] }, svgs);
  return h('figure', { className: ['fig', 'fig-mermaid'], ariaLabelledBy: ids.title }, [
    h('p', { className: ['fig-mermaid__eyebrow'], ariaHidden: 'true' }, [text('Diagram')]),
    h('p', { className: ['fig-mermaid__title'], id: ids.title }, [text(tv.title)]),
    draw,
    h('figcaption', { className: ['fig-mermaid__caption'] }, [text(tv.caption)]),
    textVersion(tv, ids.text),
  ]);
}
