// Checks that rendered heading ids are the ids GitHub gives the same headings,
// so every #anchor that works on GitHub works on the site. The expected ids are
// computed from the source with github-slugger directly (one slugger per file,
// headings in document order, frontmatter removed), not through anchors.ts, so
// the check does not share code with the resolver it guards.
// The build runs `checkBuiltSlugs` on every page in dist/ that renders a
// Markdown source; test/slugs.test.ts runs the same comparison on every source,
// including those shown inside generated pages.
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import GithubSlugger from 'github-slugger';
import type { Heading } from 'mdast';
import { toString } from 'mdast-util-to-string';
import remarkGfm from 'remark-gfm';
import remarkParse from 'remark-parse';
import { unified } from 'unified';
import { visit } from 'unist-util-visit';
import { readRepoFile } from './repo';
import { markdownPages } from './routes';

export function githubHeadingIds(markdown: string): string[] {
  const body = markdown.replace(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/, '');
  const tree = unified().use(remarkParse).use(remarkGfm).parse(body);
  const slugger = new GithubSlugger();
  const ids: string[] = [];
  visit(tree, 'heading', (h: Heading) => {
    ids.push(slugger.slug(toString(h, { includeHtml: false, includeImageAlt: false })));
  });
  return ids;
}

export function renderedHeadingIds(html: string): string[] {
  return [...html.matchAll(/<h[1-6]\b[^>]*?\sid="([^"]*)"/g)].map((m) => m[1]!);
}

/** Differences between two id lists, or null when they are equal. */
export function compareIds(want: string[], got: string[]): string | null {
  if (want.length === got.length && want.every((w, i) => got[i] === w)) return null;
  const i = want.findIndex((w, j) => got[j] !== w);
  const at = i === -1 ? want.length : i;
  return `expected ${want.length} ids, got ${got.length}; first difference at heading ${at + 1}: "${want[at] ?? '(none)'}" vs "${got[at] ?? '(none)'}"`;
}

export interface SlugReport {
  pages: number;
  headings: number;
  problems: string[];
}

/** Compare every built Markdown page in `distDir` with its source. */
export function checkBuiltSlugs(distDir: string): SlugReport {
  const report: SlugReport = { pages: 0, headings: 0, problems: [] };
  for (const route of markdownPages()) {
    // The raw template shows its source as code, so it has no heading ids.
    if (route.template === 'raw') continue;
    const file = path.join(distDir, route.url, 'index.html');
    if (!existsSync(file)) {
      report.problems.push(`${route.url}: no ${path.relative(distDir, file)} for ${route.source}`);
      continue;
    }
    const want = githubHeadingIds(readRepoFile(route.source!));
    const diff = compareIds(want, renderedHeadingIds(readFileSync(file, 'utf8')));
    report.pages += 1;
    report.headings += want.length;
    if (diff) report.problems.push(`${route.url} (${route.source}): ${diff}`);
  }
  return report;
}
