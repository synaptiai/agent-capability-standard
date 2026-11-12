// Every glyph of the site as a character grid (see grid.ts for the
// characters). Data only: its imports are more data, so the check scripts
// can load it with plain `node`.
import { GROUP_ALIASES, GROUP_GLYPHS } from './glyphs-groups.ts';
import { CARD_GRIDS, PAGE_GRIDS } from './glyphs-pages.ts';
import { PROSE_ALIASES } from './glyphs-prose.ts';

/** One 9x9 glyph per cognitive layer, keyed by the layer id in the ontology. */
export const LAYER_GLYPHS: Readonly<Record<string, readonly string[]>> = {
  // An eye
  PERCEIVE: [
    '.........',
    '..#####..',
    '.#.....#.',
    '#..###..#',
    '#..#=#..#',
    '#..###..#',
    '.#.....#.',
    '..#####..',
    '.........',
  ],
  // A light bulb
  UNDERSTAND: [
    '...###...',
    '..#===#..',
    '.#=====#.',
    '.#==#==#.',
    '.#==#==#.',
    '..#=#=#..',
    '...###...',
    '...###...',
    '....#....',
  ],
  // A plan tree
  REASON: [
    '....#....',
    '....#....',
    '..#####..',
    '..#...#..',
    '..#...#..',
    '.###.###.',
    '.#=#.#=#.',
    '.###.###.',
    '.........',
  ],
  // A cube
  MODEL: [
    '...###...',
    '.##===##.',
    '#=======#',
    '###===###',
    '#..###..#',
    '#...#...#',
    '#...#...#',
    '.##.#.##.',
    '...###...',
  ],
  // A spark
  SYNTHESIZE: [
    '.........',
    '...#.....',
    '...#.....',
    '..#=#....',
    '##=#=##..',
    '..#=#..#.',
    '...#..#=#',
    '...#...#.',
    '.........',
  ],
  // A play button
  EXECUTE: [
    '.#.......',
    '.##......',
    '.#=#.....',
    '.#==#....',
    '.#===#...',
    '.#==#....',
    '.#=#.....',
    '.##......',
    '.#.......',
  ],
  // A check in a box
  VERIFY: [
    '#########',
    '#.......#',
    '#......##',
    '#.....#.#',
    '##...#..#',
    '#.#.#...#',
    '#..#....#',
    '#.......#',
    '#########',
  ],
  // A stack of records
  REMEMBER: [
    '..#####..',
    '.#=====#.',
    '.#######.',
    '.#.....#.',
    '.#######.',
    '.#.....#.',
    '.#######.',
    '.#.....#.',
    '..#####..',
  ],
  // Three connected nodes
  COORDINATE: [
    '...###...',
    '...#=#...',
    '...###...',
    '....#....',
    '...#.#...',
    '..#...#..',
    '###...###',
    '#=#...#=#',
    '###...###',
  ],
};

