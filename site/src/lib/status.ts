// The badge style of each status value the site shows: RFC statuses (the
// spec/GOVERNANCE.md vocabulary), the `**Document Status**:` values, the
// Standard's status, and the label for profile workflows no catalog defines.
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
  | 'proposed';

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
};

/** The style of a status value, trimmed first. Throws on a value with no style. */
export function statusStyle(value: string): StatusStyle {
  const style = STATUS_STYLES[value.trim()];
  if (!style) throw new Error(`status: no badge style for "${value.trim()}"; add it to src/lib/status.ts`);
  return style;
}
