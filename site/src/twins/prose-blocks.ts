// The figure blocks of a prose, RFC or skill page's Markdown copy for the
// figures rehype-prose-figures draws from the source's own fences (visual
// spec 6.1): a box diagram, a directory tree and a pattern chain. Each block
// goes directly before the fence it redraws, so the "**Figure: …**" line is
// followed by the data: the fence itself, and for a chain its steps in flow
// order as well. The same tests pick the fences as the plugin does (top-level
// fences only; a pattern fence that a mermaid fence follows, or that names a
// capability the ontology lacks, gets no chain), so the copy has one block per
// numbered figure.
import type { Code, Heading, Root } from 'mdast';
import { toString } from 'mdast-util-to-string';
import { loadOntology } from '../data/ontology';
import { chainCaption, directoryCaption, directoryTree, isBoxDiagram, patternChain } from '../plugins/rehype-prose-figures';
import { code } from './md';

export interface ProseBlockOptions {
  /**
   * The start of a heading whose first box diagram after it the page folds
   * into a <details> as the text version of another figure; that box loses
   * its number, so it gets no block.
   */
  foldBoxAfter?: string;
}

/** The fence languages Shiki renders as plain text: none given, `text` or `plaintext`. */
const PLAIN = new Set([null, undefined, '', 'text', 'plaintext']);

/** The caption of a box diagram's block: the drawing has no caption on the page, only its name. */
export const BOX_CAPTION = 'The source draws this with box characters; the drawing follows as text.';

/** Insertions before each top-level fence of the parsed source `tree` that the page draws as a figure. */
export function proseFigureEdits(tree: Root, options: ProseBlockOptions = {}): { start: number; end: number; text: string }[] {
  const out: { start: number; end: number; text: string }[] = [];
  const o = loadOntology();
  let heading = '';
  let foldArmed = false;
  const kids = tree.children;
  for (let i = 0; i < kids.length; i++) {
    const node = kids[i]!;
    if (node.type === 'heading') {
      heading = toString(node as Heading).replace(/\s+/g, ' ').trim();
      if (options.foldBoxAfter && heading.startsWith(options.foldBoxAfter)) foldArmed = true;
      continue;
    }
    if (node.type !== 'code') continue;
    const fence = node as Code;
    let block: string | null = null;
    if (PLAIN.has(fence.lang) && isBoxDiagram(fence.value)) {
      const dir = directoryTree(fence.value);
      if (dir) block = `**Figure: ${heading ? `Directory tree: ${heading}` : 'Directory tree'}.** ${directoryCaption(dir)}`;
      else if (foldArmed) foldArmed = false;
      else block = `**Figure: ${heading ? `Diagram: ${heading}` : 'Diagram'}.** ${BOX_CAPTION}`;
    } else if (fence.lang === 'yaml') {
      const chain = patternChain(fence.value);
      const next = kids[i + 1];
      const drawnByMermaid = next?.type === 'code' && (next as Code).lang === 'mermaid';
      if (chain && !drawnByMermaid && chain.ids.every((c) => o.byId.has(c))) {
        const steps = chain.ids.map((id, k) => {
          const ins = chain.inputs[k]!.length > 0 ? ` (takes ${chain.inputs[k]!.map(code).join(', ')} from outside the chain)` : '';
          const outp = chain.outputs[k] ? `, passes on ${code(chain.outputs[k]!)}` : '';
          return `${k + 1}. ${code(id)}${ins}${outp}`;
        });
        block = `**Figure: The ${chain.name} pattern as a chain.** ${chainCaption(chain)}\n\n${steps.join('\n')}`;
      }
    }
    if (block === null) continue;
    const start = fence.position!.start.offset! - ((fence.position!.start.column ?? 1) - 1);
    out.push({ start, end: start, text: `${block}\n\n` });
  }
  return out;
}
