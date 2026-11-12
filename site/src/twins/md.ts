// Helpers for writing the Markdown copies of pages (each page's copy is at
// <route>index.md). Links between pages point at the other page's copy, as an
// absolute URL, so an agent that reads one copy can follow links to others.
import type { Definition, Heading, Image, Link, Root } from 'mdast';
import { visit } from 'unist-util-visit';
import { parseMarkdown, stripFrontmatter } from '../lib/anchors';
import { mermaidTwinEdits } from '../lib/mermaid/twin';
import { SITE_ORIGIN, repoResolver } from '../lib/links';
import { COMMIT_SHA, githubBlobUrl } from '../lib/repo';
import { ROUTES } from '../lib/routes';

const URLS: ReadonlySet<string> = new Set(ROUTES.map((r) => r.url));

/** The absolute URL of a page's Markdown copy: `/a/b/` -> `https://…/a/b/index.md`. */
export function mdUrl(pageUrl: string): string {
  const [path, frag] = pageUrl.split('#');
  if (!URLS.has(path!)) throw new Error(`twins: ${pageUrl} is not a route`);
  return `${SITE_ORIGIN}${path}index.md${frag === undefined ? '' : `#${frag}`}`;
}

/** A Markdown link to another page's copy. */
export function mdLink(text: string, pageUrl: string): string {
  return `[${text}](${mdUrl(pageUrl)})`;
}

/** Text safe inside a table cell: no line breaks, pipes escaped. */
export function cell(text: string): string {
  return text.replace(/\s*\n\s*/g, ' ').replace(/(?<!\\)\|/g, '\\|').trim();
}

/**
 * An inline code span that reads back as exactly `text`: its fence is one
 * backtick longer than any backtick run inside, and it is padded with a space
 * on each side (which CommonMark strips) when the text has a backtick or
 * begins or ends with a space.
 */
export function code(text: string): string {
  const longest = Math.max(0, ...[...text.matchAll(/`+/g)].map((m) => m[0].length));
  const ticks = '`'.repeat(longest + 1);
  const pad = /^ *$/.test(text) ? '' : longest > 0 || /^ | $/.test(text) ? ' ' : '';
  return `${ticks}${pad}${text}${pad}${ticks}`;
}

export function table(headers: string[], rows: string[][]): string {
  const line = (cells: string[]) => `| ${cells.join(' | ')} |`;
  return [line(headers), line(headers.map(() => '---')), ...rows.map(line)].join('\n');
}

/** A fenced block whose fence is longer than any backtick run inside it. */
export function fence(lang: string, body: string): string {
  const longest = Math.max(2, ...[...body.matchAll(/`+/g)].map((m) => m[0].length));
  const f = '`'.repeat(longest + 1);
  return `${f}${lang}\n${body.replace(/\n+$/, '')}\n${f}`;
}

/** The line under the H1 that says where a page comes from. */
export function sourceLine(source: string): string {
  return `Source: [${source}](${githubBlobUrl(source)}), commit ${COMMIT_SHA.slice(0, 12)}.`;
}

export function generatedLine(sources: string[]): string {
  const list = sources.map((s) => `[${s}](${githubBlobUrl(s)})`).join(', ');
  return sources.length === 0
    ? `Generated from the repository at commit ${COMMIT_SHA.slice(0, 12)}.`
    : `Generated from ${list} at commit ${COMMIT_SHA.slice(0, 12)}.`;
}

/** Join blocks with one blank line between them, dropping empty ones. */
export function blocks(...parts: (string | null | undefined | false)[]): string {
  return `${parts.filter((p): p is string => typeof p === 'string' && p.trim() !== '').map((p) => p.trim()).join('\n\n')}\n`;
}

interface Edit {
  start: number;
  end: number;
  text: string;
}

export interface CopyOptions {
  /** Add this many `#` to every ATX heading, for a source shown inside another page. */
  shiftHeadings?: number;
  /** Put a `Source:` line after the H1 (or at the top, when there is no H1). */
  sourceNote?: boolean;
  /** Title for an H1 to add when the source has none. */
  title?: string;
}

/**
 * The Markdown copy of a repository Markdown file: the source with its
 * frontmatter removed and every link, image and link definition rewritten by
 * the shared resolver in `md` mode. Only the link targets change; the rest of
 * the text is kept byte for byte. A link that does not resolve throws, as it
 * fails the HTML build.
 */
export function markdownCopy(repoPath: string, text: string, options: CopyOptions = {}): string {
  const body = stripFrontmatter(text).replace(/^\s+/, '');
  const tree: Root = parseMarkdown(body);
  const resolve = repoResolver();
  const edits: Edit[] = [];
  const problems: string[] = [];

  visit(tree, (node) => {
    if (node.type !== 'link' && node.type !== 'image' && node.type !== 'definition') return;
    const n = node as Link | Image | Definition;
    const start = n.position?.start.offset;
    const end = n.position?.end.offset;
    if (start === undefined || end === undefined) return;
    const r = resolve(repoPath, n.url, 'md');
    if (!r.ok) {
      problems.push(`${repoPath}:${n.position?.start.line}: ${n.url} -> ${r.reason}`);
      return;
    }
    if (r.url === n.url) return;
    // The destination comes after the link text (or the label of a definition).
    let from = start;
    if (n.type === 'link' && n.children.length > 0) from = n.children.at(-1)!.position?.end.offset ?? start;
    const slice = body.slice(from, end);
    const marker = n.type === 'definition' ? slice.indexOf(']:') : slice.indexOf('](');
    const at = marker === -1 ? -1 : slice.indexOf(n.url, marker);
    if (at === -1) {
      // Autolinks (<https://…>) and destinations written with escapes are left alone
      // only when they need no rewrite; anything else must be rewritten.
      problems.push(`${repoPath}:${n.position?.start.line}: cannot find the destination ${n.url} in the source`);
      return;
    }
    edits.push({ start: from + at, end: from + at + n.url.length, text: r.url });
  });

  // Each mermaid fence stays, followed by its text version.
  edits.push(...mermaidTwinEdits(tree, body));

  if (problems.length > 0) throw new Error(`twins: links in ${repoPath} did not resolve:\n  ${problems.join('\n  ')}`);

  let h1: Heading | undefined;
  visit(tree, 'heading', (h: Heading) => {
    if (!h1 && h.depth === 1) h1 = h;
    const s = h.position?.start.offset;
    if (options.shiftHeadings && s !== undefined && body[s] === '#') {
      edits.push({ start: s, end: s, text: '#'.repeat(Math.min(options.shiftHeadings, 6 - h.depth)) });
    }
  });

  const note = options.sourceNote ? `\n\n${sourceLine(repoPath)}` : '';
  let out = body;
  const h1End = h1?.position?.end.offset;
  if (note && h1End !== undefined) edits.push({ start: h1End, end: h1End, text: note });
  // Apply from the end so earlier offsets stay valid.
  edits.sort((a, b) => b.start - a.start || b.end - a.end);
  for (const e of edits) out = out.slice(0, e.start) + e.text + out.slice(e.end);
  if (!h1) {
    const title = options.title ? `# ${options.title}` : '';
    out = blocks(title, note.trim(), out);
  }
  return `${out.trimEnd()}\n`;
}
