// The menu panel's focus cycle. Expected moves are the ones the design notes
// ask for ("focus is trapped while it is open"), worked out by hand for a
// cycle of the menu button and three links.
import { describe, expect, it } from 'vitest';
import { wrapFocus } from '../src/lib/focus';

const items = ['button', 'a1', 'a2', 'a3'];

describe('wrapFocus', () => {
  it('moves Tab from the last link back to the menu button', () => {
    expect(wrapFocus(items, 'a3', false)).toBe('button');
  });

  it('moves Shift+Tab from the menu button to the last link', () => {
    expect(wrapFocus(items, 'button', true)).toBe('a3');
  });

  it('leaves moves inside the cycle to the browser', () => {
    expect(wrapFocus(items, 'button', false)).toBeNull();
    expect(wrapFocus(items, 'a2', false)).toBeNull();
    expect(wrapFocus(items, 'a3', true)).toBeNull();
  });

  it('brings focus that has left the cycle back into it', () => {
    expect(wrapFocus(items, 'body', false)).toBe('button');
    expect(wrapFocus(items, null, true)).toBe('a3');
  });

  it('does nothing with no items', () => {
    expect(wrapFocus([], 'a1', false)).toBeNull();
  });
});
