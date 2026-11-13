// hast helpers the rehype plugins share.
import type { Element, ElementContent, Root, RootContent } from 'hast';

/** Whether `n` is an element, and of tag `tag` when one is given. */
export const isEl = (n: unknown, tag?: string): n is Element =>
  typeof n === 'object' && n !== null && (n as Element).type === 'element' && (tag === undefined || (n as Element).tagName === tag);

/** Text of a hast node, aria-hidden parts included (heading-anchor links hold no text). */
export function hastText(n: ElementContent | Root | RootContent): string {
  if (n.type === 'text') return n.value;
  if (n.type !== 'element' && n.type !== 'root') return '';
  return (n.children as ElementContent[]).map(hastText).join('');
}
