// Tests for scripts/check-dist.mjs on small hand-written dist directories.
// Each case plants one defect in an otherwise clean fixture, and the expected
// problem lines are written out by hand from the fixture.
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { checkDistDir, internalTarget, linkValues, markdownLinkValues } from '../scripts/check-dist.mjs';

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

  it('fails a broken site URL and a raw relative .md link in a Markdown copy', () => {
    const s = cleanSite();
    s['guide/index.md'] = `# Guide\n\nSee [x](${O}/no-such-page/) and [y](../docs/FAQ.md).\n`;
    expect(problems(s)).toEqual([
      `[links] /guide/index.md: ${O}/no-such-page/ does not resolve to a file in dist`,
      "[md-links] /guide/index.md: links to ../docs/FAQ.md, a .md file that is not a page's Markdown copy",
    ]);
  });

  it('fails a broken site URL and a missing fragment in llms-full.txt', () => {
    const s = cleanSite();
    s['llms-full.txt'] = `# all\n\n[x](${O}/no-such-page/)\n\n[y](${O}/guide/#install)\n`;
    expect(problems(s)).toEqual([
      `[links] /llms-full.txt: ${O}/no-such-page/ does not resolve to a file in dist`,
      `[links] /llms-full.txt: ${O}/guide/#install names #install, which is not an id on /guide/`,
    ]);
  });

  it('fails a social image on the site origin that is not in dist', () => {
    const s = cleanSite();
    s['guide/index.html'] = s['guide/index.html']!.replace('<head>', `<head><meta property="og:image" content="${O}/og-missing.png">`);
    expect(problems(s)).toEqual([`[links] /guide/: ${O}/og-missing.png does not resolve to a file in dist`]);
  });

  it('reports a broken link once per page, however often the page repeats it', () => {
    const s = cleanSite();
    s['index.html'] = s['index.html']!.replace('<a href="/guide/#setup">Setup</a>', '<a href="/guides/">a</a><a href="/guides/">b</a><a href="/guides/">c</a>');
    expect(problems(s)).toEqual(['[links] /: /guides/ does not resolve to a file in dist']);
  });

  it('fails when Pagefind did not run', () => {
    const s = cleanSite();
    delete s['pagefind/pagefind.js'];
    expect(problems(s)).toEqual(['[files] pagefind/pagefind.js is missing from dist']);
  });

  // Visual spec 6.1: each numbered figure has a "**Figure: {title}.**" block in the page's Markdown copy.
  const fig = (id: string, n: number, title: string) =>
    `<figure class="fig" id="${id}" aria-labelledby="${id}-title"><p class="fig__eyebrow" aria-hidden="true">Fig ${n}</p><p class="fig__title" id="${id}-title">${title}</p><div></div><figcaption class="fig__caption">c</figcaption></figure>`;

  it('passes a figure whose block is in the copy, in a list item, with its code span undone', () => {
    const s = cleanSite();
    s['guide/index.html'] = s['guide/index.html']!.replace('</h1>', `</h1>${fig('ref-a', 1, 'Steps of <code>x</code> &amp; y')}`);
    s['guide/index.md'] = '# Guide\n\n- item\n\n  **Figure: Steps of `x` & y.** c\n';
    expect(problems(s)).toEqual([]);
  });

  it('fails a numbered figure with no block, and a block with no figure', () => {
    const s = cleanSite();
    s['guide/index.html'] = s['guide/index.html']!.replace('</h1>', `</h1>${fig('ref-a', 1, 'Edge properties')}`);
    s['index.md'] = '# Home\n\n**Figure: Old chart.** gone\n';
    expect(problems(s)).toEqual([
      '[figures] /guide/: Fig 1 "Edge properties" has no "**Figure: Edge properties.**" block in /guide/index.md',
      '[figures] /index.md: the block "**Figure: Old chart.**" names no figure on the page',
    ]);
  });

  it('names a box diagram by its aria-label, and does not count a block written inside a code fence', () => {
    const s = cleanSite();
    s['guide/index.html'] = s['guide/index.html']!.replace(
      '</h1>',
      '</h1><figure class="fig fig-ascii" aria-label="Diagram: Setup"><p class="fig__eyebrow" aria-hidden="true">Fig 1</p><pre>┌─┐</pre></figure>',
    );
    s['guide/index.md'] = '# Guide\n\n```md\n**Figure: Diagram: Setup.** x\n```\n';
    expect(problems(s)).toEqual(['[figures] /guide/: Fig 1 "Diagram: Setup" has no "**Figure: Diagram: Setup.**" block in /guide/index.md']);
  });

  it('leaves out a figure whose eyebrow is not a number (a folded text version)', () => {
    const s = cleanSite();
    s['guide/index.html'] = s['guide/index.html']!.replace('</h1>', '</h1><figure class="fig fig-ascii" aria-label="Diagram: Setup"><p class="fig__eyebrow">Text version</p></figure>');
    expect(problems(s)).toEqual([]);
  });

  // A legend entry is keyed by the marks it draws, so two glyph names for one grid are one glyph.
  const glyph = (rects: string, key: string) => `<svg class="pg" viewBox="0 0 7 7" data-glyph="${key}" aria-hidden="true">${rects}</svg>`;
  const UNDO = '<rect x="0" y="2" width="7" height="1"></rect>';
  const MARK = '<rect x="3" y="3" width="1" height="1"></rect>';

  it('fails a legend that draws one glyph for two different entries', () => {
    const s = cleanSite();
    s['guide/index.html'] = s['guide/index.html']!.replace(
      '</h1>',
      `</h1><ul class="spine-legend" aria-label="Key"><li>${glyph(UNDO, 'role:rollback')}<span>step rolls back</span></li><li>${glyph(UNDO, 'fail:rollback')}<span>on failure, roll back</span></li></ul>`,
    );
    expect(problems(s)).toEqual(['[legends] /guide/: the legend "Key" draws the same glyph for "step rolls back" and "on failure, roll back"']);
  });

  it('passes a legend whose entries differ by a lane mark before the same glyph', () => {
    const s = cleanSite();
    s['guide/index.html'] = s['guide/index.html']!.replace(
      '</h1>',
      `</h1><ul class="spine-legend" aria-label="Key"><li>${glyph(UNDO, 'role:rollback')}<span>step rolls back</span></li><li>${glyph(MARK, 'close')}${glyph(UNDO, 'fail:rollback')}<span>on failure, roll back</span></li></ul>`,
    );
    expect(problems(s)).toEqual([]);
  });

  it('fails a built file that links to the review pages, which the deploy removes', () => {
    const s = cleanSite();
    s['guide/index.html'] = s['guide/index.html']!.replace('</h1>', '</h1><a href="/_review/glyphs/">Glyphs</a>');
    s['_review/glyphs/index.html'] = page('<h1 id="g">Glyph sheet</h1>');
    const p = problems(s);
    expect(p).toContain('[review] guide/index.html points at the review pages (/_review/), which are not deployed');
  });
});

