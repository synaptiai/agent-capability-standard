// What the home page says, in one place, so the page and its Markdown copy
// say the same thing. Counts, versions, names, the design principles, the
// section titles and the scroll story's steps are read from the data and the
// current Standard; only the connecting sentences are written here.
import type { Heading, PhrasingContent, RootContent } from 'mdast';
import { loadCitation } from '../data/citation';
import { loadCounts } from '../data/counts';
import { capabilitiesOfLayer, loadOntology } from '../data/ontology';
import { loadVersions, olderVersionNote } from '../data/versions';
import { loadWorkflows, type Step, type Workflow } from '../data/workflows';
import { anchorsOf, headingText, parseMarkdown, stripFrontmatter } from './anchors';
import { currentStandard, diagnosticHref, routeByUrl, type Inline } from './generated';
import { SITE_ORIGIN } from './links';
import { GITHUB_BASE, readRepoFile } from './repo';
import { PAGE_GLYPHS } from '../pixel/glyphs-pages';
import { chapterKey, principleKey, resolveGlyphKey, slugKey, TOOL_GLYPHS } from '../pixel/keys';
import { kebab } from './routes';
import { contractRows, diagramSteps, gateRows, stepRole, type StepRole } from './views';
import { andList } from './words';

/** The one-sentence summary used as the page description and in llms.txt. */
export function homeDescription(): string {
  const c = loadCounts();
  return `An open specification for composable AI agent capabilities: ${c.capabilityCount} capabilities in ${c.layerCount} layers, a typed workflow language, and a validator.`;
}

export const HOME_H1 = 'The Agent Capability Standard defines what an AI agent can do, and what has to happen before it does it.';

/** The workflow the scroll story is drawn from. */
export const STORY_WORKFLOW = 'model_deployment';

/** A link the page and its copy both show: `url` is a site page URL, or an absolute URL. */
export interface HomeLink {
  text: string;
  url: string;
}

export interface Card {
  title: string;
  line: string;
  link: HomeLink;
  /** Spec section label, e.g. "§5.8", for cards about the Standard. */
  section?: string;
  /** The card's glyph key (visual spec 2.2): a chapter, a count or a tool. */
  glyph?: string;
  /** The hero number of a reference-data card, from loadCounts(). */
  count?: number;
}

/** A sentence with one link in it; `code` shows the link text as code. */
export interface LinkSentence {
  before: string;
  link: HomeLink & { code?: boolean };
  after: string;
}

/** The headings and connecting sentences of the sections, shared by the page and its copy. */
export const STORY_HEADING = 'How a workflow is built';

export function storyIntro(): LinkSentence {
  return {
    before: 'The steps below follow the reference workflow for deploying a model, ',
    link: { text: STORY_WORKFLOW, url: `/workflows/${kebab(STORY_WORKFLOW)}/`, code: true },
    after: '.',
  };
}

export const CAPABILITIES_INTRO: Inline = [
  { code: false, text: 'Domain variants are parameters, not new capabilities: ' },
  { code: true, text: 'detect' },
  { code: false, text: ' with ' },
  { code: true, text: 'domain: anomaly' },
  { code: false, text: ', not ' },
  { code: true, text: 'detect-anomaly' },
  { code: false, text: '.' },
];

export const CAPABILITIES_DERIVED: HomeLink = { text: 'How the set was derived', url: '/background/methodology/first-principles-reassessment/' };

export const AGENTS_HEADING = 'For coding agents';
export const AGENTS_LINE = 'Paste this into Claude Code, Codex, Cursor or another coding agent.';

/** Text with inline code, as one string where code spans are in backticks. */
export function inlineText(parts: Inline): string {
  return parts.map((p) => (p.code ? `\`${p.text}\`` : p.text)).join('');
}

// ------------------------------------------------------------ opening

