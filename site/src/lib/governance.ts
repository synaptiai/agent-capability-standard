// The RFC statuses spec/GOVERNANCE.md allows. No imports, so
// scripts/check-design-data.mjs can load it with plain `node`, and the RFC
// overview and the badge check read the sentence the same way.

/** RFC statuses from GOVERNANCE.md's "An RFC's status is A, B, C or D." sentence. */
export function governanceStatuses(text: string): string[] {
  const m = /An RFC's status is ([^.]+)\./.exec(text.replace(/\s+/g, ' '));
  if (!m) throw new Error("spec/GOVERNANCE.md has no \"An RFC's status is\" sentence");
  return m[1]!
    .replace(/\([^)]*\)/g, '')
    .split(/\s*,\s*(?:or\s+)?|\s+or\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
}