/** 7x7 glyphs for flags, diagram roles, callouts and controls. */
export const UI_GLYPHS: Readonly<Record<string, readonly string[]>> = {
  // A rectangular banner with a swallowtail on a pole.
  flag: ['#######', '#====#.', '#===#..', '#====#.', '#######', '#......', '#......'],
  pencil: ['.....##', '....#=#', '...#=#.', '..#=#..', '.#=#...', '##.....', '#......'],
  stamp: ['..###..', '..###..', '...#...', '...#...', '.#####.', '#=====#', '#######'],
  undo: ['..#....', '.##....', '#######', '.##...#', '..#...#', '......#', '..####.'],
  diamond: ['...#...', '..#=#..', '.#===#.', '#==#==#', '.#===#.', '..#=#..', '...#...'],
  fork: ['...#...', '...#...', '..###..', '.#...#.', '#.....#', '#.....#', '#.....#'],
  nested: ['#######', '#.....#', '#.###.#', '#.#=#.#', '#.###.#', '#.....#', '#######'],
  check: ['.......', '......#', '.....##', '#...##.', '##.##..', '.###...', '..#....'],
  eye: ['.......', '..###..', '.#...#.', '#..#..#', '.#...#.', '..###..', '.......'],
  search: ['.###...', '#...#..', '#...#..', '#...#..', '.###...', '....##.', '.....##'],
  menu: ['.......', '#######', '.......', '#######', '.......', '#######', '.......'],
  close: ['#.....#', '.#...#.', '..#.#..', '...#...', '..#.#..', '.#...#.', '#.....#'],
  sun: ['...#...', '.#...#.', '..###..', '#.###.#', '..###..', '.#...#.', '...#...'],
  moon: ['..###..', '.##....', '##.....', '##.....', '##.....', '.##....', '..###..'],
  half: ['..###..', '.#..##.', '#...###', '#...###', '#...###', '.#..##.', '..###..'],
  'chevron-left': ['....##.', '...##..', '..##...', '.##....', '..##...', '...##..', '....##.'],
  'chevron-right': ['.##....', '..##...', '...##..', '....##.', '...##..', '..##...', '.##....'],
  copy: ['####...', '#..#...', '#.####.', '#.#..#.', '###..#.', '..#..#.', '..####.'],
  external: ['....###', '.....##', '#...#.#', '#..#...', '#......', '#......', '#####..'],
  hash: ['.#..#..', '.#..#..', '#######', '.#..#..', '#######', '.#..#..', '.#..#..'],
  // A prompt chevron and an underscore.
  code: ['.......', '##.....', '.##....', '..##...', '.##....', '##.####', '.......'],
  // An "i" in a square.
  note: ['#######', '#..#..#', '#.....#', '#.##..#', '#..#..#', '#.###.#', '#######'],
  warning: ['...#...', '..###..', '..#.#..', '.#.#.#.', '.#...#.', '#..#..#', '#######'],
  // A solid octagon with an exclamation mark cut out of it.
  caution: ['..###..', '.##.##.', '###.###', '###.###', '#######', '###.###', '..###..'],
  // ---- Inline glyphs added for the figures (visual spec 2.3). Keys with a
  // colon belong to a group; `stop` is shared by gate:stop and fail:stop.

  // Risk: one, two or three bars from the bottom; high adds an exclamation
  // mark. Low and medium are full width and high is a different silhouette
  // (bars cut by the mark), so the three differ by 14 cells or more.
  'risk:low': ['.......', '.......', '.......', '.......', '.......', '#######', '#######'],
  'risk:medium': ['.......', '.......', '#######', '#######', '.......', '#######', '#######'],
  'risk:high': ['#####.#', '#####.#', '......#', '#####.#', '#####..', '.......', '#####.#'],
  // Gate actions. skip: a hop over a post; end: an arrow into a bar.
  'gate:skip': ['..###..', '.#...#.', '.#...#.', '.#..###', '.....#.', '.......', '#######'],
  // A stop sign's outline (a thick octagon ring), not the solid square of
  // visual spec 2.3: a solid square already means "required" on input pins,
  // and a page that showed both read as one mark with two meanings.
  stop: ['.#####.', '#######', '##...##', '##...##', '##...##', '#######', '.#####.'],
  'gate:end': ['......#', '..#...#', '..##..#', '#####.#', '..##..#', '..#...#', '......#'],
  // Failure actions.
  'fail:request_more_context': ['#######', '##...##', '####.##', '###.###', '#######', '###.###', '##.....'],
  'fail:pause_and_checkpoint': ['.##.##.', '.##.##.', '.##.##.', '.##.##.', '.##.##.', '.##.##.', '.##.##.'],
  'fail:escalate': ['#######', '.......', '...#...', '..###..', '.#.#.#.', '...#...', '...#...'],
  // Data flow. store: an arrow down into a box; read: an arrow out of a box; join: fork upside down.
  'flow:store': ['...#...', '.#.#.#.', '..###..', '#..#..#', '#.....#', '#.....#', '#######'],
  'flow:read': ['.......', '####...', '#..#.#.', '#..####', '#..#.#.', '####...', '.......'],
  'flow:join': ['#.....#', '#.....#', '#.....#', '.#...#.', '..###..', '...#...', '...#...'],
  // Field-type families. open: a five-armed asterisk, apart from the close X
  // and the sun.
  'type:text': ['.......', '##..##.', '##..##.', '.#...#.', '#...#..', '.......', '.......'],
  'type:number': ['...#...', '..##...', '.#.#...', '...#...', '...#...', '...#...', '.#####.'],
  'type:boolean': ['.......', '#######', '####..#', '####..#', '####..#', '#######', '.......'],
  'type:list': ['##...##', '#.....#', '#.....#', '#.#.#.#', '#.....#', '#.....#', '##...##'],
  'type:record': ['.##.##.', '.#...#.', '.#...#.', '#..#..#', '.#...#.', '.#...#.', '.##.##.'],
  'type:open': ['...#...', '...#...', '##.#.##', '..###..', '.##.##.', '##...##', '.......'],
  // Approval and checkpoint policy. blocked: a padlock with a wide shackle and
  // a solid body (apart from the REASON tree); always: two squares sharing an edge.
  'approve:blocked': ['.#####.', '.#...#.', '.#...#.', '#######', '#######', '###.###', '#######'],
  'policy:always': ['.......', '#######', '#..#..#', '#..#..#', '#######', '.......', '.......'],
  // Lifecycle and document statuses (visual spec 2.3, extended to every
  // status style the sources use; see STATUS_STYLES in src/lib/status.ts).
  // draft: a pencil tip over a dashed line.
  'status:draft': ['....##.', '...#=#.', '..#=#..', '.##....', '.......', '#.#.#.#', '.......'],
  // accepted: a check over a solid bar.
  'status:accepted': ['......#', '.....##', '#...##.', '##.##..', '.###...', '.......', '#######'],
  // rejected: a small X over a solid bar.
  'status:rejected': ['.#...#.', '..#.#..', '...#...', '..#.#..', '.#...#.', '.......', '#######'],
  // superseded: an arrow passing over a bar.
  'status:superseded': ['...#...', '....#..', '#######', '....#..', '...#...', '.......', '#######'],
  // normative: a ruler (a bar with ticks), the rule itself.
  'status:normative': ['.......', '.......', '#.#.#.#', '#.#.#.#', '#######', '#######', '.......'],
  // normative reference: a push pin.
  'status:normative-reference': ['.#####.', '..###..', '..###..', '.#####.', '#######', '...#...', '...#...'],
  // reference: a bookmark ribbon.
  'status:reference': ['.#####.', '.#####.', '.#####.', '.#####.', '.##.##.', '.#...#.', '.......'],
  // analysis: plus and minus, for a weighing of pros and cons.
  'status:analysis': ['.##....', '######.', '######.', '.##....', '.......', '..#####', '..#####'],
  // historical: an hourglass with sand in the lower bulb.
  'status:historical': ['#######', '.#...#.', '..#.#..', '...#...', '..#=#..', '.#===#.', '#######'],
  // candidate: a ticket with notches and a perforation.
  'status:candidate': ['#######', '##.####', '#######', '.#.###.', '#######', '##.####', '#######'],
  // Skills and agents. capability: an outline tile lifted by a shadow;
  // general-purpose: a wrench.
  'skill:capability': ['.......', '####...', '#..##..', '#..##..', '#####..', '.####..', '.......'],
  'agent:general-purpose': ['.#.#...', '.###...', '..#....', '..#....', '...#...', '....##.', '....##.'],
  // A folder with a tab, for directory-tree panels.
  folder: ['.......', '###....', '#######', '#######', '#.....#', '#######', '.......'],
  // A group: two boxes under one bracket (a parallel group, a Mermaid subgraph).
  group: ['#######', '#.....#', '.......', '###.###', '#=#.#=#', '###.###', '.......'],
  // proposed: a dashed outline square.
  'status:proposed': ['#.#.#.#', '.......', '#.....#', '.......', '#.....#', '.......', '#.#.#.#'],
  // An empty tray, open at the top.
  empty: ['.......', '#.....#', '#.....#', '#.....#', '#.....#', '#######', '.......'],
  // Edge-type marks: one per ontology edge type, used at every size.
  // precedes: two thick chevrons (>>), far from soft_requires' dotted line;
  // enables: a chevron, a line and an open box, far from alternative_to's
  // double arrow.
  'mark:requires': ['.......', '....#..', '####.#.', '####..#', '####.#.', '....#..', '.......'],
  'mark:soft_requires': ['...#...', '....#..', '.....#.', '#.#.#.#', '.....#.', '....#..', '...#...'],
  'mark:enables': ['.......', '.#..###', '..#...#', '####..#', '..#...#', '.#..###', '.......'],
  'mark:precedes': ['##..##.', '.##..##', '..##..#', '...##..', '..##..#', '.##..##', '##..##.'],
  'mark:conflicts_with': ['...#...', '#..#..#', '##.#.##', '#######', '##.#.##', '#..#..#', '...#...'],
  'mark:alternative_to': ['.......', '.#...#.', '##...##', '#######', '##...##', '.#...#.', '.......'],
  'mark:specializes': ['...#...', '..#.#..', '.#...#.', '#######', '...#...', '...#...', '..###..'],
  pip: ['##', '##'],
};

