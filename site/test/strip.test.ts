// stripTags and stripComments scan characters, so removing one piece cannot
// form a new tag or comment (CodeQL js/incomplete-multi-character-sanitization).
// Expected values are worked out by hand.
import { describe, expect, it } from 'vitest';
import { stripComments, stripTags } from '../src/lib/strip';

describe('stripTags', () => {
  it('removes tags and keeps the text', () => {
    expect(stripTags('<h3 id="x">Safety <code>&amp;</code> Recovery</h3>')).toBe('Safety &amp; Recovery');
  });
  it('leaves no tag that removing an inner one would form', () => {
    // One pass of /<[^<>]*>/ turns "<scr<b>ipt>" into "<script>".
    expect(stripTags('<scr<b>ipt>alert(1)</scr</b>ipt>')).toBe('alert(1)');
  });
  it('drops the rest after an unclosed tag', () => {
    expect(stripTags('a <b c')).toBe('a ');
  });
  it('keeps a "<" that does not open a tag', () => {
    expect(stripTags('x < 5 and y <= 6 <i>z</i>')).toBe('x < 5 and y <= 6 z');
  });
  it('can put a separator in place of each tag', () => {
    expect(stripTags('a<br>b<i>c</i>', ' ')).toBe('a b c ');
  });
});

describe('stripComments', () => {
  it('leaves no comment that removing an inner one would form', () => {
    expect(stripComments('a<!<!-- x -->-- y -->b')).toBe('ab');
  });
  it('drops the rest after an unclosed comment', () => {
    expect(stripComments('a<!-- b')).toBe('a');
  });
});
