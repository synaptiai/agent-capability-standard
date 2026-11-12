// Glyphs for the groups of the section listing pages (visual spec 2.2,
// "Listing groups"), drawn for the home and listing exemplar (issue #125).
// Data only, like glyphs.ts, which spreads these into CONCEPT_GLYPHS and
// GLYPH_ALIASES so every check and the glyph sheet see them.

/** The four group glyphs the spec asks for, 9x9. */
export const GROUP_GLYPHS: Readonly<Record<string, readonly string[]>> = {
  // A tile with a plus at its top-right corner.
  'group:skill-authoring': ['......#..', '.....###.', '......#..', '######...', '#....#...', '#....#...', '#....#...', '#....#...', '######...'],
  // A section sign, with no page around it.
  'group:regulation': ['...####..', '..#......', '...##....', '..#..#...', '..#...#..', '...#..#..', '....##...', '......#..', '..####...'],
  // A rosette with two ribbon tails.
  'group:standard-cert': ['..#####..', '.#######.', '.##...##.', '.##...##.', '.#######.', '..#####..', '..##.##..', '.##...##.', '.#.....#.'],
  // A set square: a right triangle with a triangular hole.
  'group:methodology': ['#........', '##.......', '###......', '##.#.....', '##..#....', '##...#...', '##....#..', '########.', '#########'],
};

/** Groups whose glyph reuses one with the same meaning. */
export const GROUP_ALIASES: Readonly<Record<string, string>> = {
  // Not in the spec's table: the background section's research pages.
  'group:research': 'search',
};

/**
 * The glyph of a listing group, by its label (visual spec 2.2). A label that
 * is missing here fails the build, so a new group gets a glyph on purpose.
 */
export const LISTING_GROUP_GLYPHS: Readonly<Record<string, string>> = {
  Skills: 'skill:composed',
  'Skill authoring': 'group:skill-authoring',
  'EU AI Act': 'group:regulation',
  'ISO/IEC 42001': 'group:standard-cert',
  Methodology: 'group:methodology',
  Research: 'group:research',
  Proposals: 'section:rfcs',
  'Previous versions': 'chapter:versioning-and-compatibility',
  'Reference workflows': 'section:workflows',
};
