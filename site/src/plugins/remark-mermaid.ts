// Draws each ```mermaid fence as a pixel-style figure at build time (see
// src/lib/mermaid/). The fence is replaced in the page; the Markdown copy keeps
// it and adds the text version (src/twins/md.ts). A fence the site cannot
// draw (syntax outside the supported subset, or a drawing too wide for the
// page or a phone) fails the build with its file and line.
import type { Code, Heading, Root } from 'mdast';
import { toString } from 'mdast-util-to-string';
import { visit } from 'unist-util-visit';
import type { VFile } from 'vfile';
import { FONT_NARROW, layoutDiagram, NARROW_BUDGET, WIDE_BUDGET, WRAP_NARROW, type Layout } from '../lib/mermaid/layout';
import { MermaidError, parseMermaid, type Diagram, type Direction } from '../lib/mermaid/parse';
import { figureElement } from '../lib/mermaid/render';
import { failWith, lineOf, sourceOf } from './source';

const PLUGIN = 'remark-mermaid';

export interface MermaidFence {
  node: Code;
  /** Text of the nearest heading before the fence, or "" when there is none. */
  heading: string;
}

/** Every mermaid fence in document order, with the heading it sits under. */
export function mermaidFences(tree: Root): MermaidFence[] {
  const out: MermaidFence[] = [];
  let heading = '';
  visit(tree, (node) => {
    if (node.type === 'heading') heading = toString(node as Heading);
    else if (node.type === 'code' && (node as Code).lang === 'mermaid') out.push({ node: node as Code, heading });
  });
  return out;
}

/** Line of the fence body's line `n` (1-based) in the rendered text. */
function bodyLine(node: Code, n: number): number {
  return (node.position?.start.line ?? 0) + n;
}

/** Both layouts for a diagram, or the reason it cannot be drawn. */
export async function layoutsFor(d: Diagram): Promise<{ wide: Layout; narrow: Layout | null } | string> {
  // The page layout uses long lines; a diagram too wide for them gets shorter ones.
  let wide = await layoutDiagram(d);
  if (wide.width > WIDE_BUDGET) wide = await layoutDiagram(d, { wrapAt: WRAP_NARROW });
  if (wide.width > WIDE_BUDGET) {
    return `the drawing is ${wide.width}px wide, more than the ${WIDE_BUDGET}px a page has; draw it top to bottom (flowchart TB) or shorten the labels`;
  }
  if (wide.width <= NARROW_BUDGET) return { wide, narrow: null };
  // A phone gets the diagram top to bottom with shorter lines; when that is
  // still too wide (several boxes side by side), the authored direction with
  // shorter lines is tried too.
  const tries = [...new Set<Direction>(['TB', d.direction])];
  let narrow: Layout | null = null;
  for (const direction of tries) {
    const l = await layoutDiagram(d, { direction, wrapAt: WRAP_NARROW, fontSize: FONT_NARROW, compact: true });
    if (l.width <= NARROW_BUDGET) {
      narrow = l;
      break;
    }
    narrow = narrow && narrow.width <= l.width ? narrow : l;
  }
  if (narrow!.width > NARROW_BUDGET) {
    return `with shorter lines for a phone, the diagram is still ${narrow!.width}px wide, more than ${NARROW_BUDGET}px; put fewer boxes side by side or shorten the labels`;
  }
  return { wide, narrow };
}

export default function remarkMermaid() {
  return async (tree: Root, file: VFile): Promise<void> => {
    const fences = mermaidFences(tree);
    if (fences.length === 0) return;
    const src = sourceOf(file, PLUGIN);
    const problems: string[] = [];
    const parsed: { fence: MermaidFence; diagram: Diagram; line: number }[] = [];
    for (const fence of fences) {
      const at = (n: number) => lineOf(src, { position: { start: { line: bodyLine(fence.node, n) } } });
      try {
        parsed.push({ fence, diagram: parseMermaid(fence.node.value), line: bodyLine(fence.node, 0) + src.lineOffset });
      } catch (e) {
        if (e instanceof MermaidError) problems.push(`${at(e.line)}: ${e.message}`);
        else throw e;
      }
    }
    failWith(PLUGIN, problems);
    for (const { fence, diagram, line } of parsed) {
      const layouts = await layoutsFor(diagram);
      if (typeof layouts === 'string') {
        problems.push(`${lineOf(src, fence.node)}: ${layouts}`);
        continue;
      }
      const figure = figureElement(diagram, layouts.wide, layouts.narrow, { id: `mermaid-l${line}`, fallbackTitle: fence.heading });
      // An mdast node that mdast-util-to-hast turns into exactly this element.
      const node = fence.node as unknown as { type: string; data: unknown; value?: string; lang?: string | null; meta?: string | null };
      node.type = 'paragraph';
      delete node.value;
      delete node.lang;
      delete node.meta;
      (node as unknown as { children: unknown[] }).children = [];
      node.data = { hName: figure.tagName, hProperties: figure.properties, hChildren: figure.children };
    }
    failWith(PLUGIN, problems);
  };
}