export function opening() {
  const c = loadCounts();
  const v = loadVersions();
  const std = currentStandard();
  const guarded = loadOntology()
    .edges.filter((e) => e.type === 'requires' && e.from === 'checkpoint')
    .map((e) => e.to);
  if (guarded.length === 0) throw new Error('home: the ontology has no requires edge from checkpoint');
  const summary: Inline = [
    {
      code: false,
      text: `It names ${c.capabilityCount} capabilities in ${c.layerCount} layers. Each capability has a typed input and output contract and a risk level. A workflow language composes them into steps, and a validator checks a workflow before it runs: every value a step reads must come from the workflow's inputs or an earlier step, and `,
    },
    ...guarded.flatMap((g, i) => [
      ...(i === 0 ? [] : [{ code: false, text: i === guarded.length - 1 ? ' and ' : ', ' }]),
      { code: true, text: g },
    ]),
    { code: false, text: ` cannot run unless a checkpoint ran before them.` },
  ];
  const previous = v.standard.previous.map((p) => ({ ...p, note: olderVersionNote(p.version, readRepoFile(std.source)) }));
  const versionLine = [
    `Standard ${v.standard.current.version}, ${v.standard.current.status}.`,
    ...previous.filter((p) => p.note.stillSupported).map((p) => `Version ${p.version} is still supported.`),
    `Licence: ${loadCitation().license}.`,
  ].join(' ');
  const install = readRepoFile('README.md')
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => /^claude plugin (marketplace add|install) \S+$/.test(l));
  const commands = [...new Set(install)];
  if (commands.length !== 2) throw new Error(`home: expected the plugin's marketplace and install commands in README.md, found ${commands.length}`);
  return {
    summary,
    versionLine,
    links: [
      { text: 'Read the specification', url: std.url },
      { text: 'Quickstart', url: '/start/quickstart/' },
    ] satisfies HomeLink[],
    install: { label: `Claude Code plugin ${v.plugin}`, commands },
  };
}

// ------------------------------------------------------------ principles

export interface Principle {
  number: string;
  title: string;
  /** Each block is a paragraph or a bulleted list of lines. */
  blocks: ({ kind: 'p'; text: Inline } | { kind: 'ul'; items: Inline[] })[];
  /** The principle's body as written in the Standard, for the Markdown copy. */
  markdown: string;
  anchor: string;
  /** The principle's glyph key, from its heading (visual spec 2.2). */
  glyph: string;
}

function phrasing(nodes: PhrasingContent[]): Inline {
  const out: Inline = [];
  const push = (code: boolean, text: string) => {
    const last = out.at(-1);
    if (last && last.code === code && !code) last.text += text;
    else out.push({ code, text });
  };
  for (const n of nodes) {
    if (n.type === 'inlineCode') push(true, n.value);
    else if (n.type === 'text') push(false, n.value.replace(/\s*\n\s*/g, ' '));
    else if (n.type === 'break') push(false, ' ');
    else if ('children' in n) for (const p of phrasing(n.children as PhrasingContent[])) push(p.code, p.text);
  }
  return out;
}

/** The design principles of the current Standard: the H3s of its "3. Design Principles" section. */
/** The section of the Standard the design principles are read from. */
const PRINCIPLES_SECTION = '3';

export function principles(): { intro: string; items: Principle[]; sectionUrl: string; source: LinkSentence } {
  const std = currentStandard();
  const text = readRepoFile(std.source);
  const tree = parseMarkdown(text);
  const body = stripFrontmatter(text);
  const nodes = tree.children;
  const h2 = nodes.findIndex((n) => n.type === 'heading' && n.depth === 2 && headingText(n).startsWith(`${PRINCIPLES_SECTION}. `));
  if (h2 === -1) throw new Error(`home: the current Standard has no section ${PRINCIPLES_SECTION}`);
  const end = nodes.findIndex((n, i) => i > h2 && n.type === 'heading' && n.depth <= 2);
  const section = nodes.slice(h2 + 1, end === -1 ? undefined : end);
  const items: Principle[] = [];
  let introParts: string[] = [];
  let current: Principle | null = null;
  // Anchors as the page renders them (github-slugger over the whole file).
  const anchors = new Map(anchorsFor(std.source).map((e) => [e.text, e.slug] as const));
  for (const n of section as RootContent[]) {
    if (n.type === 'heading' && n.depth === 3) {
      const t = headingText(n as Heading);
      const m = /^(\d+\.\d+)\s+(.+)$/.exec(t);
      if (!m) throw new Error(`home: unexpected heading "${t}" in section 3`);
      current = { number: m[1]!, title: m[2]!, blocks: [], markdown: '', anchor: anchors.get(t) ?? '', glyph: principleKey(t) };
      items.push(current);
      continue;
    }
    if (n.type === 'thematicBreak') continue;
    const slice = body.slice(n.position!.start.offset!, n.position!.end.offset!);
    if (!current) {
      if (n.type === 'paragraph') introParts.push(slice);
      continue;
    }
    current.markdown = current.markdown ? `${current.markdown}\n\n${slice}` : slice;
    if (n.type === 'paragraph') current.blocks.push({ kind: 'p', text: phrasing(n.children) });
    else if (n.type === 'list') {
      current.blocks.push({
        kind: 'ul',
        items: n.children.map((li) => li.children.flatMap((c) => (c.type === 'paragraph' ? phrasing(c.children) : []))),
      });
    } else throw new Error(`home: section ${current.number} has a ${n.type}, which the home page does not show`);
  }
  if (items.length === 0) throw new Error('home: section 3 of the Standard has no principles');
  introParts = introParts.map((p) => p.replace(/\s*\n\s*/g, ' '));
  const sectionAnchor = anchors.get(headingText(nodes[h2] as Heading))!;
  const sectionUrl = `${std.url}#${sectionAnchor}`;
  const source: LinkSentence = { before: 'They come from ', link: { text: `section ${PRINCIPLES_SECTION} of the Standard`, url: sectionUrl }, after: '.' };
  return { intro: introParts.join(' '), items, sectionUrl, source };
}

