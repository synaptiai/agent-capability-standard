// The release notes page's figures (issue #125), drawn from CHANGELOG.md's own
// structure: no diagram is written into the changelog, because each version's
// section becomes its GitHub Release notes.
//
// - The release timeline: one row per section ("## [Unreleased]" and each
//   "## [vX.Y.Z] — date"), with a bar per change kind ("### Added", …)
//   counting the top-level list entries under it.
// - Under a long kind section (LONG_SECTION entries or more) whose entries
//   cite an issue ("#N") or name a diagnostic code the Standard defines: the
//   issues with the number of entries citing each, and the codes as tiles
//   linked to the diagnostics page. Every long section shows its first
//   SHOWN_ENTRIES entries and folds the rest; the Markdown copy keeps them all.
import { codeLines } from './md-sections';
import { plural } from './words';

/** A kind section with this many entries or more gets its own figure and folds. */
export const LONG_SECTION = 8;
/** How many entries of a long kind section stay open on the page. */
export const SHOWN_ENTRIES = 5;

export interface ReleaseEntry {
  text: string;
  /** Issue numbers the entry cites ("#114"), without the "#". */
  issues: string[];
  codes: string[];
}

export interface KindSection {
  kind: string;
  entries: ReleaseEntry[];
}

export interface Release {
  /** "Unreleased" or the version as the heading writes it, e.g. "v2.0.0". */
  version: string;
  date: string | null;
  /** The heading text as written, e.g. "[v2.0.0] — 2026-10-29". */
  heading: string;
  kinds: KindSection[];
}

// Keep a Changelog writes "## [1.0.0] - 2017-06-20"; this changelog uses an
// em dash. Any dash is accepted, as scripts/release_notes.py accepts any
// "## [version]" heading.
const RELEASE = /^## \[([^\]]+)\](?:\s+[—–-]\s+(\d{4}-\d{2}-\d{2}))?\s*$/;
const KIND = /^### (.+?)\s*$/;
const BULLET = /^[-*+] /;

/**
 * A release heading's version and date, or null when `line` is not a
 * "## [" heading. Throws on a "## [" heading in another form, so a section
 * is never dropped from the figures without notice.
 */
export function releaseHeading(line: string): { version: string; date: string | null } | null {
  if (!line.startsWith('## [')) return null;
  const r = RELEASE.exec(line);
  if (!r) throw new Error(`CHANGELOG.md: "${line}" is not "## [version]" or "## [version] - YYYY-MM-DD"`);
  return { version: r[1]!, date: r[2] ?? null };
}
const CODE = /\b[VWFSRB]\d{3}\b/g;

