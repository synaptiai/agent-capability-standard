// Checks on the finished site in dist/, run last in `npm run build`, after
// Pagefind has written its files. It reads only dist/, so it does not share
// code with the route table that produced the pages:
// - links: every internal href and src (root-relative, relative, or an
//   absolute URL on the site's own origin), every <meta> content that is a URL
//   on the site's origin (og:image), and every Markdown link in the Markdown
//   copies, the llms.txt files, llms-full.txt, agents.md and llms.md names a
//   file in dist/ (or a path agent-contract.ts lists as served elsewhere), a page directory with an
//   index.html, or a _redirects source; every #fragment on an HTML target
//   names an id (or a name) on that page;
// - md-links: no internal link ends in .md, other than a link to a page's
//   Markdown copy (<page>/index.md next to that page's index.html) or to
//   /agents.md or /llms.md;
// - copies: every page has a Markdown copy, every copy has a page, and the
//   llms.txt files (the root one and one per section) list exactly the
//   copies, each section's once, in its own file (the root may name a copy
//   in its prose and in its list);
// - sitemap: the sitemap lists exactly the HTML pages, the 404 page aside;
// - figures: every numbered figure on a page ("Fig n") has a
//   "**Figure: {title}.**" block in the page's Markdown copy, and the copy has
//   no block for a figure the page does not draw (visual spec 6.1);
// - drawn: every page of a generated template (home, capability, layer,
//   workflow, domain, edge types, diagnostics, the section indexes, schemas
//   and the Standard) has at least one numbered figure that is drawn, not
//   only a table (DRAWN_TEMPLATES, drawnFigure());
// - legends: no legend or key on a page draws the same glyph (or glyph pair) for two
//   different entries;
// - review: no built file outside the review pages (dist/_review/) points at
//   them, so removing that folder before deploying leaves nothing dangling;
// - api: openapi.json is OpenAPI 3.1, its paths (each parameter expanded by
//   its enum) are exactly the JSON files under api/v1/, every one of those
//   parses, the api-catalog is a linkset whose links resolve, and _headers
//   gives the api-catalog its RFC 9727 media type.
// Paths are compared with the case they have in dist/, as the host compares
// them, even on a case-insensitive disk.
// The heading-id check (rendered ids equal github-slugger run on the source)
// needs the sources, so it runs in the astro:build:done hook in astro.config.mjs.
//
// Run: node scripts/check-dist.mjs [path/to/dist]
import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { FUNCTION_PATHS, LLMS_TXT_PATH, PENDING_PATHS, ROOT_MARKDOWN, SECTION_LLMS } from '../src/lib/agent-contract.ts';
import { SITE_ORIGIN } from '../src/lib/origin.ts';
import { REVIEW_DIR } from '../src/lib/review.ts';
import { stripComments, stripTags } from '../src/lib/strip.ts';
import { API_BASE, API_CATALOG_PATH, API_CATALOG_PROFILE, OPENAPI_PATH } from '../src/lib/api-paths.ts';
import { isMain } from './is-main.mjs';
import { bodyClasses, templateOf } from './page-template.mjs';

export const NOT_FOUND_PAGE = '404.html';
const COPY = 'index.md';

/**
 * Every file under `dir`, relative, with forward slashes, sorted. The review
 * pages (dist/_review/) are left out: they are not routes and are never deployed.
 */
export function walk(dir, base = dir) {
  const out = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory() && dir === base && e.name === REVIEW_DIR) continue;
    if (e.isDirectory()) out.push(...walk(p, base));
    else out.push(path.relative(base, p).split(path.sep).join('/'));
  }
  return out.sort();
}

/** URL path of an HTML file: `a/b/index.html` -> `/a/b/`, `x.html` -> `/x.html`. */
export function pageUrl(file) {
  return file === 'index.html' ? '/' : file.endsWith('/index.html') ? `/${file.slice(0, -'index.html'.length)}` : `/${file}`;
}

const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", '#39': "'" };

export function decodeEntities(s) {
  return s.replace(/&(#x[0-9a-f]+|#[0-9]+|[a-z]+);/gi, (m, e) => {
    if (e[0] === '#') return String.fromCodePoint(e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10));
    return ENTITIES[e.toLowerCase()] ?? m;
  });
}

function safeDecode(s) {
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
}

