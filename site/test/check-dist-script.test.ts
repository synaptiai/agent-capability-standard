// Tests for scripts/check-dist.mjs on small hand-written dist directories.
// Each case plants one defect in an otherwise clean fixture, and the expected
// problem lines are written out by hand from the fixture.
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { checkDistDir, internalTarget, linkValues } from '../scripts/check-dist.mjs';

const O = 'https://acs.synapti.ai';

type Files = Record<string, string>;

function page(body: string): string {
  return `<!doctype html><html><head><link rel="stylesheet" href="/_astro/site.css"><script type="module" src="/_astro/app.js"></script></head><body>${body}</body></html>`;
}

/** A clean two-page site: home and /guide/, each with its copy, plus 404, sitemap, llms.txt and Pagefind. */
function cleanSite(): Files {
  return {
    'index.html': page('<h1 id="home">Home</h1><a href="/guide/#setup">Setup</a><a href="/index.md">Copy</a><a href="https://github.com/x/y/blob/main/README.md">GitHub</a>'),
    'index.md': '# Home\n',
    'guide/index.html': page('<h1 id="guide">Guide</h1><h2 id="setup">Setup</h2><a href="../">Home</a><a href="#guide">Top</a><a href="/spec/">Spec</a>'),
    'guide/index.md': '# Guide\n',
    '404.html': page('<a href="/">Home</a>'),
    '_astro/site.css': '',
    '_astro/app.js': '',
    '_redirects': '/spec/ /guide/ 302\n',
    'pagefind/pagefind.js': '',
    'llms-full.txt': '# all\n',
    'llms.txt': `# Site\n\n## Pages\n\n- [Home](${O}/index.md)\n- [Guide](${O}/guide/index.md): how to start\n`,
    'sitemap.xml': `<?xml version="1.0"?><urlset><url><loc>${O}/</loc></url><url><loc>${O}/guide/</loc></url></urlset>`,
  };
}

let dirs: string[] = [];
afterEach(() => {
  for (const d of dirs) rmSync(d, { recursive: true, force: true });
  dirs = [];
});

function build(files: Files): string {
  const dir = mkdtempSync(path.join(tmpdir(), 'acs-check-dist-'));
  dirs.push(dir);
  for (const [f, text] of Object.entries(files)) {
    mkdirSync(path.dirname(path.join(dir, f)), { recursive: true });
    writeFileSync(path.join(dir, f), text);
  }
  return dir;
}

function problems(files: Files): string[] {
  const { problems: p } = checkDistDir(build(files));
  return Object.entries(p).flatMap(([check, list]) => list.map((l) => `[${check}] ${l}`));
}

describe('check-dist.mjs', () => {
  it('passes the clean fixture and counts its pages', () => {
    const r = checkDistDir(build(cleanSite()));
    expect(Object.values(r.problems).flat()).toEqual([]);
    expect(r.stats.pages).toBe(2);
    expect(r.stats.copies).toBe(2);
  });

  it('fails a link to a page that does not exist', () => {
    const s = cleanSite();
    s['index.html'] = s['index.html']!.replace('/guide/#setup', '/guides/');
    expect(problems(s)).toEqual(['[links] /: /guides/ does not resolve to a file in dist']);
  });

  it('fails a link whose case differs from the file in dist', () => {
    const s = cleanSite();
    s['index.html'] = s['index.html']!.replace('/guide/#setup', '/Guide/');
    expect(problems(s)).toEqual(['[links] /: /Guide/ does not resolve to a file in dist']);
  });

  it('fails a fragment that is not an id on the target page', () => {
    const s = cleanSite();
    s['index.html'] = s['index.html']!.replace('/guide/#setup', '/guide/#install');
    expect(problems(s)).toEqual(['[links] /: /guide/#install names #install, which is not an id on /guide/']);
  });

  it('fails a fragment on the same page', () => {
    const s = cleanSite();
    s['guide/index.html'] = s['guide/index.html']!.replace('#guide', '#top');
    expect(problems(s)).toEqual(['[links] /guide/: #top names #top, which is not an id on /guide/']);
  });

  it('fails a src that does not resolve, and an absolute link on the site origin', () => {
    const s = cleanSite();
    s['404.html'] = page(`<img src="/og.png"><a href="${O}/missing/">x</a>`);
    expect(problems(s)).toEqual([
      '[links] /404.html: /og.png does not resolve to a file in dist',
      `[links] /404.html: ${O}/missing/ does not resolve to a file in dist`,
    ]);
  });

  it('fails a raw relative .md link but not a link to a Markdown copy or GitHub', () => {
    const s = cleanSite();
    s['guide/index.html'] = s['guide/index.html']!.replace('href="../"', 'href="../docs/FAQ.md#top"');
    expect(problems(s)).toEqual(["[md-links] /guide/: links to ../docs/FAQ.md#top, a .md file that is not a page's Markdown copy"]);
  });

  it('fails a page with no Markdown copy', () => {
    const s = cleanSite();
    delete s['guide/index.md'];
    expect(problems(s)).toEqual([
      '[copies] /guide/: no Markdown copy at /guide/index.md',
      '[copies] llms.txt lists /guide/index.md, which is not in dist',
    ]);
  });

  it('fails a copy that llms.txt leaves out, and one it lists twice', () => {
    const s = cleanSite();
    s['llms.txt'] = `# Site\n\n- [Home](${O}/index.md)\n- [Home again](${O}/index.md)\n`;
    expect(problems(s)).toEqual([
      '[copies] llms.txt does not list /guide/index.md',
      '[copies] llms.txt lists /index.md more than once',
    ]);
  });

  it('fails a sitemap that misses a page or lists one that is not built', () => {
    const s = cleanSite();
    s['sitemap.xml'] = `<urlset><url><loc>${O}/</loc></url><url><loc>${O}/404/</loc></url></urlset>`;
    expect(problems(s)).toEqual([
      '[sitemap] sitemap.xml does not list /guide/',
      '[sitemap] sitemap.xml lists /404/, which is not an HTML page in dist',
    ]);
  });

  it('fails when Pagefind did not run', () => {
    const s = cleanSite();
    delete s['pagefind/pagefind.js'];
    expect(problems(s)).toEqual(['[files] pagefind/pagefind.js is missing from dist']);
  });
});

describe('link parsing', () => {
  it('reads attributes in tags only, not in code samples or scripts', () => {
    const html = '<pre><code>&lt;a href="/nope/"&gt;</code></pre><script>const a = \'<a href="/also-nope/">\';</script><a class="x" href="/a/?q=1&amp;b=2#k%C3%A9">y</a>';
    expect(linkValues(html)).toEqual(['/a/?q=1&b=2#k%C3%A9']);
    expect(internalTarget('/a/?q=1&b=2#k%C3%A9', '/')).toEqual({ path: '/a/', fragment: 'ké' });
  });

  it('resolves relative links against the page and leaves other origins alone', () => {
    expect(internalTarget('../b/', '/a/x/')).toEqual({ path: '/a/b/', fragment: null });
    expect(internalTarget('mailto:a@b.c', '/')).toBeNull();
    expect(internalTarget('https://github.com/x', '/')).toBeNull();
    expect(internalTarget('//cdn.example/x.js', '/')).toBeNull();
  });
});
