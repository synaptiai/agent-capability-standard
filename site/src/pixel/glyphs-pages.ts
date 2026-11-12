// Glyphs for single pages (issue #125 acceptance: every section card and
// concept card has its own pixel icon, and no two different concepts share
// one). A listing card takes the glyph of the page it links to, so each page
// that appears as a card gets a glyph here, keyed by its URL. Data only, like
// glyphs.ts, which spreads PAGE_GRIDS into CONCEPT_GLYPHS so every check and
// the glyph sheet see them.
//
// A page whose subject already has a glyph with the same meaning maps to that
// glyph instead of a new grid (the reuse rule of visual spec 2.1): the
// glossary is the Standard's "Terms" chapter, the running-workflows guide is
// the executor, an overview is its group. Everything else gets a grid below.
// The same drawing rules hold: no page silhouette (that is section:spec), no
// head, magnifier, flag, braces or brackets, and circles only at radius 3 or
// more.

/** 9x9 grids for pages, keyed `page:<name>`. */
export const PAGE_GRIDS: Readonly<Record<string, readonly string[]>> = {
  // ---- Get started
  // A window of four panes, one filled: the view of the whole.
  'page:overview': ['#########', '#####...#', '#####...#', '#####...#', '#########', '#...#...#', '#...#...#', '#...#...#', '#########'],
  // Fast forward: two play triangles side by side.
  'page:quickstart': ['.........', '#...#....', '##..##...', '###.###..', '########.', '###.###..', '##..##...', '#...#....', '.........'],
  // A mortarboard with a tassel.
  'page:tutorial': ['.........', '....#....', '..#####..', '#########', '..#####.#', '..#####.#', '..#...#.#', '..#####..', '.........'],
  // A question mark.
  'page:faq': ['..#####..', '.##...##.', '.##...##.', '......##.', '....###..', '...##....', '...##....', '.........', '...##....'],

  // ---- Guides
  // A bus with three branches: one call fanned out to three.
  'page:orchestration-extensions': ['....#####', '....#.###', '....#....', '###.#.###', '#########', '###.#.###', '....#....', '....#.###', '....#####'],
  // A picture: a frame round a hill and a sun.
  'page:modality-handling': ['#########', '#.......#', '#.....#.#', '#.......#', '#...#...#', '#..###..#', '#.#####.#', '#########', '.........'],
  // A bullseye with a solid centre.
  'page:oasf-coverage': ['..#####..', '.##...##.', '##.....##', '#..###..#', '#..###..#', '#..###..#', '##.....##', '.##...##.', '..#####..'],
  // A fish hook: eye, shank and barbed bend.
  'page:hooks': ['.....###.', '.....#.#.', '.....###.', '......#..', '.#....#..', '##....#..', '.#....#..', '.##..##..', '..####...'],
  // A light bulb.
  'page:examples': ['..#####..', '.#.....#.', '#.......#', '#...#...#', '.#..#..#.', '..#.#.#..', '..#####..', '..#####..', '...###...'],
  // Four tiles, one only a dotted outline: the gap.
  'page:capability-gap-analysis': ['####.#.#.', '####....#', '####.#...', '####..#.#', '.........', '####.####', '####.####', '####.####', '####.####'],
  // A wrench: open jaw and a handle with a hole.
  'page:debug-workflow': ['##.....##', '##.....##', '###...###', '.#######.', '..#####..', '...###...', '...###...', '...#.#...', '...###...'],
  // A boot, for bootstrapping.
  'page:digital-twin-bootstrap': ['.####....', '.#..#....', '.####....', '.####....', '.####....', '.######..', '.#######.', '.########', '.########'],
  // Two arrows chasing each other round a square: a sync loop.
  'page:digital-twin-sync-loop': ['..#......', '.#######.', '..#....#.', '.......#.', '.#.....#.', '.#.......', '.#....#..', '.#######.', '......#..'],
  // Binoculars.
  'page:discover-capabilities': ['.........', '.##...##.', '.#######.', '####.####', '#..#.#..#', '#..#.#..#', '#..#.#..#', '####.####', '.........'],
  // A cube drawn in perspective.
  'page:perspective-validation': ['...######', '..#....##', '.#....#.#', '######..#', '#....#..#', '#....#..#', '#....#.#.', '#....##..', '######...'],
  // Three tick boxes, each with a line beside it.
  'page:perspective-checklist': ['##.######', '##.......', '.........', '##.######', '##.......', '.........', '##.######', '##.......', '.........'],
  // A dashed outline with one tile placed in it: a template to fill.
  'page:skill-template': ['##.###.##', '#.......#', '..###....', '#.###...#', '..###....', '.........', '#.......#', '#.......#', '##.###.##'],
  // A box with an arrow out to a bar: what the skill hands on.
  'page:output-contracts': ['........#', '........#', '###..#..#', '#.#..##.#', '#.#####.#', '#.#..##.#', '###..#..#', '........#', '........#'],
  // Two L-shaped pieces locked together above a base.
  'page:skill-composition-patterns': ['######...', '######...', '##....###', '##....###', '##.######', '##.######', '.........', '#########', '#########'],
  // Two ticks, one after the other.
  'page:verification-patterns': ['.........', '........#', '.......##', '#.....##.', '##...##.#', '.##.##.##', '..###.##.', '...#.##..', '.....#...'],

  // ---- Compliance
  // A gauge: a half dial with its needle.
  'page:risk-classification': ['.........', '.........', '..#####..', '.#.....#.', '#.#.....#', '#..#....#', '#...##..#', '#########', '.........'],
  // A ring binder with two label windows.
  'page:annex-iv': ['..#######', '###.....#', '..#.###.#', '..#.....#', '###.....#', '..#.###.#', '..#.....#', '###.....#', '..#######'],
  // Four boxes in a loop: plan, do, check, act.
  'page:quality-management-system': ['###...###', '#.#####.#', '###...###', '.#.....#.', '.#.....#.', '.#.....#.', '###...###', '#.#####.#', '###...###'],
  // A monitor on a stand, showing bars.
  'page:post-market-monitoring': ['#########', '#.......#', '#.....#.#', '#...#.#.#', '#.#.#.#.#', '#########', '....#....', '..#####..', '.........'],
  // An identity badge on a clip: photo square and two lines.
  'page:notified-body-assessment': ['...###...', '#########', '#########', '#.##.##.#', '#.##....#', '#.##.##.#', '#.......#', '#########', '.........'],
  // A hub with four parties around it.
  'page:stakeholder-analysis': ['##.....##', '##.....##', '..#...#..', '...###...', '...###...', '...###...', '..#...#..', '##.....##', '##.....##'],
  // A padlock.
  'page:ai-policy-template': ['..#####..', '.##...##.', '.#.....#.', '#########', '#########', '####.####', '####.####', '#########', '#########'],
  // A sticking plaster.
  'page:risk-treatment-plan': ['.........', '.........', '.#######.', '###.#.###', '####.####', '###.#.###', '.#######.', '.........', '.........'],
  // A ladder.
  'page:competency-framework': ['#.......#', '#########', '#.......#', '#########', '#.......#', '#########', '#.......#', '#########', '#.......#'],
  // A clipboard with ticked rows.
  'page:internal-audit-checklist': ['...###...', '##.#.#.##', '#.......#', '#.#.###.#', '#.......#', '#.#.###.#', '#.......#', '#.#.###.#', '#########'],
  // A pie chart with one quarter filled.
  'page:management-review': ['..#####..', '.#..####.', '#...#####', '#...#####', '#...#####', '#.......#', '#.......#', '.#.....#.', '..#####..'],
  // A cross in a box.
  'page:nonconformity-procedure': ['#########', '##.....##', '#.#...#.#', '#..#.#..#', '#...#...#', '#..#.#..#', '#.#...#.#', '##.....##', '#########'],
  // Govern above map, measure and manage: one block over a hub of three.
  'page:nist-ai-rmf': ['..#####..', '..#####..', '....#....', '...###...', '...###...', '..#...#..', '###...###', '###...###', '.........'],

  // ---- Background
  // A closed book with a banded spine.
  'page:whitepaper': ['.#######.', '.#=#...#.', '.#=#...#.', '.#=#.#.#.', '.#=#...#.', '.#=#...#.', '.#=#...#.', '.#######.', '.........'],
  // A sprout above the ground line with roots below it.
  'page:grounded-agency': ['.##...##.', '..##.##..', '....#....', '....#....', '#########', '....#....', '..#.#.#..', '.#..#..#.', '#...#...#'],
  // Axes from an origin, with the origin marked.
  'page:first-principles': ['#........', '#........', '#........', '#........', '#..##....', '#..##....', '#........', '#########', '.........'],
  // A bin with a lid.
  'page:rejected-candidates': ['...###...', '#########', '.........', '.#######.', '.#.#.#.#.', '.#.#.#.#.', '.#.#.#.#.', '.#.#.#.#.', '.#######.'],
  // An umbrella: what is covered.
  'page:workflow-coverage': ['....#....', '..#####..', '.#######.', '#########', '....#....', '....#....', '....#....', '..#.#....', '...#.....'],
  // An arched doorway.
  'page:agent-architecture': ['..#####..', '.#######.', '###...###', '##.....##', '##.....##', '##.....##', '##.....##', '##.....##', '###...###'],
  // A spirit level with its bubble.
  'page:skills-alignment': ['.........', '.........', '#########', '#..#=#..#', '#..#=#..#', '#########', '.........', '.........', '.........'],
  // A tree of kinds: one parent, two children.
  'page:failure-taxonomy': ['...###...', '...###...', '....#....', '.#######.', '.#.....#.', '###...###', '###...###', '.........', '.........'],
  // A U-turn arrow.
  'page:replanning': ['..###....', '.#...#...', '#.....#..', '#.....#..', '#...#####', '#....###.', '#.....#..', '#........', '#........'],
  // Two overlapping rings.
  'page:oasf-comparison': ['.........', '.###.###.', '#...#...#', '#..#.#..#', '#..#.#..#', '#..#.#..#', '#...#...#', '.###.###.', '.........'],
  // A map pin.
  'page:capability-mapping': ['..#####..', '.#######.', '###...###', '###...###', '.#######.', '..#####..', '...###...', '....#....', '.........'],
  // A stopwatch.
  'page:benchmarks': ['...###...', '....#....', '..#####..', '.#.....#.', '#...#...#', '#...###.#', '#.......#', '.#.....#.', '..#####..'],
  // Two arrows meeting point to point.
  'page:disagreements': ['....#....', '....#....', '..#####..', '...###...', '.........', '...###...', '..#####..', '....#....', '....#....'],

  // ---- Community
  // A gift box with a bow.
  'page:contributing': ['.##...##.', '...#.#...', '#########', '#########', '.........', '.###.###.', '.###.###.', '.###.###.', '.###.###.'],
  // A crown.
  'page:governance': ['.........', '#...#...#', '##.###.##', '#########', '#########', '.........', '#########', '.........', '.........'],
  // A heart.
  'page:code-of-conduct': ['.........', '.###.###.', '#########', '#########', '#########', '.#######.', '..#####..', '...###...', '....#....'],
  // A milestone on a road that runs on to an arrow.
  'page:roadmap': ['.........', '.........', '.........', '......#..', '###...##.', '#.#######', '###...##.', '......#..', '.........'],
  // A rocket.
  'page:release-notes': ['....#....', '...###...', '...#.#...', '...###...', '...###...', '..#####..', '.##.#.##.', '.#..#..#.', '....#....'],
  // A pair of quotation marks.
  'page:citation': ['.........', '.........', '###..###.', '###..###.', '###..###.', '..#....#.', '.#....#..', '.........', '.........'],
  // A microphone on a stand.
  'page:press-kit': ['...###...', '..#####..', '..#####..', '..#####..', '.#.###.#.', '.#.....#.', '..#####..', '....#....', '..#####..'],

  // ---- RFCs
  // A box with an arrow rising out of it: an extension.
  'page:oasf-safety-extensions': ['....#....', '...###...', '..#####..', '....#....', '#...#...#', '#.......#', '#.......#', '#.......#', '#########'],
};

