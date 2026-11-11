// Names the checkboxes of Markdown task lists ("- [ ] item"). GitHub-flavoured
// Markdown renders each as a disabled <input type="checkbox"> with no label, so
// a screen reader announces "checkbox, not checked" and nothing else. Each one
// gets the visible text of its list item as its accessible name, so the list
// reads as "Item text, checkbox, not checked".
import type { Element, Root } from 'hast';
import { visit } from 'unist-util-visit';
import { visibleText } from './rehype-tables';

const MAX = 120;

/** The label for a task item: its text on one line, cut at a word before MAX characters. */
export function taskLabel(text: string): string {
  const t = text.replace(/\s+/g, ' ').trim();
  if (t.length <= MAX) return t;
  const cut = t.slice(0, MAX);
  const space = cut.lastIndexOf(' ');
  return `${(space > 0 ? cut.slice(0, space) : cut).trimEnd()}…`;
}

/** The item's own text: nested lists are left out. */
function ownText(li: Element): string {
  return li.children
    .map((c) => (c.type === 'element' && (c.tagName === 'ul' || c.tagName === 'ol') ? '' : visibleText(c)))
    .join(' ');
}

function isCheckbox(n: Element): boolean {
  return n.tagName === 'input' && String(n.properties?.type) === 'checkbox';
}

export default function rehypeTaskLists() {
  return (tree: Root): void => {
    visit(tree, 'element', (li: Element) => {
      if (li.tagName !== 'li') return;
      const cls = li.properties?.className;
      if (!Array.isArray(cls) || !cls.includes('task-list-item')) return;
      // The checkbox is the item's first input, directly or inside its first paragraph.
      let box: Element | undefined;
      visit(li, 'element', (n: Element) => {
        if (n !== li && (n.tagName === 'ul' || n.tagName === 'ol')) return 'skip';
        if (!box && isCheckbox(n)) box = n;
      });
      if (!box || box.properties?.ariaLabel || box.properties?.ariaLabelledby) return;
      const label = taskLabel(ownText(li));
      if (label) box.properties = { ...box.properties, ariaLabel: label };
    });
  };
}
