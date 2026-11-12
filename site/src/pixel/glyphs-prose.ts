// Glyphs for the prose-page figures (visual spec 3.10), kept apart from
// glyphs.ts so branches merge cleanly. Data only: glyphs.ts spreads these into
// GLYPH_ALIASES so every check and the glyph sheet see them.

/**
 * F-O1's mapping types (schemas/interop/oasf_mapping.yaml), each through a
 * glyph that already carries the meaning:
 * - direct, a 1:1 correspondence: the right chevron, straight across;
 * - domain, the same capability specialized by a domain parameter: the
 *   specializes mark;
 * - composition, several capabilities together: the nested squares of a
 *   composed skill;
 * - workflow, a composed workflow pattern: the workflows section glyph;
 * - ga_extension, a GA-native capability given a synthetic GA-xxx code: the
 *   hash of a code.
 */
export const PROSE_ALIASES: Readonly<Record<string, string>> = {
  'map:direct': 'chevron-right',
  'map:domain': 'mark:specializes',
  'map:composition': 'nested',
  'map:workflow': 'section:workflows',
  'map:ga_extension': 'hash',
  // F-R2, the RFC lifecycle track: a draft is still being written (the
  // pencil), an accepted RFC is checked, a rejected one crossed out, and a
  // superseded one points on to the RFC that replaced it.
  'lifecycle:draft': 'pencil',
  'lifecycle:accepted': 'check',
  'lifecycle:rejected': 'close',
  'lifecycle:superseded': 'chevron-right',
};