/** The opening tags of a page, with script and style bodies and comments removed. */
function tags(html) {
  const bare = stripComments(html)
    .replace(/(<script\b[^>]*>)[\s\S]*?<\/script>/gi, '$1')
    .replace(/(<style\b[^>]*>)[\s\S]*?<\/style>/gi, '$1');
  return bare.match(/<[a-zA-Z][^>]*>/g) ?? [];
}

/**
 * Every href and src value in a page's tags, and every <meta> content that is
 * a URL on `origin` (og:image and the like), entity-decoded.
 */
export function linkValues(html, origin = SITE_ORIGIN) {
  const out = [];
  for (const tag of tags(html)) {
    for (const m of tag.matchAll(/\s(href|src)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/gi)) {
      out.push(decodeEntities(m[2] ?? m[3] ?? m[4] ?? ''));
    }
    if (/^<meta\b/i.test(tag)) {
      for (const m of tag.matchAll(/\scontent\s*=\s*(?:"([^"]*)"|'([^']*)')/gi)) {
        const v = decodeEntities(m[1] ?? m[2] ?? '').trim();
        if (v === origin || v.startsWith(`${origin}/`)) out.push(v);
      }
    }
  }
  return out;
}

/**
 * Every link target in a Markdown text: inline links and images
 * `[text](target "title")` and reference definitions `[id]: target`. Fenced
 * code blocks and inline code spans are skipped.
 */
export function markdownLinkValues(md) {
  const out = [];
  let fence = null;
  for (const line of md.split('\n')) {
    const f = line.match(/^\s{0,3}(`{3,}|~{3,})/);
    if (f) {
      if (fence === null) fence = f[1];
      else if (f[1][0] === fence[0] && f[1].length >= fence.length) fence = null;
      continue;
    }
    if (fence !== null) continue;
    const text = line.replace(/(`+)[\s\S]*?\1/g, '');
    for (const m of text.matchAll(/\]\(\s*(?:<([^>]*)>|([^)\s]+))/g)) out.push(m[1] ?? m[2]);
    const def = text.match(/^\s{0,3}\[[^\]]+\]:\s*<?([^\s>]+)/);
    if (def) out.push(def[1]);
  }
  return out;
}

/** Every id and name value in a page's tags. */
export function anchorIds(html) {
  const ids = new Set();
  for (const tag of tags(html)) {
    for (const m of tag.matchAll(/\s(?:id|name)\s*=\s*(?:"([^"]*)"|'([^']*)')/gi)) ids.add(decodeEntities(m[1] ?? m[2] ?? ''));
  }
  return ids;
}

/**
 * An internal link as { path, fragment } with the path absolute from the site
 * root, or null for a link to somewhere else (another origin, mailto:, data:…).
 */
export function internalTarget(value, fromUrl, origin = SITE_ORIGIN) {
  const v = value.trim();
  if (v === '' || v.startsWith('//')) return v === '' ? { path: fromUrl, fragment: null } : null;
  let rest;
  if (v.startsWith(`${origin}/`) || v === origin) rest = v.slice(origin.length) || '/';
  else if (/^[a-z][a-z0-9+.-]*:/i.test(v)) return null;
  else rest = v;
  const hash = rest.indexOf('#');
  const fragment = hash === -1 ? null : safeDecode(rest.slice(hash + 1));
  let p = hash === -1 ? rest : rest.slice(0, hash);
  p = p.replace(/\?.*$/, '');
  if (p === '') return { path: fromUrl, fragment };
  const resolved = new URL(p, `https://site.invalid${fromUrl}`).pathname;
  return { path: safeDecode(resolved), fragment };
}

/** Sources in a Cloudflare _redirects file. */
export function redirectSources(text) {
  return new Set(
    text
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l && !l.startsWith('#'))
      .map((l) => l.split(/\s+/)[0]),
  );
}

/**
 * The dist file a URL path serves, or null. `files` is the set of dist paths
 * (exact case). A directory path serves its index.html.
 */