/**
 * 9x9 concept glyphs (visual spec 2.2), keyed `group:id`. Drawn in --ink and
 * coloured by context. Concepts that reuse another glyph are in
 * GLYPH_ALIASES, never redrawn.
 */
export const CONCEPT_GLYPHS: Readonly<Record<string, readonly string[]>> = {
  // ---- Site sections (section:home is the mark)
  // Two footprints, the left one a cell higher.
  'section:start': ['..##.....', '.###.##..', '.###.###.', '.###.###.', '..##.###.', '.....##..', '..##.....', '..##.##..', '.....##..'],
  // A page with a folded corner and three rule lines.
  'section:spec': ['.#####...', '.#...##..', '.#...###.', '.#.###.#.', '.#.....#.', '.#.###.#.', '.#.....#.', '.#.###.#.', '.#######.'],
  // Nine tiles, one lifted by a shadow.
  'section:capabilities': ['##.##.##.', '##.##.##=', '.......==', '##.##.##.', '##.##.##.', '.........', '##.##.##.', '##.##.##.', '.........'],
  // Three boxes in a row, joined.
  'section:workflows': ['.........', '.........', '##.###.##', '##.###.##', '#########', '##.###.##', '##.###.##', '.........', '.........'],
  // A globe: a ring with one meridian and one parallel.
  'section:domains': ['..#####..', '.#..#..#.', '#...#...#', '#...#...#', '#########', '#...#...#', '#...#...#', '.#..#..#.', '..#####..'],
  // An open book seen from above, split at the spine.
  'section:guides': ['.........', '###...###', '#..#.#..#', '#=.#.#.=#', '#..#.#..#', '#=.#.#.=#', '####.####', '....#....', '.........'],
  // A shield with a check cut into it.
  'section:compliance': ['#########', '#########', '######.##', '#####.###', '##.#.####', '.##.####.', '..#####..', '...###...', '....#....'],
  // A speech box with three dots and a tail at the bottom left.
  'section:rfcs': ['.........', '#########', '#.......#', '#.#.#.#.#', '#.......#', '#########', '.##......', '.#.......', '.........'],
  // A classical column: capital, fluted shaft, base.
  'section:background': ['#########', '.#######.', '..#.#.#..', '..#.#.#..', '..#.#.#..', '..#.#.#..', '..#.#.#..', '.#######.', '#########'],
  // A round table from above: a centre block with a seat on each side.
  'section:community': ['...###...', '...###...', '.........', '##.###.##', '##.###.##', '##.###.##', '.........', '...###...', '...###...'],

  // ---- Chapters of the Standard, keyed by title slug (see chapterKey)
  // Four corner brackets, like a viewfinder.
  'chapter:scope': ['###...###', '#.......#', '#.......#', '.........', '....#....', '.........', '#.......#', '#.......#', '###...###'],
  // "Aa".
  'chapter:terms': ['.........', '.###.....', '#...#....', '#...#.###', '#####...#', '#...#.###', '#...#.#.#', '#...#.###', '.........'],
  // A four-point star.
  'chapter:design-principles': ['....#....', '....#....', '....#....', '...###...', '#########', '...###...', '....#....', '....#....', '....#....'],
  // Two key-value rows: a short bar, a colon, a long bar.
  'chapter:canonical-schemas': ['.........', '##.#.####', '##...####', '##.#.####', '.........', '##.#.####', '##...####', '##.#.####', '.........'],
  // A fingerprint whorl of three nested loops.
  'chapter:identity-resolution-policy': ['..#####..', '.#.....#.', '#..###..#', '#.#...#.#', '#.#.#.#.#', '#.#.#.#.#', '#.#.#.#.#', '..#.#.#..', '....#....'],
  // A balance scale.
  'chapter:authority-trust-model': ['....#....', '.#######.', '.#..#..#.', '#.#.#.#.#', '###.#.###', '....#....', '....#....', '..#####..', '.........'],
  // A beetle: an oval body with three legs a side.
  'chapter:diagnostic-model': ['..#...#..', '...###...', '#.#####.#', '.#######.', '#.##.##.#', '.###.###.', '#.##.##.#', '..##.##..', '...###...'],
  // A tag with a hole.
  'chapter:versioning-and-compatibility': ['.........', '...######', '..#######', '.########', '###.#####', '.########', '..#######', '...######', '.........'],
  // A signpost: a pole and two long arms pointing opposite ways (not a
  // solid block, so it reads apart from the stop ring).
  'chapter:decision-frameworks': ['....#....', '#######..', '########.', '#######..', '....#....', '..#######', '.########', '..#######', '....#....'],

  // ---- Domain profiles, keyed by profile file stem
  // A speaker cone and a three-bar waveform.
  'domain:audio': ['......#..', '......#..', '..#...#.#', '###.#.#.#', '###.#.#.#', '###.#.#.#', '..#...#.#', '......#..', '......#..'],
  // Three columns on a baseline, the tallest in the middle.
  'domain:data_analysis': ['.........', '...###...', '...###...', '...###...', '...###.##', '##.###.##', '##.###.##', '##.###.##', '#########'],
  // A plus cross with a pulse line through it.
  'domain:healthcare': ['...###...', '...###...', '...###...', '###.#####', '...#.....', '####.####', '...###...', '...###...', '...###...'],
  // A gear of eight teeth around a hollow centre.
  'domain:manufacturing': ['#...#...#', '.#######.', '.##...##.', '.#.....#.', '##.....##', '.#.....#.', '.##...##.', '.#######.', '#...#...#'],
  // Three overlapping outline squares.
  'domain:multimodal': ['#####....', '#...#....', '#.#####..', '#.#.#.#..', '#########', '..#.#.#.#', '..#####.#', '....#...#', '....#####'],
  // A calendar page with a tick.
  'domain:personal_assistant': ['.#.....#.', '#########', '#########', '#.......#', '#.....#.#', '#.#..#..#', '#..##...#', '#.......#', '#########'],
  // A camera body with a round lens.
  'domain:vision': ['..###....', '#########', '###...###', '##.###.##', '#.#####.#', '#.#####.#', '#.#####.#', '##.###.##', '###...###'],

  // ---- Tools, keyed by the home page's tool cards
  // A filter funnel.
  'tool:validator': ['#########', '#########', '.#######.', '..#####..', '...###...', '...###...', '...###...', '...###...', '....#....'],
  // A play triangle in a frame.
  'tool:executor': ['#########', '#.......#', '#.##....#', '#.####..#', '#.#####.#', '#.####..#', '#.##....#', '#.......#', '#########'],
  // A plug with two prongs.
  'tool:plugin': ['..#...#..', '..#...#..', '..#...#..', '#########', '#########', '.#######.', '..#####..', '....#....', '....#....'],
  // A toolbox with a handle.
  'tool:sdk': ['.........', '...###...', '...#.#...', '#########', '#########', '###.#.###', '#########', '#########', '.........'],
  // A test tube with three level marks.
  'tool:conformance': ['..#####..', '...#.#...', '...#.##..', '...#.#...', '...#.##..', '...###...', '...####..', '...###...', '....#....'],

  // ---- Trust-source types, keyed by domain_sources[].type
  // Two arrows pointing opposite ways.
  'source:api': ['.........', '......#..', '########.', '......#..', '.........', '..#......', '.########', '..#......', '.........'],
  // Three solid discs stacked, like a database cylinder.
  'source:database': ['.#######.', '#########', '.........', '.#######.', '#########', '.........', '.#######.', '#########', '.#######.'],
  // A head and shoulders.
  'source:human': ['...###...', '..#####..', '..#####..', '...###...', '.........', '.#######.', '#########', '#########', '#########'],
  // A dot with two stepped quarter-rings.
  'source:sensor': ['.........', '#####....', '.....#...', '......#..', '###....#.', '...#...#.', '....#..#.', '##..#..#.', '##..#..#.'],
  // A scroll: a sheet rolled at the top and bottom.
  'source:document': ['#########', '#########', '.#.....#.', '.#.....#.', '.#.....#.', '.#.....#.', '.#.....#.', '#########', '#########'],
  // A terminal with a prompt and an underscore.
  'source:system_log': ['#########', '#########', '#.......#', '#.#.....#', '#..#....#', '#.#..##.#', '#.......#', '#########', '.........'],

  // ---- Design principles, keyed by the slug of the Standard's section 3 headings
  // An anchor.
  'principle:grounded-claims': ['...###...', '...#.#...', '...###...', '.#######.', '....#....', '#...#...#', '##..#..##', '.##.#.##.', '..#####..'],
  // A dotted trail into an open box.
  'principle:auditable-transforms': ['.........', '#.#.#....', '.........', '....#.#.#', '....#...#', '....#...#', '....#...#', '....#####', '.........'],
  // A brick wall under a capstone.
  'principle:safety-by-construction': ['.#######.', '##.###.##', '##.###.##', '.........', '####.####', '####.####', '.........', '##.###.##', '##.###.##'],
  // A jigsaw piece with one tab and one notch.
  'principle:composable-atoms': ['...###...', '...###...', '.#######.', '.#######.', '.####....', '.####....', '.#######.', '.#######.', '.........'],
  // A key with a square bow.
  'principle:explicit-contracts': ['.........', '.........', '####.....', '#..#.....', '#..######', '#..#..#.#', '####..#.#', '.........', '.........'],

  // ---- Counts on the home page
  // Three slabs stacked with a gap.
  'count:layers': ['.........', '#########', '#########', '.........', '#########', '#########', '.........', '#########', '#########'],

  // ---- Listing groups (glyphs-groups.ts)
  ...GROUP_GLYPHS,

  // ---- Single pages and home cards (glyphs-pages.ts)
  ...PAGE_GRIDS,
  ...CARD_GRIDS,
};

