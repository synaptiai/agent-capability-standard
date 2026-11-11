// Checks on the finished site in dist/, run last in `npm run build`, after
// Pagefind has written its files. It reads only dist/, so it does not share
// code with the route table that produced the pages:
// - links: every internal href and src (root-relative, relative, or an
//   absolute URL on the site's own origin), every <meta> content that is a URL
//   on the site's origin (og:image), and every Markdown link in the Markdown
//   copies and llms-full.txt names a file in dist/, a page directory with an
//   index.html, or a _redirects source; every #fragment on an HTML target
//   names an id (or a name) on that page;
// - md-links: no internal link ends in .md, other than a link to a page's
//   Markdown copy (<page>/index.md next to that page's index.html);
// - copies: every page has a Markdown copy, every copy has a page, and
//   llms.txt lists exactly the copies;
// - sitemap: the sitemap lists exactly the HTML pages, the 404 page aside.
// Paths are compared with the case they have in dist/, as the host compares
// them, even on a case-insensitive disk.
// The heading-id check (rendered ids equal github-slugger run on the source)
// needs the sources, so it runs in the astro:build:done hook in astro.config.mjs.
//
// Run: node scripts/check-dist.mjs [path/to/dist]
import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { SITE_ORIGIN } from '../src/lib/origin.ts';

export const NOT_FOUND_PAGE = '404.html';
const COPY = 'index.md';

/** Every file under `dir`, relative, with forward slashes, sorted. */
export function walk(dir, base = dir) {
  const out = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
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
  const bare = html
    .replace(/<!--[\s\S]*?-->/g, '')
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

/** True for a Markdown file whose links the link check reads. */
function isMarkdownWithLinks(f) {
  return f === COPY || f.endsWith(`/${COPY}`) || f === 'llms-full.txt';
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
      if (/\.md$/i.test(t.path) && !isCopyLink(t.path, files)) {
        mdLinks.add(`${from}: links to ${value}, a .md file that is not a page's Markdown copy`);
        continue;
      }
      const target = servedFile(t.path, files);
      if (target === null) {
        if (!redirects.has(t.path)) links.add(`${from}: ${value} does not resolve to a file in dist`);
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

/** URL paths of the Markdown copies llms.txt links to. Links elsewhere are returned in `other`. */
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

/** Every page has a Markdown copy, every copy has a page, and llms.txt lists exactly the copies. */
export function checkCopies(fileList, llmsTxt) {
  const problems = [];
  const files = new Set(fileList);
  const pages = htmlPages(fileList).filter((u) => u.endsWith('/'));
  const other = htmlPages(fileList).filter((u) => !u.endsWith('/'));
  for (const u of other) problems.push(`${u}: an HTML file that is not a page directory, so it has no Markdown copy`);
  for (const u of pages) if (!files.has(`${u.slice(1)}${COPY}`)) problems.push(`${u}: no Markdown copy at ${u}${COPY}`);
  const copies = fileList.filter((f) => f === COPY || f.endsWith(`/${COPY}`)).map((f) => `/${f}`);
  for (const c of copies) if (!files.has(`${c.slice(1, -COPY.length)}index.html`)) problems.push(`${c}: a Markdown copy with no page`);
  const listed = llmsTxtCopies(llmsTxt);
  for (const c of setDiff(copies, listed.copies)) problems.push(`llms.txt does not list ${c}`);
  for (const c of setDiff(listed.copies, copies)) problems.push(`llms.txt lists ${c}, which is not in dist`);
  for (const c of duplicates(listed.copies)) problems.push(`llms.txt lists ${c} more than once`);
  for (const u of listed.other) problems.push(`llms.txt links to ${u}, which is not a Markdown copy on the site`);
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

function kb(bytes) {
  return `${(bytes / 1024).toFixed(1)} KB`;
}

/** Run every check on a dist directory. */
export function checkDistDir(distDir) {
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
    copies: has.has('llms.txt') ? checkCopies(fileList, read('llms.txt')) : [],
    sitemap: has.has('sitemap.xml') ? checkSitemap(fileList, read('sitemap.xml')) : [],
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
    llmsFullBytes: has.has('llms-full.txt') ? size('llms-full.txt') : 0,
    totalBytes: sum(fileList),
    files: fileList.length,
  };
  return { problems, stats };
}

export function formatStats(s) {
  return [
    `pages: ${s.pages} HTML pages (404 aside), ${kb(s.htmlBytes)} of HTML in all`,
    `Markdown copies: ${s.copies}, ${kb(s.copyBytes)}; llms.txt ${kb(s.llmsBytes)}; llms-full.txt ${kb(s.llmsFullBytes)}`,
    `links: ${s.checkedLinks} internal links checked`,
    `dist: ${s.files} files, ${kb(s.totalBytes)}`,
  ];
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
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