export function servedFile(urlPath, files) {
  const rel = urlPath.replace(/^\//, '');
  if (rel === '' || rel.endsWith('/')) {
    const f = `${rel}index.html`;
    return files.has(f) ? f : null;
  }
  if (files.has(rel)) return rel;
  return null;
}

/**
 * True when an internal path names the place of a page's Markdown copy:
 * `/a/b/index.md` where `/a/b/index.html` exists. Whether the copy itself
 * exists is the link check's business.
 */
export function isCopyLink(urlPath, files) {
  if (!urlPath.endsWith(`/${COPY}`)) return false;
  return files.has(`${urlPath.slice(1, -COPY.length)}index.html`);
}

/** True for a section's llms.txt: `<section>/llms.txt`. */
export function isSectionLlms(f) {
  return new RegExp(`^[^/]+/${SECTION_LLMS.replace('.', '\\.')}$`).test(f);
}

/** True for a Markdown file whose links the link check reads. */
function isMarkdownWithLinks(f) {
  return (
    f === COPY ||
    f.endsWith(`/${COPY}`) ||
    f === 'llms-full.txt' ||
    f === LLMS_TXT_PATH.slice(1) ||
    isSectionLlms(f) ||
    ROOT_MARKDOWN.includes(`/${f}`)
  );
}

/**
 * True for a link the build of this part of the site cannot resolve on its
 * own: a path served by a function, or one another part of the build
 * produces (agent-contract.ts), while no file in dist serves it.
 */
export function isAcceptedMissing(urlPath) {
  return FUNCTION_PATHS.includes(urlPath) || PENDING_PATHS.includes(urlPath);
}

/**
 * Link problems on every HTML file, Markdown copy and llms-full.txt in a dist
 * listing. `read(file)` returns a file's text. Returns { links, mdLinks,
 * checked } where the first two are problem lines, each reported once.
 */
export function checkLinks(fileList, read, redirects = new Set()) {
  const files = new Set(fileList);
  const sources = fileList.filter((f) => f.endsWith('.html') || isMarkdownWithLinks(f));
  const idCache = new Map();
  const idsOf = (f) => {
    if (!idCache.has(f)) idCache.set(f, anchorIds(read(f)));
    return idCache.get(f);
  };
  const links = new Set();
  const mdLinks = new Set();
  let checked = 0;
  for (const f of sources) {
    const from = f.endsWith('.html') ? pageUrl(f) : `/${f}`;
    const values = f.endsWith('.html') ? linkValues(read(f)) : markdownLinkValues(read(f));
    for (const value of values) {
      const t = internalTarget(value, from);
      if (t === null) continue;
      checked += 1;
      if (/\.md$/i.test(t.path) && !isCopyLink(t.path, files) && !ROOT_MARKDOWN.includes(t.path) && !isAcceptedMissing(t.path)) {
        mdLinks.add(`${from}: links to ${value}, a .md file that is not a page's Markdown copy`);
        continue;
      }
      const target = servedFile(t.path, files);
      if (target === null) {
        if (!redirects.has(t.path) && !isAcceptedMissing(t.path)) links.add(`${from}: ${value} does not resolve to a file in dist`);
        continue;
      }
      if (t.fragment !== null && t.fragment !== '' && target.endsWith('.html') && !idsOf(target).has(t.fragment)) {
        links.add(`${from}: ${value} names #${t.fragment}, which is not an id on ${pageUrl(target)}`);
      }
    }
  }
  return { links: [...links], mdLinks: [...mdLinks], checked };
}

/** URL paths of the HTML pages: every .html file but the 404 page. */
export function htmlPages(fileList) {
  return fileList.filter((f) => f.endsWith('.html') && f !== NOT_FOUND_PAGE).map(pageUrl);
}

/** The URL paths a sitemap lists, for <loc> values on `origin`. Others are returned in `foreign`. */
export function sitemapPaths(xml, origin = SITE_ORIGIN) {
  const paths = [];
  const foreign = [];
  for (const m of xml.matchAll(/<loc>\s*([^<]*?)\s*<\/loc>/g)) {
    const loc = decodeEntities(m[1]);
    if (loc.startsWith(`${origin}/`)) paths.push(loc.slice(origin.length));
    else foreign.push(loc);
  }
  return { paths, foreign };
}

/** URL paths of the Markdown copies an llms.txt links to. Links elsewhere are returned in `other`. */
export function llmsTxtCopies(text, origin = SITE_ORIGIN) {
  const copies = [];
  const other = [];
  for (const m of text.matchAll(/\]\(([^)\s]+)\)/g)) {
    const url = m[1];
    if (url.startsWith(`${origin}/`) && url.endsWith(`/${COPY}`)) copies.push(url.slice(origin.length));
    else other.push(url);
  }
  return { copies, other };
}