/**
 * Concepts drawn with a glyph that already has the same meaning (the "reuse"
 * rows of visual spec 2.2 and 2.3). Two concepts never share a grid by
 * copying it; they share it through this map.
 */
export const GLYPH_ALIASES: Readonly<Record<string, string>> = {
  'chapter:capability-ontology': 'section:capabilities',
  'chapter:workflow-dsl': 'section:workflows',
  'chapter:references': 'section:guides',
  'severity:error': 'caution',
  'severity:warning': 'warning',
  'gate:stop': 'stop',
  'gate:warn': 'warning',
  'gate:rollback': 'undo',
  'fail:stop': 'stop',
  'fail:rollback': 'undo',
  'flow:condition': 'diamond',
  'approve:auto': 'check',
  'approve:review': 'eye',
  'approve:human': 'stamp',
  'policy:high_risk': 'risk:high',
  'policy:medium_risk': 'risk:medium',
  'role:checkpoint': 'flag',
  'role:verify': 'check',
  'role:rollback': 'undo',
  'role:mutating': 'pencil',
  'skill:composed': 'nested',
  'agent:explore': 'search',
  'count:edges': 'mark:enables',
  'count:profiles': 'section:domains',
  'count:skills': 'skill:composed',
  ...GROUP_ALIASES,
  ...PROSE_ALIASES,
};

