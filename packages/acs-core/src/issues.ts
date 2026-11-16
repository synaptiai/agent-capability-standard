/**
 * Diagnostic locations (STANDARD v1.2.0 §9.8): the projection of a
 * finding's location to one dot-and-bracket path, for a format that wants
 * one (such as a definition issue's `path`).
 */

/** The location keys the projection reads. */
export interface IssueLocation {
  workflow?: string;
  step?: number;
  field?: string;
  [key: string]: unknown;
}

/**
 * `workflow`, then `.steps[step]` when `step` is present, then `.` and
 * `field` when `field` is present (`review.steps[1].gates[0].when`). A
 * finding with no `workflow` projects to its `field` alone.
 */
export function issuePath(location: IssueLocation): string {
  let out = location.workflow ?? '';
  if (location.workflow !== undefined && typeof location.step === 'number') out += `.steps[${location.step}]`;
  if (location.field !== undefined) out += out === '' ? location.field : `.${location.field}`;
  return out;
}
