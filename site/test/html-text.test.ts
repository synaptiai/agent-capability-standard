import { describe, expect, it } from 'vitest';
import { markerUrls, visibleText, withoutTags } from './html-text';

describe('withoutTags', () => {
  it('drops every tag and keeps the text', () => {
    expect(withoutTags('<h3 id="x">1. <code>plan</code> step</h3>')).toBe('1. plan step');
    expect(withoutTags('a < b')).toBe('a < b');
    expect(withoutTags('')).toBe('');
  });
});

describe('visibleText', () => {
  it('leaves out svg and aria-hidden content, nested or not', () => {
    const header =
      '<svg viewBox="0 0 1 1"><title>logo</title><g><path d="M0"/></g></svg>' +
      '<span aria-hidden="true">ACS<span>!</span></span>' +
      '<span class="name">Agent Capability Standard</span> home';
    expect(visibleText(header)).toBe('Agent Capability Standard home');
    expect(visibleText('a<br>b<img src="x" alt="">c')).toBe('abc');
    expect(visibleText('<span data-aria-hidden="true">kept</span>')).toBe('kept');
  });
});

describe('markerUrls', () => {
  it('reads the URL of each marker line, in order', () => {
    const text = '# T\n<!-- https://x/a/index.md -->\ntext <!-- not a marker -->\n<!-- https://x/b/index.md -->\n';
    expect(markerUrls(text)).toEqual(['https://x/a/index.md', 'https://x/b/index.md']);
  });
});
