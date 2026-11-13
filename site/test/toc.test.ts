// The contents list read from rendered HTML. Expected entries are written by
// hand from the fixture.
import { describe, expect, it } from 'vitest';
import { decodeEntities, tocEntries } from '../src/lib/toc';

describe('tocEntries', () => {
  it('reads h2 and h3 headings with ids, in order, as plain text', () => {
    const html = [
      '<h1 id="t">Title</h1>',
      '<h2 id="a">A &amp; B<a class="heading-anchor" href="#a"><span class="icon"></span></a></h2>',
      '<h3 id="c"><code>step</code> &lt;one&gt;</h3>',
      '<h4 id="d">Deep</h4>',
      '<h2>No id</h2>',
      '<h2 id="e">Caf&#xe9;   time</h2>',
    ].join('');
    expect(tocEntries(html)).toEqual([
      { depth: 2, id: 'a', text: 'A & B' },
      { depth: 3, id: 'c', text: 'step <one>' },
      { depth: 2, id: 'e', text: 'Café time' },
    ]);
  });
});

describe('decodeEntities', () => {
  it('reads numeric references, and leaves a named one it does not know unchanged', () => {
    expect(decodeEntities('A &#x26; B &#X3C; C &#38;')).toBe('A & B < C &');
    // Named references whose second letter is x are not hex references.
    expect(decodeEntities('&excl; &exist; &ex;')).toBe('&excl; &exist; &ex;');
  });
});
