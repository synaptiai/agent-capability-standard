// The heading anchors GitHub gives a Markdown file, computed from the source.
// Astro's rehypeHeadingIds uses the same slugger (github-slugger) with a fresh
// instance per file, so these are also the ids the site renders. The H1 is
// included because it is never removed from the page.
import GithubSlugger from 'github-slugger';
import type { Heading, Html, Root } from 'mdast';
import { toString } from 'mdast-util-to-string';
import remarkGfm from 'remark-gfm';
import remarkParse from 'remark-parse';
import { unified } from 'unified';
import { visit } from 'unist-util-visit';

const FRONTMATTER = /^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/;

/** The text Astro renders: the source with any YAML frontmatter removed. */
export function stripFrontmatter(text: string): string {
  return text.replace(FRONTMATTER, '');
}

/**
 * Number of source lines before the text Astro renders. Astro removes the
 * frontmatter and trims the rest, so line 1 of the rendered text is this many
 * lines into the file.
 */
export function bodyLineOffset(source: string): number {
  const rest = stripFrontmatter(source);
  const skipped = source.length - rest.length + (rest.length - rest.trimStart().length);
  return source.slice(0, skipped).split('\n').length - 1;
}

const parser = unified().use(remarkParse).use(remarkGfm);

export function parseMarkdown(text: string): Root {
  return parser.parse(stripFrontmatter(text));
}

/** Plain text of a heading as GitHub slugs it: inline HTML tags are dropped. */
export function headingText(node: Heading): string {
  return toString(node, { includeHtml: false, includeImageAlt: false });
}

const NAMED_ANCHOR = /<a\s[^>]*?\b(?:name|id)\s*=\s*["']([^"']+)["']/gi;

export interface Anchors {
  /** Heading slugs in document order. */
  headings: string[];
  /** Every valid fragment: heading slugs plus `<a name|id>` values. */
  all: ReadonlySet<string>;
}

/** Anchors of a Markdown text. Pure; `anchorsOf` caches it per repo path. */
export function computeAnchors(text: string): Anchors {
  const tree = parseMarkdown(text);
  const slugger = new GithubSlugger();
  const headings: string[] = [];
  const named: string[] = [];
  visit(tree, (node) => {
    if (node.type === 'heading') headings.push(slugger.slug(headingText(node)));
    if (node.type === 'html') {
      for (const m of (node as Html).value.matchAll(NAMED_ANCHOR)) named.push(m[1]!);
    }
  });
  return { headings, all: new Set([...headings, ...named]) };
}

const cache = new Map<string, Anchors>();

/** Anchors of a repository file, read through `read` and cached by path. */
export function anchorsOf(repoPath: string, read: (p: string) => string): Anchors {
  let a = cache.get(repoPath);
  if (!a) {
    a = computeAnchors(read(repoPath));
    cache.set(repoPath, a);
  }
  return a;
}