function anchorsFor(source: string) {
  return anchorsOf(source, readRepoFile).entries;
}

// ------------------------------------------------------------ why

export const WHY =
  'Most agent frameworks let a model call tools in any order. If a retrieval step returns nothing useful, the next step still runs. If a write fails halfway, there is often no saved state to go back to. If two sources disagree, nothing says which one wins. These are design problems, so the standard handles them in the design. It fixes the order some steps must run in, requires a restore point before changes, and defines how sources are weighed when they conflict.';

// ------------------------------------------------------------ scroll story

export interface StoryStep {
  /** 1-based beat number, also the diagram elements it reveals. */
  beat: number;
  title: string;
  text: Inline;
}

export interface StoryData {
  workflow: Workflow;
  contractStep: Step;
  checkpointStep: Step;
  changeStep: Step;
  verifyStep: Step;
  rollbackStep: Step;
  /** Required output fields of the contract step's capability. */
  contractOutputs: string[];
  contractInputs: string[];
  steps: StoryStep[];
}

const t = (text: string): Inline => [{ code: false, text }];
const c = (text: string): Inline => [{ code: true, text }];
const join = (...parts: Inline[]): Inline => parts.flat();
const codeList = (xs: string[]): Inline =>
  xs.flatMap((x, i) => [...(i === 0 ? [] : t(i === xs.length - 1 ? ' and ' : ', ')), ...c(x)]);

