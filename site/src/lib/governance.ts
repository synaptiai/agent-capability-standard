// The RFC and Standard statuses spec/GOVERNANCE.md allows. No imports, so
// scripts/check-design-data.mjs can load it with plain `node`, and the RFC
// overview and the badge check read the sentences the same way.

/** The values of a "<subject> status is A, B, C or D." sentence. */
function statusList(text: string, subject: string): string[] {
  const m = new RegExp(`${subject} status is ([^.]+)\\.`).exec(text.replace(/\s+/g, ' '));
  if (!m) throw new Error(`spec/GOVERNANCE.md has no "${subject} status is" sentence`);
  return m[1]!
    .replace(/\([^)]*\)/g, '')
    .split(/\s*,\s*(?:or\s+)?|\s+or\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** RFC statuses from GOVERNANCE.md's "An RFC's status is A, B, C or D." sentence. */
export function governanceStatuses(text: string): string[] {
  return statusList(text, "An RFC's");
}

/** Standard statuses from GOVERNANCE.md's "A Standard document's status is A, B, C or D." sentence. */
export function standardStatuses(text: string): string[] {
  return statusList(text, "A Standard document's");
}
