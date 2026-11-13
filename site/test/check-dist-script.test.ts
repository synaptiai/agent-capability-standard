// Tests for scripts/check-dist.mjs on small hand-written dist directories.
// Each case plants one defect in an otherwise clean fixture, and the expected
// problem lines are written out by hand from the fixture.
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { checkDistDir, drawnFigure, internalTarget, linkValues, markdownLinkValues } from '../scripts/check-dist.mjs';

const O = 'https://acs.synapti.ai';

type Files = Record<string, string>;

function page(body: string): string {
  return `<!doctype html><html><head><link rel="stylesheet" href="/_astro/site.css"><script type="module" src="/_astro/app.js"></script></head><body class="page page--prose">${body}</body></html>`;
}

/**
 * A clean two-page site: home and /guide/, each with its copy, plus 404,
 * sitemap, Pagefind, a root llms.txt that lists the home copy and links the
 * guide section's llms.txt, which lists the guide's copy.
 */
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
    'llms.txt': `# Site\n\n## Pages\n\n- [Home](${O}/index.md)\n- [All guide pages](${O}/guide/llms.txt)\n`,
    'guide/llms.txt': `# Guide\n\n- [Guide](${O}/guide/index.md): how to start\n`,
    'sitemap.xml': `<?xml version="1.0"?><urlset><url><loc>${O}/</loc></url><url><loc>${O}/guide/</loc></url></urlset>`,
    ...apiFiles(),
  };
}