export function story(): StoryData {
  const wf = loadWorkflows().byId.get(STORY_WORKFLOW);
  if (!wf) throw new Error(`home: the catalog has no ${STORY_WORKFLOW} workflow`);
  const ontology = loadOntology();
  const counts = loadCounts();
  const find = (what: string, pred: (s: Step) => boolean): Step => {
    const s = wf.steps.find(pred);
    if (!s) throw new Error(`home: ${STORY_WORKFLOW} has no ${what} step`);
    return s;
  };
  const contractStep = wf.steps[0]!;
  const checkpointStep = find('checkpoint', (s) => s.capability === 'checkpoint');
  const changeStep = find('state-changing', (s) => stepRole(s) === 'mutating');
  const verifyStep = find('verify', (s) => s.capability === 'verify');
  const rollbackStep = find('rollback', (s) => s.capability === 'rollback');
  if (!(checkpointStep.index < changeStep.index && changeStep.index < verifyStep.index && verifyStep.index < rollbackStep.index)) {
    throw new Error(`home: ${STORY_WORKFLOW} no longer runs checkpoint, change, verify and rollback in that order`);
  }
  const contractCap = ontology.byId.get(contractStep.capability)!;
  const contractInputs = Object.keys(contractStep.input_bindings);
  const contractOutputs = contractRows(contractCap.output_schema).filter((r) => r.depth === 0 && r.required).map((r) => r.name);
  const used = new Set(wf.steps.map((s) => s.capability));
  const changeGates = gateRows(changeStep).filter((g) => g.when.includes(`${checkpointStep.store_as}.`));
  const rollbackGate = gateRows(rollbackStep)[0];
  const rollbackReads = Object.values(rollbackStep.input_bindings).map(String).find((v) => v.includes(`${checkpointStep.store_as}.`));
  const guardedBy = ontology.edges.filter((e) => e.type === 'requires' && e.from === 'checkpoint').map((e) => e.to);
  const flags = [
    ...(changeStep.effective.checkpoint.needed ? ['a checkpoint before it'] : []),
    ...(changeStep.effective.requires_approval ? ['approval'] : []),
  ];

  const steps: StoryStep[] = [
    {
      beat: 1,
      title: 'An agent does a few kinds of thing.',
      text: t(
        `It perceives, reasons, changes things and checks its work. The standard names ${counts.capabilityCount} of these operations and sorts them into ${counts.layerCount} layers. In the diagram each tile is a capability, with its two-letter symbol, in the column under its layer's glyph. The ${used.size} that the model deployment workflow uses have a dark frame.`,
      ),
    },
    {
      beat: 2,
      title: 'Each capability has a contract.',
      text: join(
        t(`The workflow is a list of ${wf.steps.length} steps. Its first step uses `),
        c(contractStep.capability),
        t('. It is given '),
        codeList(contractInputs),
        t(' and must return '),
        codeList(contractOutputs),
        t('. Each step stores its output under a name, and the validator checks every value a later step reads against the schema of the step that produced it.'),
      ),
    },
    {
      beat: 3,
      title: 'A checkpoint comes first.',
      text: join(
        t(`Step ${checkpointStep.index}, `),
        c(checkpointStep.capability),
        t(`, saves a restore point and stores it as `),
        c(checkpointStep.store_as ?? ''),
        t('. The ontology requires a checkpoint before '),
        codeList(guardedBy),
        t('.'),
      ),
    },
    {
      beat: 4,
      title: 'Then the step that changes things.',
      text: join(
        t(`Step ${changeStep.index}, `),
        c(changeStep.capability),
        t(`: ${changeStep.purpose} It changes state, so it needs ${flags.join(' and ')}.`),
        ...(changeGates.length > 0
          ? [t(' One of its gates reads '), c(changeGates[0]!.when), t(` and stops the run: "${changeGates[0]!.message}"`)]
          : []),
      ),
    },
    {
      beat: 5,
      title: 'Verify checks the result.',
      text: join(t(`Step ${verifyStep.index}, `), c(verifyStep.capability), t(`: ${verifyStep.purpose} It stores its verdict as `), c(verifyStep.store_as ?? ''), t('.')),
    },
    {
      beat: 6,
      title: 'Rollback is the way back.',
      text: join(
        t(`Step ${rollbackStep.index}, `),
        c(rollbackStep.capability),
        ...(rollbackReads ? [t(', reads '), c(rollbackReads)] : []),
        t(`. ${rollbackStep.purpose}`),
        ...(rollbackGate ? [t(' Its gate skips it when '), c(rollbackGate.when), t(`: "${rollbackGate.message}"`)] : []),
      ),
    },
  ];
  return { workflow: wf, contractStep, checkpointStep, changeStep, verifyStep, rollbackStep, contractInputs, contractOutputs, steps };
}

// ------------------------------------------------------------ what it covers

/** One line per section of the Standard, keyed by section number. Titles come from the Standard. */
const SECTION_LINES: [string, string][] = [
  ['4', 'Capabilities, layers, and the edges that order them.'],
  ['5', 'Steps, bindings, gates and failure modes.'],
  ['5.8', 'The expression language for conditions, gates and failure-mode triggers.'],
  ['5.9', ''],
  ['6', 'World state and events, with provenance and uncertainty.'],
  ['7', 'How entities are matched, merged and split across sources.'],
  ['8', 'How sources are weighed when they conflict, with decay over time.'],
  ['9', 'Error and warning codes with fixed severities.'],
  ['10', 'Levels from structural checks up to patch suggestions.'],
  ['11', 'Semantic versioning, deprecation and compatibility rules.'],
];

