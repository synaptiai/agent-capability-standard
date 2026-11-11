// The contents list read from rendered HTML. Expected entries are written by
// hand from the fixture.
import { describe, expect, it } from 'vitest';
import { tocEntries } from '../src/lib/toc';

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