/** The issue numbers an entry cites as "#N", in first-seen order. */
export function entryIssues(entry: string): string[] {
  return [...new Set([...entry.matchAll(/(?<![\w&])#(\d{1,5})\b/g)].map((m) => m[1]!))];
}

/** The diagnostic codes an entry names, in first-seen order. */
export function entryCodes(entry: string): string[] {
  return [...new Set(entry.match(CODE) ?? [])];
}

/** The changelog's release sections, in file order (newest first). */
export function parseReleases(changelog: string): Release[] {
  const out: Release[] = [];
  let rel: Release | null = null;
  let kind: KindSection | null = null;
  let entry: string[] | null = null;
  const closeEntry = () => {
    if (entry && kind) {
      const t = entry.join('\n');
      kind.entries.push({ text: t, issues: entryIssues(t), codes: entryCodes(t) });
    }
    entry = null;
  };
  const code = codeLines(changelog);
  for (const [i, line] of changelog.split('\n').entries()) {
    const r = code[i] ? null : releaseHeading(line);
    if (r) {
      closeEntry();
      rel = { version: r.version, date: r.date, heading: line.slice(3).trim(), kinds: [] };
      out.push(rel);
      kind = null;
      continue;
    }
    if (!code[i] && (/^## /.test(line) || /^# /.test(line))) {
      closeEntry();
      rel = null;
      kind = null;
      continue;
    }
    const k = code[i] ? null : KIND.exec(line);
    if (k && rel) {
      closeEntry();
      kind = { kind: k[1]!, entries: [] };
      rel.kinds.push(kind);
      continue;
    }
    if (!kind) continue;
    // A line of a code block is neither an entry nor the end of one, as in
    // releaseBars: a "- " line inside a fence is code, not a change.
    if (code[i]) continue;
    if (BULLET.test(line)) {
      closeEntry();
      entry = [line.slice(2)];
    } else if (entry && /^\s+\S/.test(line)) {
      entry.push(line.trim());
    } else if (entry && line.trim() !== '') {
      closeEntry();
    }
  }
  closeEntry();
  if (out.length === 0) throw new Error('CHANGELOG.md: no "## [version]" section');
  return out;
}

/** The change kinds the changelog uses, in KIND_ORDER. */
export function kindsInUse(releases: Release[]): string[] {
  const seen: string[] = [];
  for (const r of releases) for (const k of r.kinds) if (!seen.includes(k.kind)) seen.push(k.kind);
  const rank = (k: string) => (KIND_ORDER.indexOf(k) < 0 ? KIND_ORDER.length : KIND_ORDER.indexOf(k));
  return seen.map((k, i) => ({ k, i })).sort((a, b) => rank(a.k) - rank(b.k) || a.i - b.i).map((x) => x.k);
}

/** The Keep a Changelog order of change kinds; others follow in first-seen order. */
export const KIND_ORDER: readonly string[] = ['Added', 'Changed', 'Deprecated', 'Removed', 'Fixed', 'Security'];

/** Entries of one kind in one release (0 when the release has no such section). */
export function kindCount(r: Release, kind: string): number {
  return r.kinds.filter((k) => k.kind === kind).reduce((n, k) => n + k.entries.length, 0);
}


export const TIMELINE_TITLE = 'Releases and the entries under each kind of change, newest first';

export function timelineCaption(releases: Release[]): string {
  const kinds = kindsInUse(releases);
  const total = releases.reduce((n, r) => n + r.kinds.reduce((m, k) => m + k.entries.length, 0), 0);
  const top = [...releases].sort((a, b) => kindTotal(b) - kindTotal(a))[0]!;
  const dated = releases.filter((r) => r.date);
  const span = dated.length > 0 ? ` from ${dated.at(-1)!.date} to ${dated[0]!.date}` : '';
  return `${plural(releases.length, 'section', 'sections')}${span}, ${plural(total, 'entry', 'entries')} under ${kinds.join(', ')}; ${top.version} has the most (${kindTotal(top)}). Each bar counts the top-level list entries under that heading.`;
}

export function kindTotal(r: Release): number {
  return r.kinds.reduce((n, k) => n + k.entries.length, 0);
}

export function sectionTitle(r: Release, k: KindSection): string {
  return `Issues and diagnostic codes in ${r.version}, ${k.kind}`;
}

/** Issues with the number of entries citing each, most first; entries citing none counted apart. */
export function issueCounts(k: KindSection): { rows: { issue: string; count: number }[]; none: number } {
  const counts = new Map<string, number>();
  for (const e of k.entries) for (const i of e.issues) counts.set(i, (counts.get(i) ?? 0) + 1);
  const rows = [...counts].map(([issue, count]) => ({ issue, count })).sort((a, b) => b.count - a.count || Number(a.issue) - Number(b.issue));
  return { rows, none: k.entries.filter((e) => e.issues.length === 0).length };
}

/** The diagnostic codes a section's entries name that the Standard defines, sorted. */
export function sectionCodes(k: KindSection, known: ReadonlySet<string>): string[] {
  return [...new Set(k.entries.flatMap((e) => e.codes))].filter((c) => known.has(c)).sort();
}

/** A long section gets a figure when its entries name a defined code or cite an issue. */
export function sectionHasFigure(k: KindSection, known: ReadonlySet<string>): boolean {
  return k.entries.length >= LONG_SECTION && (sectionCodes(k, known).length > 0 || issueCounts(k).rows.length > 0);
}

export function sectionCaption(r: Release, k: KindSection, known: ReadonlySet<string>): string {
  const { rows, none } = issueCounts(k);
  const codes = sectionCodes(k, known);
  const issues =
    rows.length === 0
      ? 'none cites an issue'
      : `${plural(k.entries.length - none, 'entry cites', 'entries cite')} ${plural(rows.length, 'issue', 'issues')}, #${rows[0]!.issue} the most (${rows[0]!.count})`;
  const codeWords = codes.length === 0 ? 'no diagnostic code is named' : `${plural(codes.length, 'diagnostic code', 'diagnostic codes')} of the Standard named, each linked to its entry on the diagnostics page`;
  return `${plural(k.entries.length, 'entry', 'entries')} under ${k.kind} in ${r.version}: ${issues}; ${codeWords}.`;
}

/** The long kind sections: those that fold, whether or not they get a figure. */
export function longSections(releases: Release[]): { release: Release; section: KindSection }[] {
  return releases.flatMap((release) => release.kinds.filter((k) => k.entries.length >= LONG_SECTION).map((section) => ({ release, section })));
}
