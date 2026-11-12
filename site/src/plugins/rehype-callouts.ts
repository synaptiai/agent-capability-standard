// Turns a blockquote that opens with a label into a callout. Two source forms
// are accepted: `> **Note:** text` (the colon may also sit after the bold) and
// GitHub's alert form `> [!NOTE]`. The labels are Note, Tip, Important, Warning
// and Caution. The result is
//   <div class="callout callout--note" role="note">
//     <p class="callout__label"><svg …/> Note</p> ...the rest of the quote...
//   </div>
// The label carries the same 7x7 glyph as the generated callouts
// (CALLOUT_GLYPHS, visual spec 3.10.3), decorative beside the word.
// Any other blockquote is left as it is.
import type { Element, ElementContent, Root } from 'hast';
import { visit } from 'unist-util-visit';
import { glyphElement } from '../pixel/hast';

export const CALLOUT_TYPES = ['note', 'tip', 'important', 'warning', 'caution'] as const;
export type CalloutType = (typeof CALLOUT_TYPES)[number];

/** The glyph of each callout type, shared with the generated callouts (Callout.astro). */
export const CALLOUT_GLYPHS: Readonly<Record<CalloutType | 'requirement', string>> = {
  note: 'note',
  tip: 'check',
  important: 'note',
  warning: 'warning',
  caution: 'caution',
  requirement: 'mark:required',
};

const LABEL = /^(note|tip|important|warning|caution)\s*(:?)$/i;
const ALERT = /^\[!(note|tip|important|warning|caution)\]\s*/i;

function toString(n: ElementContent): string {
  if (n.type === 'text') return n.value;
  return n.type === 'element' ? n.children.map(toString).join('') : '';
}

function isElement(n: ElementContent | undefined, tag?: string): n is Element {
  return n?.type === 'element' && (tag === undefined || n.tagName === tag);
}

function isBlank(n: ElementContent): boolean {
  return n.type === 'text' && n.value.trim() === '';
}

/** Strip the label from the quote's first paragraph; returns the callout type. */
function takeLabel(p: Element): CalloutType | null {
  const kids = p.children;
  const first = kids[0];
  if (isElement(first, 'strong')) {
    const m = LABEL.exec(toString(first).trim());
    if (!m) return null;
    const after = kids[1];
    if (m[2] === '') {
      if (after?.type !== 'text' || !after.value.startsWith(':')) return null;
      after.value = after.value.slice(1);
    }
    kids.shift();
    const lead = kids[0];
    if (lead?.type === 'text') lead.value = lead.value.replace(/^\s+/, '');
    return m[1]!.toLowerCase() as CalloutType;
  }
  if (first?.type === 'text') {
    const m = ALERT.exec(first.value);
    if (!m) return null;
    first.value = first.value.slice(m[0].length);
    if (first.value === '') kids.shift();
    const br = kids[0];
    if (isElement(br, 'br')) kids.shift();
    return m[1]!.toLowerCase() as CalloutType;
  }
  return null;
}

export default function rehypeCallouts() {
  return (tree: Root): void => {
    visit(tree, 'element', (node: Element) => {
      if (node.tagName !== 'blockquote') return;
      const p = node.children.find((c) => !isBlank(c));
      if (!isElement(p, 'p')) return;
      const type = takeLabel(p);
      if (type === null) return;
      if (p.children.every(isBlank)) node.children.splice(node.children.indexOf(p), 1);
      const label = type[0]!.toUpperCase() + type.slice(1);
      node.tagName = 'div';
      node.properties = { className: ['callout', `callout--${type}`], role: 'note' };
      node.children.unshift({
        type: 'element',
        tagName: 'p',
        properties: { className: ['callout__label'] },
        children: [glyphElement(CALLOUT_GLYPHS[type]), { type: 'text', value: ` ${label}` }],
      });
    });
  };
}
