// Renders repository Markdown the way the build does: the same unified()
// processor options and Shiki settings astro.config.mjs uses, the same
// frontmatter handling as Astro's Markdown content entries (frontmatter
// blanked, then the body trimmed), and the source file's URL as the path.
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import {
  markdownConfigDefaults,
  parseFrontmatter,
  unified,
  type MarkdownRenderResult,
} from '@astrojs/markdown-remark';
import { PROCESSOR_OPTIONS, SHIKI_CONFIG } from '../src/lib/markdown';
import { readRepoFile, REPO_ROOT } from '../src/lib/repo';

type Renderer = { render: (content: string, opts?: { fileURL?: URL; frontmatter?: Record<string, unknown> }) => Promise<MarkdownRenderResult> };

let renderer: Promise<Renderer> | undefined;

function getRenderer(): Promise<Renderer> {
  renderer ??= unified(PROCESSOR_OPTIONS).createRenderer({
    syntaxHighlight: markdownConfigDefaults.syntaxHighlight,
    shikiConfig: SHIKI_CONFIG,
  }) as Promise<Renderer>;
  return renderer;
}

/** Render a repository file; `text` replaces its contents when given. */
export async function renderRepoFile(repoPath: string, text?: string): Promise<MarkdownRenderResult> {
  const source = text ?? readRepoFile(repoPath);
  const { frontmatter, content } = parseFrontmatter(source, { frontmatter: 'empty-with-spaces' });
  const r = await getRenderer();
  return r.render(content.trim(), {
    fileURL: pathToFileURL(path.join(REPO_ROOT, repoPath)),
    frontmatter,
  });
}