function setDiff(a, b) {
  const bs = new Set(b);
  return [...new Set(a)].filter((x) => !bs.has(x));
}

function duplicates(list) {
  const seen = new Set();
  return [...new Set(list.filter((x) => (seen.has(x) ? true : (seen.add(x), false))))];
}

/**
 * Every page has a Markdown copy and every copy has a page. The llms.txt
 * files list the copies: each section's llms.txt (`<section>/llms.txt`)
 * lists its copies once, no copy is in two of them, the root llms.txt links
 * every section's file, and together the files list every copy and nothing
 * that is not one. (Whether the root's other links resolve is the link
 * check's business.)
 */
export function checkCopies(fileList, read) {
  const problems = [];
  const files = new Set(fileList);
  const pages = htmlPages(fileList).filter((u) => u.endsWith('/'));
  const other = htmlPages(fileList).filter((u) => !u.endsWith('/'));
  for (const u of other) problems.push(`${u}: an HTML file that is not a page directory, so it has no Markdown copy`);
  for (const u of pages) if (!files.has(`${u.slice(1)}${COPY}`)) problems.push(`${u}: no Markdown copy at ${u}${COPY}`);
  const copies = fileList.filter((f) => f === COPY || f.endsWith(`/${COPY}`)).map((f) => `/${f}`);
  for (const c of copies) if (!files.has(`${c.slice(1, -COPY.length)}index.html`)) problems.push(`${c}: a Markdown copy with no page`);
  const root = llmsTxtCopies(read(LLMS_TXT_PATH.slice(1)));
  const sections = fileList.filter(isSectionLlms);
  const owner = new Map();
  for (const f of sections) {
    const listed = llmsTxtCopies(read(f));
    for (const c of duplicates(listed.copies)) problems.push(`${f} lists ${c} more than once`);
    for (const c of new Set(listed.copies)) {
      if (owner.has(c)) problems.push(`${c} is listed by both ${owner.get(c)} and ${f}`);
      else owner.set(c, f);
    }
    if (!root.other.includes(`${SITE_ORIGIN}/${f}`)) problems.push(`llms.txt does not link ${f}`);
  }
  // A copy another part of the build makes may be missing from this build.
  const listed = [...owner.keys(), ...root.copies.filter((c) => copies.includes(c) || !isAcceptedMissing(c))];
  for (const c of setDiff(copies, listed)) problems.push(`no llms.txt lists ${c}`);
  for (const c of setDiff(listed, copies)) problems.push(`an llms.txt lists ${c}, which is not in dist`);
  return problems;
}

/** The sitemap lists exactly the HTML pages, the 404 page aside. */
export function checkSitemap(fileList, xml) {
  const problems = [];
  const pages = htmlPages(fileList);
  const { paths, foreign } = sitemapPaths(xml);
  for (const u of setDiff(pages, paths)) problems.push(`sitemap.xml does not list ${u}`);
  for (const u of setDiff(paths, pages)) problems.push(`sitemap.xml lists ${u}, which is not an HTML page in dist`);
  for (const u of duplicates(paths)) problems.push(`sitemap.xml lists ${u} more than once`);
  for (const u of foreign) problems.push(`sitemap.xml lists ${u}, which is not on ${SITE_ORIGIN}`);
  return problems;
}

// ------------------------------------------------------------ figures and legends

const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr']);

/**
 * The element whose start tag begins at `start` in `html`: its tag name, the
 * offset just after its start tag and the offset of its end tag (both
 * `html.length` when it is never closed).
 */
function elementAt(html, start) {
  const tag = /^<([a-zA-Z][\w-]*)\b[^>]*?(\/?)>/.exec(html.slice(start));
  if (!tag) return null;
  const name = tag[1].toLowerCase();
  const open = start + tag[0].length;
  if (VOID.has(name) || tag[2] === '/') return { name, open, close: open, end: open };
  const re = new RegExp(`<${name}\\b[^>]*?(/?)>|</${name}\\s*>`, 'gi');
  re.lastIndex = open;
  let depth = 1;
  for (let m = re.exec(html); m; m = re.exec(html)) {
    if (m[0][1] === '/') depth -= 1;
    else if (m[1] !== '/') depth += 1;
    if (depth === 0) return { name, open, close: m.index, end: m.index + m[0].length };
  }
  return { name, open, close: html.length, end: html.length };
}

