// Shared by the Markdown plugins: which repository file is being rendered, and
// how to turn a position in the rendered text into a line of that file.
import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { VFile } from 'vfile';
import { bodyLineOffset } from '../lib/anchors';
import { REPO_ROOT } from '../lib/repo';

export interface SourceFile {
  /** Path relative to the repository root, with forward slashes. */
  repoPath: string;
  /** Add to a rendered-text line number to get the source line. */
  lineOffset: number;
}

const offsets = new Map<string, number>();

/** The repository file a plugin is running on. Throws if there is none. */
export function sourceOf(file: VFile, plugin: string): SourceFile {
  if (!file.path) throw new Error(`${plugin}: file.path is missing, so the source file is unknown`);
  const abs = path.resolve(file.path);
  const rel = path.relative(REPO_ROOT, abs);
  if (rel === '' || rel.startsWith('..') || path.isAbsolute(rel)) {
    throw new Error(`${plugin}: ${abs} is outside the repository ${REPO_ROOT}`);
  }
  const repoPath = rel.split(path.sep).join('/');
  let lineOffset = offsets.get(abs);
  if (lineOffset === undefined) {
    lineOffset = bodyLineOffset(readFileSync(abs, 'utf8'));
    offsets.set(abs, lineOffset);
  }
  return { repoPath, lineOffset };
}

/** `path:line` of a node in the source file. */
export function lineOf(src: SourceFile, node: { position?: { start: { line: number } } | undefined }): string {
  const line = node.position?.start.line;
  return line === undefined ? src.repoPath : `${src.repoPath}:${line + src.lineOffset}`;
}

/** Throw once with every problem in a file, one per line. */
export function failWith(plugin: string, problems: string[]): void {
  if (problems.length === 0) return;
  throw new Error(`${plugin}: ${problems.length} problem(s):\n  ${problems.join('\n  ')}`);
}
