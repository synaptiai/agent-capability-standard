// The figure blocks of the release notes' Markdown copy (visual spec 6.1): the
// timeline before the first release heading, and each long section's figure
// right after its "### Kind" heading, as the page places them. The copy keeps
// every entry; only the page folds them.
import type { Heading, Root } from 'mdast';
import { toString } from 'mdast-util-to-string';
import { loadDiagnostics } from '../data/diagnostics';
import {
  issueCounts,
  kindCount,
  kindsInUse,
  parseReleases,
  sectionCaption,
  sectionCodes,
  sectionHasFigure,
  sectionTitle,
  timelineCaption,
  TIMELINE_TITLE,
  type Release,
} from '../lib/release-figures';
import { code, figure, table } from './md';

type Edit = { start: number; end: number; text: string };

export function timelineBlock(releases: Release[]): string {
  const kinds = kindsInUse(releases);
  const rows = releases.map((r) => [`${code(r.version)}${r.date ? ` (${r.date})` : ''}`, ...kinds.map((k) => String(kindCount(r, k)))]);
  return figure(TIMELINE_TITLE, timelineCaption(releases), table(['Release', ...kinds], rows));
}

export function sectionBlock(r: Release, k: Release['kinds'][number], known: ReadonlySet<string>): string {
  const { rows, none } = issueCounts(k);
  const lines: string[] = [];
  if (rows.length > 0) {
    lines.push('Issues cited, with the number of entries citing each:', '');
    for (const x of rows) lines.push(`- #${x.issue}: ${x.count}`);
    if (none > 0) lines.push(`- none: ${none}`);
  }
  const codes = sectionCodes(k, known);
  if (codes.length > 0) {
    if (lines.length > 0) lines.push('');
    lines.push(`Diagnostic codes named: ${codes.map(code).join(', ')}.`);
  }
  return figure(sectionTitle(r, k), sectionCaption(r, k, known), lines.join('\n'));
}

/** Insertions into the parsed CHANGELOG.md `tree` for the page's figures. */
export function releaseFigureEdits(tree: Root, changelog: string): Edit[] {
  const releases = parseReleases(changelog);
  const known = new Set(loadDiagnostics().map((d) => d.code));
  const out: Edit[] = [];
  let rel: Release | undefined;
  let first = true;
  for (const node of tree.children) {
    if (node.type !== 'heading') continue;
    const h = node as Heading;
    const t = toString(h).trim();
    if (h.depth === 2) {
      rel = releases.find((r) => t.includes(`[${r.version}]`) || t.startsWith(r.version));
      if (first) {
        const start = h.position!.start.offset!;
        out.push({ start, end: start, text: `${timelineBlock(releases)}\n\n` });
        first = false;
      }
      continue;
    }
    if (h.depth !== 3 || !rel) continue;
    const section = rel.kinds.find((k) => k.kind === t);
    if (!section || !sectionHasFigure(section, known)) continue;
    const end = h.position!.end.offset!;
    out.push({ start: end, end, text: `\n\n${sectionBlock(rel, section, known)}` });
  }
  return out;
}
