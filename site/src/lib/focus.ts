// Focus wrapping for the menu panel. While the panel is open, Tab cycles
// through the menu button and the panel's links and never leaves them.

/**
 * Where Tab should move focus inside a cycle of `items` (in tab order), or
 * null to let the browser move it. Tab on the last item goes to the first;
 * Shift+Tab on the first goes to the last; focus outside the cycle goes to
 * the first item (or the last, with Shift).
 */
export function wrapFocus<T>(items: readonly T[], current: T | null, shift: boolean): T | null {
  if (items.length === 0) return null;
  const first = items[0]!;
  const last = items[items.length - 1]!;
  const i = current === null ? -1 : items.indexOf(current);
  if (i === -1) return shift ? last : first;
  if (!shift && i === items.length - 1) return first;
  if (shift && i === 0) return last;
  return null;
}