/**
 * The glyph of each page that can appear as a card, by URL. A listing card
 * for a page missing here fails the build (SectionIndex), so a new page gets
 * a glyph on purpose.
 */
export const PAGE_GLYPHS: Readonly<Record<string, string>> = {
  '/start/overview/': 'page:overview',
  '/start/quickstart/': 'page:quickstart',
  '/start/tutorial/': 'page:tutorial',
  '/start/faq/': 'page:faq',
  '/start/glossary/': 'chapter:terms',

  '/guides/running-workflows/': 'tool:executor',
  '/guides/orchestration-extensions/': 'page:orchestration-extensions',
  '/guides/modality-handling/': 'page:modality-handling',
  '/guides/claude-agent-sdk/': 'tool:sdk',
  '/guides/oasf-coverage/': 'page:oasf-coverage',
  '/guides/hooks/': 'page:hooks',
  '/guides/examples/': 'page:examples',
  '/guides/skills/': 'skill:composed',
  '/guides/skills/capability-gap-analysis/': 'page:capability-gap-analysis',
  '/guides/skills/debug-workflow/': 'page:debug-workflow',
  '/guides/skills/digital-twin-bootstrap/': 'page:digital-twin-bootstrap',
  '/guides/skills/digital-twin-sync-loop/': 'page:digital-twin-sync-loop',
  '/guides/skills/discover-capabilities/': 'page:discover-capabilities',
  '/guides/skills/perspective-validation/': 'page:perspective-validation',
  '/guides/skills/perspective-validation/checklist/': 'page:perspective-checklist',
  '/guides/skill-authoring/': 'group:skill-authoring',
  '/guides/skill-authoring/skill-template-enhanced/': 'page:skill-template',
  '/guides/skill-authoring/output-contracts/': 'page:output-contracts',
  '/guides/skill-authoring/composition-patterns/': 'page:skill-composition-patterns',
  '/guides/skill-authoring/verification-patterns/': 'page:verification-patterns',

  '/compliance/eu-ai-act/': 'group:regulation',
  '/compliance/eu-ai-act/risk-classification/': 'page:risk-classification',
  '/compliance/eu-ai-act/annex-iv-technical-documentation/': 'page:annex-iv',
  '/compliance/eu-ai-act/quality-management-system/': 'page:quality-management-system',
  '/compliance/eu-ai-act/post-market-monitoring/': 'page:post-market-monitoring',
  '/compliance/eu-ai-act/notified-body-assessment/': 'page:notified-body-assessment',
  '/compliance/iso-42001/': 'group:standard-cert',
  '/compliance/iso-42001/stakeholder-analysis/': 'page:stakeholder-analysis',
  '/compliance/iso-42001/ai-policy-template/': 'page:ai-policy-template',
  '/compliance/iso-42001/risk-treatment-plan/': 'page:risk-treatment-plan',
  '/compliance/iso-42001/competency-framework/': 'page:competency-framework',
  '/compliance/iso-42001/internal-audit-checklist/': 'page:internal-audit-checklist',
  '/compliance/iso-42001/management-review/': 'page:management-review',
  '/compliance/iso-42001/nonconformity-procedure/': 'page:nonconformity-procedure',
  '/compliance/nist-ai-rmf/': 'page:nist-ai-rmf',

  '/background/whitepaper/': 'page:whitepaper',
  '/background/grounded-agency/': 'page:grounded-agency',
  '/background/methodology/first-principles-reassessment/': 'page:first-principles',
  '/background/methodology/rejected-candidates/': 'page:rejected-candidates',
  '/background/methodology/workflow-coverage/': 'page:workflow-coverage',
  '/background/methodology/agent-architecture-research/': 'page:agent-architecture',
  '/background/methodology/skills-alignment-evaluation/': 'page:skills-alignment',
  '/background/research/failure-taxonomy/': 'page:failure-taxonomy',
  '/background/research/replanning-capabilities/': 'page:replanning',
  '/background/research/oasf-comparison/': 'page:oasf-comparison',
  '/background/research/capability-mapping/': 'page:capability-mapping',
  '/background/research/benchmarks/': 'page:benchmarks',
  '/background/research/validator-engine-disagreements-1-0/': 'page:disagreements',

  '/community/contributing/': 'page:contributing',
  '/community/governance/': 'page:governance',
  '/community/code-of-conduct/': 'page:code-of-conduct',
  '/community/roadmap/': 'page:roadmap',
  '/community/release-notes/': 'page:release-notes',
  '/community/citation/': 'page:citation',
  '/community/press-kit/': 'page:press-kit',

  '/rfcs/proposals/oasf-safety-extensions/': 'page:oasf-safety-extensions',
};

