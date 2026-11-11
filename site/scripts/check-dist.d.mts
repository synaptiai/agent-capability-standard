// Types for check-dist.mjs, for the tests.
export interface Target {
  path: string;
  fragment: string | null;
}
export interface DistStats {
  pages: number;
  checkedLinks: number;
  htmlBytes: number;
  copyBytes: number;
  copies: number;
  llmsBytes: number;
  llmsFullBytes: number;
  totalBytes: number;
  files: number;
}
export const NOT_FOUND_PAGE: string;
export function walk(dir: string, base?: string): string[];
export function pageUrl(file: string): string;
export function decodeEntities(s: string): string;
export function linkValues(html: string): string[];
export function anchorIds(html: string): Set<string>;
export function internalTarget(value: string, fromUrl: string, origin?: string): Target | null;
export function redirectSources(text: string): Set<string>;
export function servedFile(urlPath: string, files: Set<string>): string | null;
export function isCopyLink(urlPath: string, files: Set<string>): boolean;
export function checkLinks(
  fileList: string[],
  read: (file: string) => string,
  redirects?: Set<string>,
): { links: string[]; mdLinks: string[]; checked: number };
export function htmlPages(fileList: string[]): string[];
export function sitemapPaths(xml: string, origin?: string): { paths: string[]; foreign: string[] };
export function llmsTxtCopies(text: string, origin?: string): { copies: string[]; other: string[] };
export function checkCopies(fileList: string[], llmsTxt: string): string[];
export function checkSitemap(fileList: string[], xml: string): string[];
export function checkDistDir(distDir: string): { problems: Record<string, string[]>; stats: DistStats };
export function formatStats(stats: DistStats): string[];
