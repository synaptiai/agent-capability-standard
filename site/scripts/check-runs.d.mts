// Types for check-runs.mjs, for the tests.
import type { ExemptRun, PageGeometry, Run } from '../src/lib/runs';

export interface PageResult {
  template: string;
  width: number;
  small?: { top: number; bottom: number }[];
  runs: Run[];
  missing: ExemptRun[];
}
export interface Summary {
  limit: number;
  target: number;
  results: {
    url: string;
    template: string;
    enforced: boolean;
    longest: Run | null;
    narrow: Run | null;
    over: Run[];
    small: { top: number; bottom: number }[];
    failing: Run[];
  }[];
  missing: string[];
  /** Enforced URLs and exempt-run pages that are not among the pages measured (complete runs only). */
  unmatched: string[];
}
export function standardUrlFrom(redirects: string): string;
export function assertMeasured(paths: string[], results: Summary['results'], failed: string[]): void;
export function collectGeometry(args: {
  entries: (ExemptRun & { key: string; label: string })[];
  selector: string;
  min: { width: number; height: number };
  vh: number;
}): { classes: string[]; geometry: PageGeometry; small: { top: number; bottom: number }[]; missing: string[] } | null;
export function withTemplate<T extends { classes: string[] }>(raw: T | null): (Omit<T, 'classes'> & { template: string }) | null;
export function selfCheck(browser: unknown): Promise<string[]>;
export function runSweep(
  dist: string,
  options?: { only?: string[] | null; concurrency?: number; log?: (m: string) => void },
): Promise<Summary & { failed: string[] }>;
export function summarise(
  pages: Map<string, { wide?: PageResult; narrow?: PageResult }>,
  options?: { complete?: boolean; standardUrl?: string | null },
): Summary;
export function reportLines(summary: Omit<Summary, 'unmatched'> & { unmatched?: string[] }): string[];
