// The parts of scripts/check-axe.mjs that do not need a browser: reading the
// sitemap and mapping a request path to a file in dist/. Expected values come
// from the hand-written sitemap and directory below. The browser run itself is
// the CI step "Check accessibility with axe".
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import { AXE_TAGS, fileFor, pathsArg, sitemapPaths, THEMES, WIDTHS } from '../scripts/check-axe.mjs';

const dist = mkdtempSync(path.join(tmpdir(), 'acs-axe-'));
afterAll(() => rmSync(dist, { recursive: true, force: true }));

describe('the --paths argument (check-axe and check-runs)', () => {
  it('takes the pages it names out of the arguments, and null without it', () => {
    const args = ['dist', '--paths', '/,/a/', '--all'];
    expect(pathsArg(args)).toEqual(['/', '/a/']);
    expect(args).toEqual(['dist', '--all']);
    expect(pathsArg(['dist'])).toBeNull();
  });

  it('throws when --paths names no page', () => {
    expect(() => pathsArg(['--paths'])).toThrow('--paths names no page');
    expect(() => pathsArg(['--paths', ''])).toThrow('--paths names no page');
    expect(() => pathsArg(['--paths', ','])).toThrow('--paths names no page');
  });
});

describe('check-axe', () => {
  it('reads every page path from a sitemap, in order', () => {
    const xml = '<urlset><url><loc>https://acs.synapti.ai/</loc></url><url><loc> https://acs.synapti.ai/a/b/ </loc></url></urlset>';
    expect(sitemapPaths(xml)).toEqual(['/', '/a/b/']);
  });

  it('serves a page directory as its index.html and refuses paths outside dist', () => {
    mkdirSync(path.join(dist, 'a'), { recursive: true });
    writeFileSync(path.join(dist, 'a', 'index.html'), '<p>a</p>');
    writeFileSync(path.join(dist, 'style.css'), '');
    expect(fileFor(dist, '/a/')).toBe(path.join(dist, 'a', 'index.html'));
    expect(fileFor(dist, '/a/?q=1#x')).toBe(path.join(dist, 'a', 'index.html'));
    expect(fileFor(dist, '/style.css')).toBe(path.join(dist, 'style.css'));
    expect(fileFor(dist, '/missing/')).toBeNull();
    expect(fileFor(dist, '/../etc/passwd')).toBeNull();
  });

  it('checks both themes at a desktop and the 360px phone width, against WCAG 2.2 AA and best practice', () => {
    // Build brief D2: every page, light and dark; the design's phone width is 360px.
    expect(THEMES).toEqual(['light', 'dark']);
    expect(WIDTHS).toContain(360);
    expect(AXE_TAGS).toEqual(expect.arrayContaining(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa', 'best-practice']));
  });
});