/** A data API of two files and one parameter with two values, its OpenAPI document, api-catalog and header. */
function apiFiles(): Files {
  const openapi = {
    openapi: '3.1.1',
    paths: {
      '/api/v1/index.json': { get: { operationId: 'readApiIndex' } },
      '/api/v1/things/{id}.json': { get: { operationId: 'readThing', parameters: [{ name: 'id', in: 'path', schema: { type: 'string', enum: ['a', 'b'] } }] } },
    },
  };
  const catalog = {
    linkset: [
      { anchor: `${O}/.well-known/api-catalog`, item: [{ href: `${O}/api/v1/` }] },
      { anchor: `${O}/api/v1/`, 'service-desc': [{ href: `${O}/openapi.json` }], 'service-doc': [{ href: `${O}/guide/` }] },
    ],
  };
  return {
    'openapi.json': JSON.stringify(openapi),
    'api/v1/index.json': '{}',
    'api/v1/things/a.json': '{}',
    'api/v1/things/b.json': '{}',
    '.well-known/api-catalog': JSON.stringify(catalog),
    '_headers': '/*.md\n  Content-Type: text/markdown\n\n/.well-known/api-catalog\n  Content-Type: application/linkset+json; profile="https://www.rfc-editor.org/info/rfc9727"\n',
    '_redirects': '/spec/ /guide/ 302\n/api/v1/ /api/v1/index.json 302\n',
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

/** The problems check-dist finds; `drawn` are the templates whose pages need a drawn figure (none in the clean site). */
function problems(files: Files, drawn: readonly string[] = []): string[] {
  const { problems: p } = checkDistDir(build(files), { drawnTemplates: drawn });
  return Object.entries(p).flatMap(([check, list]) => list.map((l) => `[${check}] ${l}`));
}

describe('check-dist.mjs', () => {
  it('passes the clean fixture and counts its pages', () => {
    const r = checkDistDir(build(cleanSite()), { drawnTemplates: [] });
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
      `[links] /guide/llms.txt: ${O}/guide/index.md does not resolve to a file in dist`,
      '[copies] /guide/: no Markdown copy at /guide/index.md',
      '[copies] an llms.txt lists /guide/index.md, which is not in dist',
    ]);
  });

  it('fails a copy that no llms.txt lists and a section file the root does not link, but lets the root name a copy twice', () => {
    const s = cleanSite();
    s['llms.txt'] = `# Site\n\n- [Home](${O}/index.md)\n- [Home again](${O}/index.md)\n`;
    s['guide/llms.txt'] = '# Guide\n';
    expect(problems(s)).toEqual([
      '[copies] llms.txt does not link guide/llms.txt',
      '[copies] no llms.txt lists /guide/index.md',
    ]);
  });

  it('fails a copy that two section files list', () => {
    const s = cleanSite();
    s['llms.txt'] += `- [More](${O}/more/llms.txt)\n`;
    s['more/llms.txt'] = `# More\n\n- [Guide](${O}/guide/index.md)\n- [Guide](${O}/guide/index.md)\n`;
    expect(problems(s)).toEqual(['[copies] more/llms.txt lists /guide/index.md more than once', '[copies] /guide/index.md is listed by both guide/llms.txt and more/llms.txt']);
  });

  it('accepts a link to a path another part of the build serves, and to /agents.md, but not to another missing file', () => {
    const s = cleanSite();
    s['llms.txt'] += `- [MCP](${O}/.well-known/mcp/server-card.json)\n- [API](${O}/openapi.json)\n- [Developers](${O}/developers/index.md)\n- [Agents](${O}/agents.md)\n- [Other](${O}/other.json)\n`;
    s['agents.md'] = `# Agents\n\n[Home](${O}/index.md) and [missing](${O}/gone/)\n`;
    expect(problems(s)).toEqual([
      `[links] /agents.md: ${O}/gone/ does not resolve to a file in dist`,
      `[links] /llms.txt: ${O}/other.json does not resolve to a file in dist`,
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

  it('treats an element whose class ends in "key" as a legend too', () => {
    const s = cleanSite();
    s['guide/index.html'] = s['guide/index.html']!.replace(
      '</h1>',
      `</h1><dl class="diag-key"><div>${glyph(UNDO, 'a')}<dt>error</dt></div><div>${glyph(UNDO, 'b')}<dt>warning</dt></div></dl>`,
    );
    expect(problems(s)).toEqual(['[legends] /guide/: the legend "diag-key" draws the same glyph for "error" and "warning"']);
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

describe('drawn figures', () => {
  const fig = (n: number, drawing: string) =>
    `<figure class="fig" aria-labelledby="f${n}-t"><p class="fig__eyebrow" aria-hidden="true">Fig ${n}</p><p class="fig__title" id="f${n}-t">F${n}</p><div class="fig__drawing">${drawing}</div><figcaption class="fig__caption">c</figcaption></figure>`;
  const svg = '<svg viewBox="0 0 1 1"><rect width="1" height="1"/></svg>';
  const table = (cell: string) => `<div class="table-wrap"><table><tbody><tr><td>${cell}</td></tr></tbody></table></div>`;

  it('counts an SVG drawing, or HTML marks with no table, as drawn', () => {
    expect(drawnFigure(fig(1, svg))).toBe(true);
    expect(drawnFigure(fig(1, '<ul class="bar-list"><li><span class="pixel-bar__fill" style="width: 40%"></span>4 min</li></ul>'))).toBe(true);
    expect(drawnFigure(fig(1, `${svg}${table('x')}`))).toBe(true);
  });

  it('does not count a table, even with glyphs in its cells, a legend beside it or a drawing folded under it', () => {
    expect(drawnFigure(fig(1, table('x')))).toBe(false);
    expect(drawnFigure(fig(1, table(`${svg} yes`)))).toBe(false);
    expect(drawnFigure(fig(1, `${table('3')}<p class="heat-legend">${svg} 1 to 3</p>`))).toBe(false);
    expect(drawnFigure(fig(1, `${table('3')}<details><summary>s</summary>${svg}</details>`))).toBe(false);
  });

  it('fails a generated page whose numbered figures are all tables, and leaves prose pages alone', () => {
    const files = cleanSite();
    files['guide/index.html'] = files['guide/index.html']!.replace('page--prose', 'page--listing page--with-sidebar').replace('</body>', `${fig(1, table('x'))}</body>`);
    files['guide/index.md'] = '# Guide\n\n**Figure: F1.** c\n';
    expect(problems(files, ['listing'])).toEqual(['[drawn] /guide/ [listing]: none of its 1 numbered figure(s) is drawn; each is only a table']);
    files['guide/index.html'] = files['guide/index.html']!.replace('page--listing', 'page--prose');
    expect(problems(files)).toEqual([]);
    files['guide/index.html'] = files['guide/index.html']!.replace('page--prose', 'page--listing').replace('</body>', `${fig(2, svg)}</body>`);
    files['guide/index.md'] += '\n**Figure: F2.** c\n';
    expect(problems(files, ['listing'])).toEqual([]);
  });

  it('fails a page whose body names no template, and a drawn template no built page uses', () => {
    const files = cleanSite();
    files['guide/index.html'] = files['guide/index.html']!.replace('<body class="page page--prose">', '<body class="page page--with-sidebar">');
    expect(problems(files)).toEqual(['[drawn] /guide/: its body has no page--<template> class, so no check knows its template']);
    expect(problems(cleanSite(), ['listing'])).toEqual(['[drawn] DRAWN_TEMPLATES lists "listing", which no built page uses']);
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

describe('check-dist.mjs: the data API', () => {
  it('fails an enum value with no file, and a file the OpenAPI document does not describe', () => {
    const s = cleanSite();
    delete s['api/v1/things/b.json'];
    s['api/v1/things/c.json'] = '{}';
    expect(problems(s)).toEqual([
      '[api] openapi.json describes /api/v1/things/b.json, which is not a file in dist',
      '[api] /api/v1/things/c.json is in dist but openapi.json does not describe it',
    ]);
  });

  it('fails a path parameter with no enum, a JSON file that does not parse, and an OpenAPI 3.0 document', () => {
    const s = cleanSite();
    const doc = JSON.parse(s['openapi.json']!);
    doc.openapi = '3.0.3';
    delete doc.paths['/api/v1/things/{id}.json'].get.parameters[0].schema.enum;
    s['openapi.json'] = JSON.stringify(doc);
    s['api/v1/index.json'] = '{';
    const p = problems(s);
    expect(p.slice(0, 2)).toEqual(['[api] openapi.json: openapi is 3.0.3, not 3.1.x', '[api] openapi.json: /api/v1/things/{id}.json has no enum for {id}']);
    expect(p).toContain('[api] /api/v1/things/a.json is in dist but openapi.json does not describe it');
    expect(p.some((l) => l.startsWith('[api] api/v1/index.json is not valid JSON'))).toBe(true);
  });

  it('fails an api-catalog link that does not resolve, and a missing api-catalog header', () => {
    const s = cleanSite();
    s['.well-known/api-catalog'] = s['.well-known/api-catalog']!.replace(`${O}/guide/`, `${O}/developers/`);
    s['_headers'] = '/*.md\n  Content-Type: text/markdown\n';
    expect(problems(s)).toEqual([
      `[api] .well-known/api-catalog: service-doc ${O}/developers/ does not resolve to a file in dist`,
      '[api] _headers does not serve /.well-known/api-catalog as application/linkset+json; profile="https://www.rfc-editor.org/info/rfc9727"',
    ]);
  });

  it('fails when openapi.json or the api-catalog is missing', () => {
    const s = cleanSite();
    delete s['openapi.json'];
    delete s['.well-known/api-catalog'];
    expect(problems(s)).toEqual(['[api] openapi.json is missing from dist', '[api] .well-known/api-catalog is missing from dist']);
  });
});
