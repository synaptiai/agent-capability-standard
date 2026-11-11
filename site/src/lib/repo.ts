// Facts about the repository the site is built from. The site always builds
// from `site/`, and content is read from the repository root above it.
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

function git(args: string[], cwd: string): string {
  return execFileSync('git', args, { cwd, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
}

function findRepoRoot(): string {
  const top = git(['rev-parse', '--show-toplevel'], process.cwd()).trim();
  const siteDir = path.join(top, 'site');
  if (path.resolve(process.cwd()) !== siteDir) {
    throw new Error(`repo: run the site from ${siteDir}, not ${process.cwd()}`);
  }
  if (!existsSync(path.join(siteDir, 'package.json'))) {
    throw new Error(`repo: ${siteDir} has no package.json`);
  }
  return top;
}

/** Absolute path of the repository root. */
export const REPO_ROOT: string = findRepoRoot();

/** Read a repository file as UTF-8. `repoPath` uses forward slashes. */
export function readRepoFile(repoPath: string): string {
  return readFileSync(path.join(REPO_ROOT, repoPath), 'utf8');
}

function readGithubBase(): string {
  const plugin = JSON.parse(readRepoFile('.claude-plugin/plugin.json')) as { repository?: unknown };
  const repo = plugin.repository;
  if (typeof repo !== 'string' || !/^https:\/\/github\.com\/[^/]+\/[^/]+$/.test(repo)) {
    throw new Error(`repo: plugin.json "repository" is not a GitHub URL: ${String(repo)}`);
  }
  return repo;
}

/** The repository on GitHub, e.g. https://github.com/<owner>/<name>. */
export const GITHUB_BASE: string = readGithubBase();

/** The commit the site is built from. */
export const COMMIT_SHA: string = git(['rev-parse', 'HEAD'], REPO_ROOT).trim();

/** Every path `git ls-files` lists, relative to the root, with forward slashes. */
export const TRACKED_FILES: ReadonlySet<string> = new Set(
  git(['ls-files', '-z'], REPO_ROOT)
    .split('\0')
    .filter((p) => p.length > 0),
);

/** Tracked files under a directory prefix (no trailing slash), sorted. */
export function trackedUnder(dir: string, ext?: string): string[] {
  const prefix = `${dir}/`;
  return [...TRACKED_FILES]
    .filter((p) => p.startsWith(prefix) && (ext === undefined || p.endsWith(ext)))
    .sort();
}

/** GitHub URL of a file on the main branch. */
export function githubBlobUrl(repoPath: string): string {
  return `${GITHUB_BASE}/blob/main/${repoPath}`;
}

/** GitHub URL of a directory on the main branch. */
export function githubTreeUrl(repoPath: string): string {
  return `${GITHUB_BASE}/tree/main/${repoPath}`;
}
