// Diagnostic codes from the current Standard's §9.2 to §9.7 tables, cross-checked
// against core/src/diag.rs. Only those sections are read: Appendix C repeats
// a code in a change table. Severity is not a table column; it comes from the
// §9.1 row whose code range covers the code, and must agree with the section
// heading ("... Errors" or "Warnings").
import { slug } from 'github-slugger';
import { readRepoFile } from '../lib/repo';
import { standardVersions } from './versions';

export const DIAG_RS = 'core/src/diag.rs';

export type Severity = 'error' | 'warning';

export interface Diagnostic {
  code: string;
  name: string;
  severity: Severity;
  /** The §9 subsection heading without its number, e.g. "Validation Errors". */
  category: string;
  /** Spec section number, e.g. "9.2". */
  section: string;
  /** GitHub-style id of that section's heading in the spec. */
  sectionAnchor: string;
  descriptionMd: string;
  /** Id of the code's entry on the diagnostics page. */
  anchor: string;
}

/** Any table row that starts with a code-like cell, read or not. */
const CODE_ROW = /^\|\s*[A-Z]\d{3}\s*\|/;

interface Range {
  prefix: string;
  severity: Severity;
}

function lines(text: string): string[] {
  return text.split(/\r?\n/);
}

function indexOfHeading(ls: string[], re: RegExp, what: string): number {
  const i = ls.findIndex((l) => re.test(l));
  if (i < 0) throw new Error(`diagnostics: the spec has no ${what} heading`);
  return i;
}

/** §9.1: code range (e.g. "V1xx") to severity. */
function parseRanges(ls: string[]): Range[] {
  const start = indexOfHeading(ls, /^### 9\.1 /, '§9.1');
  const end = indexOfHeading(ls, /^### 9\.2 /, '§9.2');
  const ranges: Range[] = [];
  for (const l of ls.slice(start + 1, end)) {
    const m = /^\|[^|]+\|\s*([A-Z]\d)xx\s*\|\s*(error|warning)\s*\|/.exec(l);
    if (m) ranges.push({ prefix: m[1]!, severity: m[2] as Severity });
  }
  if (ranges.length === 0) throw new Error('diagnostics: §9.1 has no code ranges');
  return ranges;
}

/** Parse §9.2 up to (not including) §9.8. Exported for tests. */
export function parseSpecDiagnostics(text: string): Diagnostic[] {
  const ls = lines(text);
  const ranges = parseRanges(ls);
  const start = indexOfHeading(ls, /^### 9\.2 /, '§9.2');
  const end = indexOfHeading(ls, /^### 9\.8 /, '§9.8');
  const out: Diagnostic[] = [];
  let section: { number: string; title: string; anchor: string } | null = null;
  let sectionSeverity: Severity | null = null;
  for (const l of ls.slice(start, end)) {
    const h = /^### (9\.\d+) (.+)$/.exec(l);
    if (h) {
      section = { number: h[1]!, title: h[2]!.trim(), anchor: slug(l.replace(/^#+\s*/, '')) };
      sectionSeverity = null;
      continue;
    }
    const row = /^\|\s*([VBSRFW]\d{3})\s*\|\s*([A-Z_]+)\s*\|\s*(.*?)\s*\|\s*$/.exec(l);
    // A row that starts with a code but does not match is an error, not
    // skipped: diag.rs would miss it the same way, and the cross-check
    // compares only what both parsers keep.
    if (!row && CODE_ROW.test(l)) throw new Error(`diagnostics: cannot read the diagnostic row: ${l.trim()}`);
    if (!row || !section) continue;
    const code = row[1]!;
    const range = ranges.find((r) => code.startsWith(r.prefix));
    if (!range) throw new Error(`diagnostics: ${code} is in no §9.1 code range`);
    if (sectionSeverity !== null && sectionSeverity !== range.severity) {
      throw new Error(`diagnostics: §${section.number} mixes error and warning codes`);
    }
    // The heading must agree: "... Errors" sections hold errors, "Warnings" warnings.
    const headed: Severity | null = /Errors$/.test(section.title)
      ? 'error'
      : /^Warnings$/.test(section.title)
        ? 'warning'
        : null;
    if (headed !== range.severity) {
      throw new Error(`diagnostics: ${code} has severity ${range.severity} under §${section.number} ${section.title}`);
    }
    sectionSeverity = range.severity;
    out.push({
      code,
      name: row[2]!,
      severity: range.severity,
      category: section.title,
      section: section.number,
      sectionAnchor: section.anchor,
      descriptionMd: row[3]!,
      anchor: code.toLowerCase(),
    });
  }
  const seen = new Set<string>();
  for (const d of out) {
    if (seen.has(d.code)) throw new Error(`diagnostics: ${d.code} appears twice in §9.2-§9.7`);
    seen.add(d.code);
  }
  return out;
}

/** The (code, name, severity) triples core/src/diag.rs declares. */
export function parseDiagRs(text: string): { code: string; name: string; severity: Severity }[] {
  const re = /(\w+) = "([VBSRFW]\d{3})", "([A-Z_]+)", (Error|Warning);/g;
  const found = [...text.matchAll(re)];
  const loose = [...text.matchAll(/"[A-Z]\d{3}",/g)].length;
  if (loose !== found.length) {
    throw new Error(`diagnostics: cannot read ${loose - found.length} code entries in ${DIAG_RS}; expected Name = "X999", "NAME", Error|Warning;`);
  }
  return found.map((m) => ({
    code: m[2]!,
    name: m[3]!,
    severity: m[4] === 'Error' ? 'error' : 'warning',
  }));
}

/** Fail unless the spec and diag.rs list the same codes with the same name and severity. */
export function crossCheck(spec: Diagnostic[], rust: ReturnType<typeof parseDiagRs>): void {
  const problems: string[] = [];
  const rs = new Map(rust.map((r) => [r.code, r]));
  for (const d of spec) {
    const r = rs.get(d.code);
    if (!r) problems.push(`${d.code} is in the spec but not in ${DIAG_RS}`);
    else if (r.name !== d.name || r.severity !== d.severity) {
      problems.push(`${d.code}: spec has ${d.name}/${d.severity}, ${DIAG_RS} has ${r.name}/${r.severity}`);
    }
  }
  const specCodes = new Set(spec.map((d) => d.code));
  for (const r of rust) if (!specCodes.has(r.code)) problems.push(`${r.code} is in ${DIAG_RS} but not in the spec`);
  if (problems.length > 0) throw new Error(`diagnostics: spec and core disagree:\n  ${problems.join('\n  ')}`);
}

let cached: Diagnostic[] | undefined;

export function loadDiagnostics(): Diagnostic[] {
  if (cached) return cached;
  const current = standardVersions()[0];
  if (!current) throw new Error('diagnostics: no spec/STANDARD-v*.md file is tracked');
  const spec = parseSpecDiagnostics(readRepoFile(current.source));
  crossCheck(spec, parseDiagRs(readRepoFile(DIAG_RS)));
  cached = spec;
  return cached;
}
