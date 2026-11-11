// Wraps each Markdown table in a scroll container that keyboard users can
// reach and screen readers can name:
//   <div class="table-wrap" role="region" tabindex="0" aria-label="Table: Layer architecture">
//     <table>...</table>
//   </div>
// The label is the table's caption if it has one, otherwise the text of the
// nearest heading before it, otherwise "Table". A label already used on the
// page gets " (2)", " (3)" and so on, so screen readers can tell the
// regions apart. The table itself keeps its
// table display, so its semantics are not lost. Generated pages use the
// TableWrap component, which writes the same wrapper.
import type { Element, ElementContent, Root, RootContent } from 'hast';
import { SKIP, visit } from 'unist-util-visit';

const HEADING = /^h[1-6]$/;

/** Visible text of a node: text inside aria-hidden elements is left out. */
export function visibleText(n: ElementContent | RootContent): string {
  if (n.type === 'text') return n.value;
  if (n.type !== 'element') return '';
  if (String(n.properties?.ariaHidden) === 'true') return '';
  return n.children.map(visibleText).join('');
}

/** The wrapper's accessible name, from a caption or a heading. */
export function tableLabel(caption: string | null, heading: string | null): string {
  const c = caption?.replace(/\s+/g, ' ').trim();
  if (c) return c;
  const h = heading?.replace(/\s+/g, ' ').trim();
  return h ? `Table: ${h}` : 'Table';
}

/** `label`, or `label (n)` when it was already used `n - 1` times. */
export function uniqueLabel(label: string, used: Map<string, number>): string {
  const n = (used.get(label) ?? 0) + 1;
  used.set(label, n);
  return n === 1 ? label : `${label} (${n})`;
}

function isWrap(n: Root | Element | undefined): boolean {
  if (n?.type !== 'element') return false;
  const cls = n.properties?.className;
  return Array.isArray(cls) && cls.includes('table-wrap');
}

export default function rehypeTables() {
  return (tree: Root): void => {
    let heading: string | null = null;
    const used = new Map<string, number>();
    visit(tree, 'element', (node: Element, index, parent) => {
      if (HEADING.test(node.tagName)) {
        heading = visibleText(node);
        return SKIP;
      }
      if (node.tagName !== 'table' || parent === undefined || index === undefined) return;
      if (isWrap(parent)) return SKIP;
      const caption = node.children.find((c): c is Element => c.type === 'element' && c.tagName === 'caption');
      parent.children[index] = {
        type: 'element',
        tagName: 'div',
        properties: {
          className: ['table-wrap'],
          role: 'region',
          tabIndex: 0,
          ariaLabel: uniqueLabel(tableLabel(caption ? visibleText(caption) : null, heading), used),
        },
        children: [node],
      };
      return SKIP;
    });
  };
}