describe('link parsing', () => {
  it('reads attributes in tags only, not in code samples or scripts', () => {
    const html = '<pre><code>&lt;a href="/nope/"&gt;</code></pre><script>const a = \'<a href="/also-nope/">\';</script><a class="x" href="/a/?q=1&amp;b=2#k%C3%A9">y</a>';
    expect(linkValues(html)).toEqual(['/a/?q=1&b=2#k%C3%A9']);
    expect(internalTarget('/a/?q=1&b=2#k%C3%A9', '/')).toEqual({ path: '/a/', fragment: 'ké' });
  });

  it('reads meta content only when it is a URL on the site origin', () => {
    const html = `<meta property="og:image" content="${O}/og.png"><meta name="description" content="/not-a-link/"><meta property="og:see" content="https://example.com/x.png">`;
    expect(linkValues(html)).toEqual([`${O}/og.png`]);
  });

  it('reads Markdown links and definitions, not code', () => {
    const md = [
      '[a](/x/ "title") ![i](<../img one.png>) and `[no](/code-span/)`',
      '```js',
      'f(arr[0](/fenced/))',
      '```',
      '[ref]: https://example.com/r',
    ].join('\n');
    expect(markdownLinkValues(md)).toEqual(['/x/', '../img one.png', 'https://example.com/r']);
  });

  it('resolves relative links against the page and leaves other origins alone', () => {
    expect(internalTarget('../b/', '/a/x/')).toEqual({ path: '/a/b/', fragment: null });
    expect(internalTarget('mailto:a@b.c', '/')).toBeNull();
    expect(internalTarget('https://github.com/x', '/')).toBeNull();
    expect(internalTarget('//cdn.example/x.js', '/')).toBeNull();
  });
});
