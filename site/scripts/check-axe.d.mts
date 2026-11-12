// Types for check-axe.mjs, for the tests.
export const AXE_TAGS: string[];
export const THEMES: string[];
export const WIDTHS: number[];
export function sitemapPaths(xml: string): string[];
export function fileFor(dist: string, urlPath: string): string | null;
export function runAxe(
  dist: string,
  options?: { concurrency?: number; only?: string[] | null; log?: (m: string) => void },
): Promise<{ pages: number; runs: number; findings: string[] }>;
