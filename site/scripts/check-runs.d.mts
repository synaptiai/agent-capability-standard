// Types for check-runs.mjs, for the tests.
import type { ExemptRun, PageGeometry, Run } from '../src/lib/runs';

export interface PageResult {
  template: string;
  width: number;
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
    failing: Run[];
  }[];
  missing: string[];
}
export function collectGeometry(args: {
  entries: (ExemptRun & { key: string; label: string })[];
  selector: string;
  min: { width: number; height: number };
  vh: number;
}): { template: string; geometry: PageGeometry; missing: string[] } | null;
export function selfCheck(browser: unknown): Promise<string[]>;
export function runSweep(
  dist: string,
  options?: { only?: string[] | null; concurrency?: number; log?: (m: string) => void },
): Promise<Summary>;
export function summarise(pages: Map<string, { wide?: PageResult; narrow?: PageResult }>, complete?: boolean): Summary;
export function reportLines(summary: Summary): string[];