export function coverage(): { standard: Card[]; data: Card[]; tools: Card[] } {
  const std = currentStandard();
  const entries = anchorsFor(std.source);
  const heading = (num: string) => {
    const e = entries.find((x) => x.text.startsWith(`${num}. `) || x.text.startsWith(`${num} `));
    if (!e) throw new Error(`home: the current Standard has no section ${num}`);
    return { title: e.text.replace(/^[\d.]+\s+/, ''), slug: e.slug };
  };
  const standard = SECTION_LINES.map(([num, line]) => {
    const h = heading(num);
    let text = line;
    if (num === '5.9') {
      // The extensions are 5.9 and the sections after it in section 5.
      const later = entries
        .map((x) => /^5\.(\d+)\s+(.+)$/.exec(x.text))
        .filter((m): m is RegExpExecArray => m !== null && Number(m[1]) > 9)
        .map((m) => m[2]!.toLowerCase());
      if (later.length === 0) throw new Error('home: section 5 has no sections after 5.9');
      text = `What a workflow declares to use: ${later.slice(0, -1).join(', ')} and ${later.at(-1)}.`;
    }
    // A chapter's card takes the chapter glyph. A subsection's card takes its
    // own topic glyph, so it does not repeat its chapter's card beside it.
    const chapter = entries.find((x) => x.text.startsWith(`${num.split('.')[0]}. `))!;
    const topic = `topic:${slugKey(h.title)}`;
    const glyph = num.includes('.') ? (resolveGlyphKey(topic) === null ? null : topic) : chapterKey(chapter.text);
    if (glyph === null) {
      throw new Error(`home: section ${num} of the Standard has no glyph (a subsection needs ${topic} in glyphs-pages.ts; an appendix has none)`);
    }
    return { title: h.title, line: text, link: { text: `§${num}`, url: `${std.url}#${h.slug}` }, section: `§${num}`, glyph };
  });
  // The section of the Standard that defines the diagnostic codes, by its heading.
  const diagnosticsSection = entries.map((x) => /^(\d+)\.\s+Diagnostic/.exec(x.text)?.[1]).find(Boolean);
  if (!diagnosticsSection) throw new Error('home: the current Standard has no top-level Diagnostic section');
  const k = loadCounts();
  const data: Card[] = [
    { title: 'Capabilities', count: k.capabilityCount, glyph: 'count:capabilities', line: 'Each with its contract, risk level, edges and skill.', link: { text: 'Capabilities', url: '/capabilities/' } },
    { title: 'Layers', count: k.layerCount, glyph: 'count:layers', line: 'The groups the capabilities are sorted into.', link: { text: 'Layers', url: `/layers/${loadOntology().layers[0]!.slug}/` } },
    { title: 'Workflows', count: k.workflowCount, glyph: 'count:workflows', line: 'Reference and domain workflows, step by step.', link: { text: 'Workflows', url: '/workflows/' } },
    { title: 'Domain profiles', count: k.profileCount, glyph: 'count:profiles', line: 'Trust weights, risk thresholds and checkpoint rules per field.', link: { text: 'Domains', url: '/domains/' } },
    { title: 'Edge types', count: k.edgeTypeCount, glyph: 'count:edges', line: 'The kinds of relation between capabilities.', link: { text: 'Edge types', url: '/spec/edge-types/' } },
    { title: 'Diagnostic codes', count: k.diagnosticCount, glyph: 'count:diagnostics', line: 'What each code means and whether it is an error.', link: { text: 'Diagnostics', url: '/spec/diagnostics/' } },
    { title: 'Skills', count: k.skillCount, glyph: 'count:skills', line: 'Skill files for agents: one per capability, and composed skills that combine several.', link: { text: 'Skills', url: '/guides/skills/' } },
  ];
  const tools: Card[] = [
    { title: 'Validator', line: `A Rust core with a Python command-line tool. It reports the diagnostic codes of section ${diagnosticsSection}.`, link: { text: 'Quickstart', url: '/start/quickstart/' } },
    { title: 'Executor', line: 'Runs a workflow and hands each action to your host code.', link: { text: 'Running workflows', url: '/guides/running-workflows/' } },
    { title: 'Claude Code plugin', line: 'One skill per capability, plus hooks that block file edits until a checkpoint exists.', link: { text: 'Safety hooks', url: '/guides/hooks/' } },
    { title: 'Python SDK adapter', line: 'Adds checkpoint enforcement and evidence tracking to the Claude Agent SDK.', link: { text: 'Claude Agent SDK', url: '/guides/claude-agent-sdk/' } },
    { title: 'Conformance suite', line: 'Fixtures that a validator or executor must pass.', link: { text: 'Conformance', url: '/spec/conformance/' } },
  ];
  for (const t of tools) {
    t.glyph = TOOL_GLYPHS[t.title];
    if (!t.glyph) throw new Error(`home: the tool card "${t.title}" has no glyph in TOOL_GLYPHS`);
  }
  return { standard, data, tools };
}

