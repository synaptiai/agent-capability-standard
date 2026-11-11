// Tests on the search helpers. The inputs are what Pagefind 1.6 returned on
// this site's built index (matched words read from each result's content at
// its locations): "zzzqqq" matched a lone "z", "xylophonequark" matched
// "(${x.y:", "qwxzv" matched "Q:", and real queries matched the words below.
import { describe, expect, it } from 'vitest';
import { isRealMatch, wordsAt } from '../src/lib/search-match';
import { spaceForSearch } from '../src/lib/search-text';
import { loadFailedMessage, retryingLoader } from '../src/lib/search-loader';

describe('search matches', () => {
  it('drops results Pagefind matched only on a short prefix of a made-up word', () => {
    expect(isRealMatch('zzzqqq', ['z'])).toBe(false);
    expect(isRealMatch('zzzqqq', ['Z"'])).toBe(false);
    expect(isRealMatch('xylophonequark', ['(${x.y:'])).toBe(false);
    expect(isRealMatch('qwxzv', ['Q:', 'Q:'])).toBe(false);
  });

  it('keeps stemmed matches, prefix matches and exact identifiers', () => {
    expect(isRealMatch('checkpoints', ['checkpoint.', 'Checkpoint'])).toBe(true);
    expect(isRealMatch('check', ['checkpoint'])).toBe(true);
    expect(isRealMatch('debug_code_change', ['debug_code_change.'])).toBe(true);
    expect(isRealMatch('V102', ['(V102);'])).toBe(true);
    expect(isRealMatch('workflow dsl', ['Workflow', 'DSL.'])).toBe(true);
    // A file path in the page matches a word of the path.
    expect(isRealMatch('whitepaper', ['spec/WHITEPAPER.md,'])).toBe(true);
    expect(isRealMatch('5.8', ['(§5.8);'])).toBe(true);
    // A made-up word does not match through one part of a path.
    expect(isRealMatch('zzzqqq', ['spec/z.md'])).toBe(false);
  });

  it('needs every query word to be matched', () => {
    expect(isRealMatch('workflow zzzqqq', ['workflow', 'z'])).toBe(false);
    expect(isRealMatch('', ['workflow'])).toBe(false);
  });

  it('accepts a one- or two-letter query word matched in full', () => {
    expect(isRealMatch('x', ['x.y'])).toBe(true);
    expect(isRealMatch('ui', ['UI'])).toBe(true);
  });

  it('reads the words at the given locations', () => {
    expect(wordsAt('VERIFY checkpoint. Save state\nfor  recovery', [1, 4])).toEqual(['checkpoint.', 'for']);
  });
});

describe('word breaks for search', () => {
  it('puts a space after the closing tags Pagefind does not break words on', () => {
    // The capability page markup the review quoted.
    const before = '<caption>Inputs of checkpoint</caption><thead><tr><th scope="col">Field</th><th scope="col">Type</th></tr></thead>';
    expect(spaceForSearch(before)).toBe(
      '<caption>Inputs of checkpoint</caption> <thead><tr><th scope="col">Field</th> <th scope="col">Type</th> </tr></thead>',
    );
    expect(spaceForSearch('<dl><dt>Declares</dt><dd>Standard 1.1.0</dd></dl>')).toBe('<dl><dt>Declares</dt> <dd>Standard 1.1.0</dd> </dl>');
    expect(spaceForSearch('<details><summary>Show</summary><pre>x</pre></details>')).toBe('<details><summary>Show</summary> <pre>x</pre></details>');
  });

  it('leaves other tags and text alone', () => {
    const html = '<p>a</p><td>b</td><code>c</code><span>d</span> </th>';
    expect(spaceForSearch(html)).toBe(html);
  });
});

describe('search index loader', () => {
  it('loads once, and after a failure tries again on the next call with a new URL', async () => {
    const urls: string[] = [];
    let fail = true;
    const load = retryingLoader('/pagefind/pagefind.js', async (url) => {
      urls.push(url);
      if (fail) throw new Error('offline');
      return { ok: url };
    });
    expect(await load()).toBeNull();
    expect(await load()).toBeNull();
    fail = false;
    const mod = await load();
    expect(mod).toEqual({ ok: '/pagefind/pagefind.js?retry=2' });
    expect(await load()).toBe(mod);
    // A cached failure of the same URL is never reused.
    expect(urls).toEqual(['/pagefind/pagefind.js', '/pagefind/pagefind.js?retry=1', '/pagefind/pagefind.js?retry=2']);
  });

  it('shares one attempt between calls made while it is loading', async () => {
    let calls = 0;
    const load = retryingLoader('/x.js', async () => {
      calls++;
      return 1;
    });
    await Promise.all([load(), load(), load()]);
    expect(calls).toBe(1);
  });

  it('tells a reader of the built site to retry, and a developer how to build', () => {
    expect(loadFailedMessage(false)).toBe('Search could not load. Check your connection and try again.');
    expect(loadFailedMessage(true)).toMatch(/npm run build/);
  });
});
