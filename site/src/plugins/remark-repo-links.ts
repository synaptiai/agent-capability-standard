// Rewrites every link, image and link definition in a repository Markdown file
// with the shared resolver (src/lib/resolve.ts): .md links become site routes,
// other tracked files and directories go to GitHub, and #anchors are checked
// against the target's headings. Code spans and code blocks hold no link nodes,
// so they are left alone. Any link that does not resolve fails the build, with
// every bad link in the file listed as path:line.
import type { Root } from 'mdast';
import { visit } from 'unist-util-visit';
import type { VFile } from 'vfile';
import { emptyFileStats, linkStats, repoResolver } from '../lib/links';
import type { Resolver } from '../lib/resolve';
import { failWith, lineOf, sourceOf } from './source';

export interface RemarkRepoLinksOptions {
  resolver?: Resolver;
}

export default function remarkRepoLinks(options: RemarkRepoLinksOptions = {}) {
  return (tree: Root, file: VFile): void => {
    const src = sourceOf(file, 'remark-repo-links');
    const resolve = options.resolver ?? repoResolver();
    const stats = emptyFileStats();
    const problems: string[] = [];
    visit(tree, (node) => {
      if (node.type !== 'link' && node.type !== 'image' && node.type !== 'definition') return;
      const r = resolve(src.repoPath, node.url, 'html');
      if (!r.ok) {
        problems.push(`${lineOf(src, node)}: ${node.url} -> ${r.reason}`);
        return;
      }
      stats.byKind[r.kind] += 1;
      if (r.anchorChecked) stats.anchorsChecked += 1;
      node.url = r.url;
    });
    failWith('remark-repo-links', problems);
    linkStats.set(src.repoPath, stats);
  };
}