/** The child elements of the element at `start`, as [start, end] offsets. */
function childElements(html, start) {
  const el = elementAt(html, start);
  const out = [];
  const re = /<([a-zA-Z][\w-]*)\b/g;
  re.lastIndex = el.open;
  for (let m = re.exec(html); m && m.index < el.close; m = re.exec(html)) {
    const c = elementAt(html, m.index);
    out.push([m.index, c.end]);
    re.lastIndex = c.end;
  }
  return out;
}

const plainText = (html) => decodeEntities(stripTags(html)).replace(/\s+/g, ' ').trim();

/**
 * The numbered figures of a page, in order: each `<figure>` whose eyebrow
 * reads "Fig n", with its name (the text of the element its aria-labelledby
 * names, or its aria-label).
 */
export function pageFigures(html) {
  const out = [];
  for (const m of html.matchAll(/<figure\b[^>]*>/g)) {
    const el = elementAt(html, m.index);
    const inner = html.slice(el.open, el.close);
    // The figure's own eyebrow comes before any figure nested in it.
    const own = inner.split(/<figure\b/)[0];
    const n = /<p\b[^>]*class="[^"]*eyebrow[^"]*"[^>]*>\s*Fig (\d+)\s*<\/p>/.exec(own);
    if (!n) continue;
    const by = /\saria-labelledby="([^"]+)"/.exec(m[0])?.[1];
    let title = null;
    if (by) {
      const at = html.search(new RegExp(`<[a-zA-Z][\\w-]*\\b[^>]*\\sid="${by.split(' ')[0].replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"`));
      if (at !== -1) {
        const t = elementAt(html, at);
        title = plainText(html.slice(t.open, t.close));
      }
    }
    if (title === null) {
      const label = /\saria-label="([^"]*)"/.exec(m[0])?.[1];
      title = label === undefined ? null : decodeEntities(label).trim();
    }
    out.push({ n: Number(n[1]), title });
  }
  return out;
}

/**
 * The titles of the "**Figure: {title}.**" blocks of a Markdown copy, as
 * plain text (code spans and backslash escapes undone). A block may sit in a
 * list item or a block quote.
 */
