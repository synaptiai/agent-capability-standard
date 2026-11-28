// Types for report-audit.mjs.
export interface Advisory {
  name: string;
  severity: string;
  id: string;
  title: string;
  range: string;
  url: string;
}
export function escapeData(text: unknown): string;
export function advisories(report: unknown): Advisory[];
export function report(status: number | null, stdout: string): { annotation: string | null; summary: string };