// ------------------------------------------------------------ FAQ

export interface FaqItem {
  question: string;
  answer: Inline;
}

/** The minimum deprecation period, in months, from the deprecation policy of the current Standard. */
export function deprecationMonths(): number {
  const text = readRepoFile(currentStandard().source);
  const m = /^\s*\d+\.\s+Minimum deprecation period:\s*(\d+)\s+months?\s*$/im.exec(text);
  if (!m) throw new Error('home: the current Standard states no "Minimum deprecation period: N months"');
  return Number(m[1]);
}

export function faq(): { items: FaqItem[]; more: HomeLink } {
  const v = loadVersions().standard.current;
  const months = deprecationMonths();
  // Codes named in an answer must exist; diagnosticHref throws if one does not.
  for (const code of ['V102', 'B203']) diagnosticHref(code);
  return {
    items: [
      {
        question: 'Is this a framework?',
        answer: t('No. It is a specification, and a framework can implement it. MCP connects tools to models; this standard describes what a capability does and what must happen before it runs.'),
      },
      {
        question: 'Do I need Claude Code?',
        answer: t('No. The specification and the validator do not depend on it. The Claude Code plugin is one implementation, with a skill per capability and hooks that require a checkpoint before file edits.'),
      },
      {
        question: 'What does the validator check?',
        answer: join(
          t('Structure, capability names, ordering edges, bindings and their types, safety flags and expressions. It reports codes such as '),
          c('V102'),
          t(' or '),
          c('B203'),
          t('. It does not check whether claims are grounded, or how entities are matched across sources.'),
        ),
      },
      {
        question: 'How stable is it?',
        answer: t(
          `Version ${v.version} is a ${v.status}. Breaking changes need a new major version. A feature is deprecated in a minor release with a warning, and removed no earlier than the next major release and at least ${months} ${months === 1 ? 'month' : 'months'} later.`,
        ),
      },
    ],
    more: { text: 'Read the full FAQ', url: '/start/faq/' },
  };
}

// ------------------------------------------------------------ get started

export function getStarted(): { prompt: string; cards: (Card & { extra?: HomeLink })[] } {
  const std = currentStandard();
  return {
    prompt: `Read ${SITE_ORIGIN}/llms.txt and the pages it lists. Then help me write a workflow that follows the Agent Capability Standard and passes its validator.`,
    cards: [
      { title: 'Quickstart', line: 'Validate the reference workflows on your machine.', link: { text: 'Quickstart', url: '/start/quickstart/' } },
      { title: 'Specification', line: 'The normative text, with requirement keywords marked.', link: { text: `Standard ${std.version}`, url: std.url } },
      {
        title: 'Contribute',
        line: 'Open an issue, or propose a change as an RFC.',
        link: { text: 'Issues on GitHub', url: `${GITHUB_BASE}/issues` },
        extra: { text: 'RFCs', url: '/rfcs/' },
      },
    ].map((card: Card & { extra?: HomeLink }) => ({ ...card, glyph: startGlyph(card) })),
  };
}

/**
 * A get-started card's glyph (visual spec 2.2): the glyph of the page its
 * first site link goes to, or of that page's section when the page has none.
 * A card with only outside links has none.
 */
function startGlyph(card: Card & { extra?: HomeLink }): string {
  const target = [card.link, card.extra].find((l) => l?.url.startsWith('/'));
  if (!target) throw new Error(`home: the get-started card "${card.title}" links to no site page, so it has no section glyph`);
  const url = target.url.split('#')[0]!;
  return PAGE_GLYPHS[url] ?? `section:${routeByUrl(url).section}`;
}

// ------------------------------------------------------------ figures

/** Titles of the home page's figures, shared by the page and its copy. */
export const STORY_FIG_TITLE = `From capabilities to the steps of ${STORY_WORKFLOW}`;
export const TABLE_FIG_TITLE = 'The periodic table of capabilities';
export const GALLERY_FIG_TITLE = 'Every workflow, one square per step';
export const WORKFLOWS_HEADING = 'The workflows';
export const GALLERY_INTRO = 'The catalogs ship reference workflows and workflows for each domain. Each one is a list of steps. Below, each square is one step, in order, marked with the symbol of the capability it runs or with its safety role.';