export function copyFigureTitles(md) {
  const text = md.replace(/^( {0,3})(`{3,}|~{3,})[^\n]*\n[\s\S]*?^\1\2[^\n]*$/gm, '');
  return [...text.matchAll(/^[ \t>]*\*\*Figure: (.+?)\.\*\*(?= |$)/gm)].map((m) =>
    m[1].replace(/`+ ?([^`]*?) ?`+/g, '$1').replace(/\\([\\`*_{}\[\]()#+\-.!|<>])/g, '$1').replace(/\s+/g, ' ').trim(),
  );
}

/** Each numbered figure of every page has a figure block in its Markdown copy, and each block a figure. */
export function checkFigureCopies(fileList, read) {
  const files = new Set(fileList);
  const problems = [];
  for (const u of htmlPages(fileList)) {
    const copy = `${u.slice(1)}${COPY}`;
    if (!files.has(copy)) continue; // checkCopies reports it
    const figs = pageFigures(read(`${u.slice(1)}index.html`));
    const blocks = copyFigureTitles(read(copy));
    for (const f of figs) if (f.title === null) problems.push(`${u}: Fig ${f.n} has no accessible name`);
    const left = [...blocks];
    const unmatched = [];
    for (const f of figs.filter((x) => x.title !== null)) {
      const i = left.indexOf(f.title);
      if (i === -1) unmatched.push(f);
      else left.splice(i, 1);
    }
    for (const f of unmatched) problems.push(`${u}: Fig ${f.n} "${f.title}" has no "**Figure: ${f.title}.**" block in ${u}${COPY}`);
    for (const b of left) problems.push(`${u}${COPY}: the block "**Figure: ${b}.**" names no figure on the page`);
  }
  return problems;
}

/**
 * The page templates whose every page needs a drawn figure: the generated
 * pages and the Standard. Prose, RFC and skill pages draw from their own
 * sources and are left to the figure-gap sweep (scripts/check-runs.mjs).
 */
export const DRAWN_TEMPLATES = [
  'home',
  'capability',
  'capabilities-index',
  'layer',
  'workflow',
  'workflows-index',
  'domain',
  'domains-index',
  'edge-types',
  'diagnostics',
  'listing',
  'rfcs-index',
  'schemas',
  'spec',
  'developers',
];

/** A page's template, from its body's `page--<template>` class. */
export function pageTemplate(html) {
  return templateOf(bodyClasses(html));
}

/** `html` with every element whose tag is `name`, or whose class matches `cls`, cut out. */
function without(html, { name, cls }) {
  let out = html;
  for (;;) {
    const re = name ? new RegExp(`<${name}\\b`, 'i') : new RegExp(`<[a-zA-Z][\\w-]*\\b[^>]*\\sclass="[^"]*${cls}[^"]*"`);
    const m = re.exec(out);
    if (!m) return out;
    const el = elementAt(out, m.index);
    out = out.slice(0, m.index) + out.slice(el.end);
  }
}

/**
 * Whether a numbered figure is drawn: its drawing, less any folded
 * <details> and any legend or key, is not a table, or holds an SVG outside
 * its tables. A table with glyphs or heat fills in its cells is still a
 * table: the reader reads it row by row.
 */
export function drawnFigure(figureHtml) {
  const at = figureHtml.search(/<div\b[^>]*class="[^"]*\bfig__drawing\b/);
  if (at === -1) return false;
  const d = elementAt(figureHtml, at);
  let drawing = figureHtml.slice(d.open, d.close);
  drawing = without(drawing, { name: 'details' });
  drawing = without(drawing, { cls: '(?:legend|-key|__key)\\b' });
  if (!/<table\b/i.test(drawing)) return plainText(drawing) !== '' || /<svg\b/i.test(drawing);
  return /<svg\b/i.test(without(drawing, { name: 'table' }));
}

/**
 * Every page of a DRAWN_TEMPLATES template has a drawn numbered figure. A
 * page whose body names no template, and a DRAWN_TEMPLATES entry no built
 * page uses, are problems too: either would let a page skip the check.
 */
export function checkDrawnFigures(fileList, read, drawnTemplates = DRAWN_TEMPLATES) {
  const problems = [];
  const seen = new Set();
  for (const u of htmlPages(fileList)) {
    const html = read(`${u.slice(1)}index.html`);
    const t = pageTemplate(html);
    if (t === null) {
      problems.push(`${u}: its body has no page--<template> class, so no check knows its template`);
      continue;
    }
    seen.add(t);
    if (!drawnTemplates.includes(t)) continue;
    let numbered = 0;
    let drawn = 0;
    for (const m of html.matchAll(/<figure\b[^>]*>/g)) {
      const el = elementAt(html, m.index);
      const inner = html.slice(m.index, el.end);
      if (!/<p\b[^>]*class="[^"]*eyebrow[^"]*"[^>]*>\s*Fig \d+\s*<\/p>/.test(inner.split(/<figure\b/).slice(0, 2).join(''))) continue;
      numbered += 1;
      if (drawnFigure(inner)) drawn += 1;
    }
    if (drawn === 0) problems.push(`${u} [${t}]: none of its ${numbered} numbered figure(s) is drawn; each is only a table`);
  }
  for (const t of drawnTemplates) if (!seen.has(t)) problems.push(`DRAWN_TEMPLATES lists "${t}", which no built page uses`);
  return problems;
}

/**
 * No legend draws one glyph for two entries with different words. A legend
 * is an element with a class ending in "legend" or "key"; an entry is a child element
 * with at least one SVG, keyed by the marks of all its SVGs, so two glyph keys
 * that draw the same grid count as one glyph.
 */
export function checkLegends(fileList, read) {
  const problems = [];
  for (const f of fileList.filter((x) => x.endsWith('.html'))) {
    const html = read(f);
    for (const m of html.matchAll(/<([a-zA-Z][\w-]*)\b[^>]*\sclass="(?:[^"]*\s)?[\w-]*(?:legend|key)(?:\s[^"]*)?"[^>]*>/g)) {
      const name = /\saria-label="([^"]*)"/.exec(m[0])?.[1] ?? /class="([^"]*)"/.exec(m[0])[1];
      const words = new Map();
      for (const [a, b] of childElements(html, m.index)) {
        const item = html.slice(a, b);
        const svgs = item.match(/<svg\b[\s\S]*?<\/svg>/g);
        if (!svgs) continue;
        const key = svgs.map((s) => s.replace(/^<svg\b[^>]*>/, '').replace(/\s+/g, ' ')).join('|');
        const label = plainText(item.replace(/<svg\b[\s\S]*?<\/svg>/g, ''));
        const seen = words.get(key);
        if (seen === undefined) words.set(key, label);
        else if (seen !== label) problems.push(`${pageUrl(f)}: the legend "${decodeEntities(name)}" draws the same glyph for "${seen}" and "${label}"`);
      }
    }
  }
  return problems;
}

/** Built files outside the review pages that point at them. */
export function checkReviewLinks(fileList, read) {
  const re = new RegExp(`(^|["'(/=\\s])/?${REVIEW_DIR}/`);
  return fileList
    .filter((f) => /\.(html|md|txt|xml|json|js|css|webmanifest)$/.test(f) && !f.startsWith('pagefind/'))
    .filter((f) => re.test(read(f)))
    .map((f) => `${f} points at the review pages (/${REVIEW_DIR}/), which are not deployed`);
}

// ------------------------------------------------------------ data API

/**
 * The URL paths an OpenAPI document's paths stand for: a path with a
 * `{param}` becomes one path per value of that parameter's enum. A parameter
 * with no enum is a problem, because then no file list can be checked.
 */
export function openApiFilePaths(doc) {
  const paths = [];
  const problems = [];
  for (const [p, item] of Object.entries(doc.paths ?? {})) {
    const names = [...p.matchAll(/\{([^}]+)\}/g)].map((m) => m[1]);
    if (names.length === 0) {
      paths.push(p);
      continue;
    }
    if (names.length > 1) {
      problems.push(`openapi.json: ${p} has more than one path parameter`);
      continue;
    }
    const param = (item.get?.parameters ?? []).find((x) => x.in === 'path' && x.name === names[0]);
    const values = param?.schema?.enum;
    if (!Array.isArray(values) || values.length === 0) {
      problems.push(`openapi.json: ${p} has no enum for {${names[0]}}`);
      continue;
    }
    for (const v of values) paths.push(p.replace(`{${names[0]}}`, v));
  }
  return { paths, problems };
}

/** The data API in dist: the OpenAPI document, the JSON files, the api-catalog and its header. */
export function checkApi(fileList, read, redirects = new Set()) {
  const problems = [];
  const files = new Set(fileList);
  const parse = (f) => {
    try {
      return JSON.parse(read(f));
    } catch (e) {
      problems.push(`${f} is not valid JSON: ${e.message}`);
      return null;
    }
  };
  const apiDir = `${API_BASE.slice(1)}/`;
  const apiFiles = fileList.filter((f) => f.startsWith(apiDir));
  for (const f of apiFiles) if (!f.endsWith('.json')) problems.push(`${f}: a file under ${apiDir} that is not JSON`);
  const openapiFile = OPENAPI_PATH.slice(1);
  if (!files.has(openapiFile)) problems.push(`${openapiFile} is missing from dist`);
  else {
    const doc = parse(openapiFile);
    if (doc) {
      if (typeof doc.openapi !== 'string' || !/^3\.1\.\d+$/.test(doc.openapi)) problems.push(`${openapiFile}: openapi is ${doc.openapi}, not 3.1.x`);
      const { paths, problems: p } = openApiFilePaths(doc);
      problems.push(...p);
      const served = apiFiles.map((f) => `/${f}`);
      for (const u of setDiff(paths, served)) problems.push(`${openapiFile} describes ${u}, which is not a file in dist`);
      for (const u of setDiff(served, paths)) problems.push(`${u} is in dist but ${openapiFile} does not describe it`);
    }
  }
  for (const f of apiFiles.filter((x) => x.endsWith('.json'))) parse(f);
  const catalogFile = API_CATALOG_PATH.slice(1);
  if (!files.has(catalogFile)) problems.push(`${catalogFile} is missing from dist`);
  else {
    const cat = parse(catalogFile);
    if (cat && (!Array.isArray(cat.linkset) || cat.linkset.length === 0)) problems.push(`${catalogFile}: no linkset array`);
    for (const entry of cat?.linkset ?? []) {
      if (typeof entry.anchor !== 'string') problems.push(`${catalogFile}: a linkset entry has no anchor`);
      for (const [rel, targets] of Object.entries(entry)) {
        if (rel === 'anchor') continue;
        for (const t of Array.isArray(targets) ? targets : []) {
          const target = internalTarget(t.href ?? '', `/${catalogFile}`);
          if (target === null) continue;
          if (servedFile(target.path, files) === null && !redirects.has(target.path)) {
            problems.push(`${catalogFile}: ${rel} ${t.href} does not resolve to a file in dist`);
          }
        }
      }
    }
    const headers = files.has('_headers') ? read('_headers') : '';
    const block = headers.split(/\n(?=\S)/).find((b) => b.split('\n')[0].trim() === API_CATALOG_PATH) ?? '';
    const type = /^\s+Content-Type:\s*(.+)$/im.exec(block)?.[1]?.trim() ?? '';
    if (!type.startsWith('application/linkset+json') || !type.includes(`profile="${API_CATALOG_PROFILE}"`)) {
      problems.push(`_headers does not serve ${API_CATALOG_PATH} as application/linkset+json; profile="${API_CATALOG_PROFILE}"`);
    }
  }
  return problems;
}

function kb(bytes) {
  return `${(bytes / 1024).toFixed(1)} KB`;
}

/** Run every check on a dist directory. */
export function checkDistDir(distDir, { drawnTemplates = DRAWN_TEMPLATES } = {}) {
  const fileList = walk(distDir);
  const read = (f) => readFileSync(path.join(distDir, f), 'utf8');
  const size = (f) => statSync(path.join(distDir, f)).size;
  const has = new Set(fileList);
  const missing = ['sitemap.xml', 'llms.txt', 'llms-full.txt', 'pagefind/pagefind.js'].filter((f) => !has.has(f));
  const redirects = has.has('_redirects') ? redirectSources(read('_redirects')) : new Set();
  const { links, mdLinks, checked } = checkLinks(fileList, read, redirects);
  const problems = {
    files: missing.map((f) => `${f} is missing from dist`),
    links,
    'md-links': mdLinks,
    copies: has.has('llms.txt') ? checkCopies(fileList, read) : [],
    sitemap: has.has('sitemap.xml') ? checkSitemap(fileList, read('sitemap.xml')) : [],
    figures: checkFigureCopies(fileList, read),
    drawn: checkDrawnFigures(fileList, read, drawnTemplates),
    legends: checkLegends(fileList, read),
    review: checkReviewLinks(fileList, read),
    api: checkApi(fileList, read, redirects),
  };
  const sum = (list) => list.reduce((n, f) => n + size(f), 0);
  const htmlFiles = fileList.filter((f) => f.endsWith('.html'));
  const copies = fileList.filter((f) => f === COPY || f.endsWith(`/${COPY}`));
  const stats = {
    pages: htmlPages(fileList).length,
    checkedLinks: checked,
    htmlBytes: sum(htmlFiles),
    copyBytes: sum(copies),
    copies: copies.length,
    llmsBytes: has.has('llms.txt') ? size('llms.txt') : 0,
    sectionLlms: fileList.filter(isSectionLlms).length,
    llmsFullBytes: has.has('llms-full.txt') ? size('llms-full.txt') : 0,
    totalBytes: sum(fileList),
    files: fileList.length,
  };
  return { problems, stats };
}

export function formatStats(s) {
  return [
    `pages: ${s.pages} HTML pages (404 aside), ${kb(s.htmlBytes)} of HTML in all`,
    `Markdown copies: ${s.copies}, ${kb(s.copyBytes)}; llms.txt ${kb(s.llmsBytes)} and ${s.sectionLlms} section llms.txt files; llms-full.txt ${kb(s.llmsFullBytes)}`,
    `links: ${s.checkedLinks} internal links checked`,
    `dist: ${s.files} files, ${kb(s.totalBytes)}`,
  ];
}

if (isMain(import.meta.url)) {
  const dist = process.argv[2] ?? fileURLToPath(new URL('../dist', import.meta.url));
  const { problems, stats } = checkDistDir(dist);
  const lines = Object.entries(problems).flatMap(([check, list]) => list.map((p) => `[${check}] ${p}`));
  for (const l of formatStats(stats)) console.log(`check-dist: ${l}`);
  if (lines.length > 0) {
    console.error(`check-dist: ${lines.length} problem(s) in ${dist}:\n  ${lines.join('\n  ')}`);
    process.exit(1);
  }
  console.log(`check-dist: every check passed (${Object.keys(problems).join(', ')})`);
}