/** Older chapter titles that name the same chapter (1.0.0 "Error Model" is 1.1.0 "Diagnostic Model"). */
export const CHAPTER_ALIASES: Readonly<Record<string, string>> = {
  'error-model': 'diagnostic-model',
};

/** H2s of the Standard that start with this word get no chapter glyph. */
export const CHAPTER_EXEMPT_PREFIX = 'Appendix';

/**
 * The mark: nine 3x3 blocks, one per cognitive layer, with one-unit gaps on a
 * 12x12 grid. The centre block is the accent. The bottom-right block sits one
 * unit lower and one unit to the right, in the lighter shade, as if it were
 * sliding into its slot.
 */
export const MARK: readonly string[] = [
  '###.###.###.',
  '###.###.###.',
  '###.###.###.',
  '............',
  '###.aaa.###.',
  '###.aaa.###.',
  '###.aaa.###.',
  '............',
  '###.###.....',
  '###.###..===',
  '###.###..===',
  '.........===',
];

/** Letters for the static social image, 5x7 each. */
export const LETTERS: Readonly<Record<string, readonly string[]>> = {
  A: ['.###.', '#...#', '#...#', '#####', '#...#', '#...#', '#...#'],
  C: ['.####', '#....', '#....', '#....', '#....', '#....', '.####'],
  S: ['.####', '#....', '#....', '.###.', '....#', '....#', '####.'],
};