/**
 * Grids for cards on the home page that showed the same glyph as another card
 * there: the count cards next to the chapters they count, the two §5
 * subsections next to their chapter, and the Conformance chapter next to the
 * conformance suite. glyphs.ts spreads these into CONCEPT_GLYPHS.
 */
export const CARD_GRIDS: Readonly<Record<string, readonly string[]>> = {
  // A field of tiles, as many as fit: the capabilities, counted.
  'count:capabilities': ['#.#.#.#.#', '.........', '#.#.#.#.#', '.........', '#.#.#.#.#', '.........', '#.#.#.#.#', '.........', '#.#.#.#.#'],
  // Rows of steps of different lengths: the workflows, counted.
  'count:workflows': ['.........', '##.##.##.', '.........', '##.##....', '.........', '##.##.##.', '.........', '##.......', '.........'],
  // A list of codes, each a short tag and a line: the diagnostic codes, counted.
  'count:diagnostics': ['##.######', '.........', '##.####..', '.........', '##.######', '.........', '##.###...', '.........', '##.#####.'],
  // A ruler: the measure an implementation is held to (the Standard's
  // conformance chapter, apart from the conformance suite's test tube).
  'chapter:conformance': ['.........', '.........', '#########', '#.#.#.#.#', '#.#...#.#', '#.......#', '#########', '.........', '.........'],
  // A decision diamond with two branches.
  'topic:condition-expressions': ['....#....', '...#.#...', '..#...#..', '...#.#...', '....#....', '....#....', '.#######.', '.#.....#.', '.#.....#.'],
  // A solid step joined to a dashed one: what a workflow adds.
  'topic:workflow-extensions': ['.........', '####.##.#', '####.....', '####....#', '#####....', '####....#', '####.....', '####.#.##', '.........'],
};
