// The badge style of each status value the site shows: RFC statuses (the
// spec/GOVERNANCE.md vocabulary), the `**Document Status**:` values, the
// first clause of every other `**Status:**` line on a routed page (the
// Standard's, the compliance documents', a guide's), and the label for
// profile workflows no catalog defines. Every style has a `status:` glyph.
// No imports, so scripts/check-design-data.mjs can load it with plain `node`
// and fail the build when a source uses a value with no style.

export type StatusStyle =
  | 'draft'
  | 'accepted'
  | 'rejected'
  | 'superseded'
  | 'normative'
  | 'normative-reference'
  | 'reference'
  | 'analysis'
  | 'historical'
  | 'candidate'
  | 'proposed'
  | 'template'
  | 'implementation'
  | 'ready'
  | 'guide'
  | 'integrated';

/** Label for a workflow a domain profile lists that no catalog defines. */
export const PROPOSED_WORKFLOW_STATUS = 'Proposed, not yet in a catalog';

export const STATUS_STYLES: Readonly<Record<string, StatusStyle>> = {
  Draft: 'draft',
  'Draft Proposal': 'draft',
  Accepted: 'accepted',
  Rejected: 'rejected',
  Superseded: 'superseded',
  Normative: 'normative',
  'Normative Reference': 'normative-reference',
  Reference: 'reference',
  Informative: 'reference',
  'Critical Analysis': 'analysis',
  'Historical (Informative)': 'historical',
  'Candidate Standard': 'candidate',
  [PROPOSED_WORKFLOW_STATUS]: 'proposed',
  // A part of the Standard published beside it (spec/EDGE_TYPES.md): normative.
  Standard: 'normative',
  Template: 'template',
  'Reference implementation': 'implementation',
  'Reference analysis': 'analysis',
  'Ready for use': 'ready',
  Guide: 'guide',
  'SDK-integrated': 'integrated',
};

/**
 * The status a `**Status:**` line gives: its first clause, before a dash,
 * a semicolon, a parenthesis or a `|`, without a trailing version
 * ("Reference implementation — Maps ..." is "Reference implementation").
 */
export function statusClause(line: string): string {
  // "Candidate Standard v1.1.0 (accepted ...)": the version is not the status.
  return line.split(/\s+[—–-]\s+|;|\s*\(|\s*\|/)[0]!.replace(/\s+v\d+(?:\.\d+)*$/, '').trim();
}

/** The style of a status value, trimmed first. Throws on a value with no style. */
export function statusStyle(value: string): StatusStyle {
  const style = STATUS_STYLES[value.trim()];
  if (!style) throw new Error(`status: no badge style for "${value.trim()}"; add it to src/lib/status.ts`);
  return style;
}
