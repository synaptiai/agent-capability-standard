// The Markdown copy of a page keeps each mermaid fence, which GitHub and other
// Markdown readers draw, and adds the figure's text version after it, so a
// reader of the copy gets the same words as a reader of the page.
import type { Root } from 'mdast';
import { mermaidFences } from '../../plugins/remark-mermaid';
import { parseMermaid } from './parse';
import { twinBlock } from './text';

/** Insertions after each mermaid fence in `body` (the text `tree` was parsed from). */
export function mermaidTwinEdits(tree: Root, body: string): { start: number; end: number; text: string }[] {
  return mermaidFences(tree).map(({ node, heading }) => {
    const end = node.position!.end.offset!;
    const indent = ' '.repeat((node.position!.start.column ?? 1) - 1);
    const block = twinBlock(parseMermaid(node.value), heading)
      .split('\n')
      .map((l) => (l === '' ? '' : indent + l))
      .join('\n');
    const lineEnd = body.indexOf('\n', end);
    const at = lineEnd === -1 ? body.length : lineEnd;
    return { start: at, end: at, text: `\n\n${block}` };
  });
}