/**
 * The story's other steps with a safety role (stepRole, the rule every step
 * map and strip uses), which carry their role mark too: in model_deployment,
 * the constrain steps get the verify mark, as in the gallery's strip.
 */
export function storyExtraMarks(): { index: number; capability: string; role: Exclude<StepRole, 'plain'> }[] {
  const s = story();
  const shown = new Set([s.checkpointStep.index, s.changeStep.index, s.verifyStep.index, s.rollbackStep.index]);
  return s.workflow.steps
    .map((st) => ({ index: st.index, capability: st.capability, role: stepRole(st) }))
    .filter((x): x is { index: number; capability: string; role: Exclude<StepRole, 'plain'> } => x.role !== 'plain' && !shown.has(x.index));
}

/** Fig: the story. Its caption names the steps the marks sit on. */
export function storyCaption(): string {
  const s = story();
  const extra = storyExtraMarks();
  const ROLE_WORDS: Record<string, string> = { checkpoint: 'checkpoint', mutating: 'change', verify: 'check', rollback: 'rollback' };
  const more =
    extra.length === 0
      ? ''
      : ` ${extra.length === 1 ? 'Step' : 'Steps'} ${andList(extra.map((x) => `${x.index} (${x.capability})`))} also ${extra.length === 1 ? 'carries' : 'carry'} the ${andList([...new Set(extra.map((x) => ROLE_WORDS[x.role]!))])} mark, as on every step map.`;
  return `The ${s.workflow.id} workflow has ${s.workflow.steps.length} steps: it saves a checkpoint at step ${s.checkpointStep.index}, makes its change at step ${s.changeStep.index}, verifies at step ${s.verifyStep.index} and can roll back at step ${s.rollbackStep.index}.${more}`;
}

/** Fig: the periodic table. The smallest and largest layers, from the ontology. */
export function tableCaption(): string {
  const o = loadOntology();
  const sizes = o.layers.map((l) => ({ id: l.id, n: capabilitiesOfLayer(o, l.id).length }));
  const min = Math.min(...sizes.map((x) => x.n));
  const max = Math.max(...sizes.map((x) => x.n));
  const at = (n: number) => andList(sizes.filter((x) => x.n === n).map((x) => x.id));
  return `${o.capabilities.length} capabilities in ${o.layers.length} layers, from ${min} in ${at(min)} to ${max} in ${at(max)}.`;
}

/** A workflow in the gallery. */
export interface GalleryItem {
  workflow: Workflow;
  steps: number;
  checkpoints: number;
  gated: number;
}

/** A group of the gallery: the reference workflows, then one per domain catalog. */
export interface GalleryGroup {
  label: string;
  glyph: string;
  items: GalleryItem[];
}

/**
 * Fig: the workflow gallery (visual spec 3.11, F-H2), grouped by catalog as
 * the sidebar groups them: the core catalog first, then each domain.
 */
export function gallery(): GalleryGroup[] {
  const groups: GalleryGroup[] = [];
  for (const wf of loadWorkflows().all) {
    const label = wf.catalog === 'core' ? 'Reference workflows' : (wf.domain ?? wf.source);
    const glyph = wf.catalog === 'core' ? 'section:workflows' : `domain:${(wf.domain ?? '').replace(/-/g, '_')}`;
    let g = groups.find((x) => x.label === label);
    if (!g) groups.push((g = { label, glyph, items: [] }));
    const d = diagramSteps(wf);
    g.items.push({
      workflow: wf,
      steps: wf.steps.length,
      checkpoints: d.filter((x) => x.role === 'checkpoint').length,
      gated: wf.steps.filter((x) => (x.gates?.length ?? 0) > 0).length,
    });
  }
  return groups;
}

export function galleryCaption(): string {
  const items = gallery().flatMap((g) => g.items);
  const steps = items.map((i) => i.steps);
  const withCheckpoint = items.filter((i) => i.checkpoints > 0).length;
  const high = items.filter((i) => i.workflow.risk === 'high').length;
  return `${items.length} workflows in ${gallery().length} groups, from ${Math.min(...steps)} to ${Math.max(...steps)} steps; ${withCheckpoint} save a checkpoint and ${high} are high risk.`;
}
