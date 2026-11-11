// The only route table. The sidebar, links, Markdown copies and llms.txt all
// read it. When this module loads it checks that:
// - every tracked public .md file has exactly one row;
// - every Markdown source is tracked and not excluded;
// - no URL is used twice and every URL has the /a/b/ form;
// - no workflow takes a slug the workflow section reserves;
// - every directory in the directory map exists and points at a page.
// A new public .md file therefore needs a row here, or the build fails.
import { loadOntology } from '../data/ontology';
import { loadProfiles } from '../data/profiles';
import { COMPOSED_SKILLS } from '../data/skills';
import { standardVersions, type StandardVersion } from '../data/versions';
import { loadWorkflows, RESERVED_WORKFLOW_SLUGS } from '../data/workflows';
import { TRACKED_FILES } from './repo';

export const SECTIONS = [
  { id: 'home', label: 'Home' },
  { id: 'start', label: 'Get started' },
  { id: 'spec', label: 'Specification' },
  { id: 'capabilities', label: 'Capabilities' },
  { id: 'workflows', label: 'Workflows' },
  { id: 'domains', label: 'Domains' },
  { id: 'guides', label: 'Guides' },
  { id: 'compliance', label: 'Compliance' },
  { id: 'rfcs', label: 'RFCs' },
  { id: 'background', label: 'Background' },
  { id: 'community', label: 'Community' },
] as const;
export type Section = (typeof SECTIONS)[number]['id'];

export type Template =
  | 'home'
  | 'listing'
  | 'prose'
  | 'spec'
  | 'rfc'
  | 'raw'
  | 'skill'
  | 'capabilities-index'
  | 'capability'
  | 'layer'
  | 'workflows-index'
  | 'workflow'
  | 'domains-index'
  | 'domain'
  | 'edge-types'
  | 'diagnostics'
  | 'schemas'
  | 'rfcs-index'
  | 'citation';

export interface Route {
  /** Repo path of the Markdown source, or null for a page generated from data only. */
  source: string | null;
  url: string;
  section: Section;
  /** Sidebar sub-group, e.g. a layer id or "EU AI Act". */
  group?: string;
  /** Position within the section, from 0, in sidebar order. */
  order: number;
  template: Template;
  /** Sidebar label. */
  title: string;
  /** The Markdown renders inside a generated page rather than on its own. */
  embed?: boolean;
  /** Repo path of the data file a generated page is built from. */
  data?: string;
}

/**
 * Paths that never get a page. From the plan's exclusion list, plus `.github/`
 * (the pull request template is repository plumbing, not documentation).
 */
export const EXCLUSIONS: readonly { pattern: RegExp; reason: string }[] = [
  { pattern: /^_archive\//, reason: 'archived v1 material' },
  { pattern: /^analysis\//, reason: 'internal analysis (top-level folder only)' },
  { pattern: /^tasks\//, reason: 'task tracking' },
  { pattern: /^docs\/reviews\//, reason: 'internal reviews' },
  { pattern: /^docs\/research\/raw_data\//, reason: 'raw research data' },
  { pattern: /^docs\/schemas(\/|$)/, reason: 'symlink to schemas/' },
  { pattern: /^skills\/[^/]+\/reference\//, reason: 'synced copies' },
  { pattern: /^CLAUDE\.md$/, reason: 'agent instructions' },
  { pattern: /^\.github\//, reason: 'repository plumbing' },
  { pattern: /^docs\/(MEDIUM_ARTICLE[^/]*|PROJECT_ARTICLE|TWITTER_THREAD)\.md$/, reason: 'drafts' },
  { pattern: /^docs\/proposals\/GROUNDED_HARNESS_V3\.md$/, reason: 'empty draft' },
];

export function isExcluded(repoPath: string): boolean {
  return EXCLUSIONS.some((e) => e.pattern.test(repoPath));
}

/** Tracked .md files that must have a route. */
export function publicMarkdown(tracked: Iterable<string>): string[] {
  return [...tracked].filter((p) => p.endsWith('.md') && !isExcluded(p)).sort();
}

/** File name to URL segment: `ORCHESTRATION_EXTENSIONS.md` -> `orchestration-extensions`. */
export function kebab(name: string): string {
  return name
    .replace(/\.md$/i, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

const URL_FORM = /^\/(?:[a-z0-9][a-z0-9.-]*\/)*$/;

/**
 * Check a route table against the tracked files. Returns every problem found,
 * one line each. Pure, so tests can feed it a broken table.
 */
export function checkRoutes(
  rows: readonly Route[],
  tracked: ReadonlySet<string>,
  directories: Readonly<Record<string, string>> = {},
): string[] {
  const problems: string[] = [];
  const urls = new Map<string, Route>();
  const sources = new Map<string, Route>();
  for (const r of rows) {
    if (!URL_FORM.test(r.url)) problems.push(`${r.url}: URL must look like /a/b/`);
    const clash = urls.get(r.url);
    if (clash) problems.push(`${r.url}: used by ${clash.source ?? clash.title} and ${r.source ?? r.title}`);
    urls.set(r.url, r);
    if (r.template === 'workflow') {
      const last = r.url.split('/').at(-2) ?? '';
      if (RESERVED_WORKFLOW_SLUGS.includes(last)) problems.push(`${r.url}: workflow slug ${last} is reserved`);
    }
    if (r.source === null) continue;
    if (!tracked.has(r.source)) problems.push(`${r.source}: routed but not tracked by git`);
    if (isExcluded(r.source)) problems.push(`${r.source}: routed but excluded`);
    const dup = sources.get(r.source);
    if (dup) problems.push(`${r.source}: routed twice (${dup.url} and ${r.url})`);
    sources.set(r.source, r);
  }
  for (const p of publicMarkdown(tracked)) {
    if (!sources.has(p)) problems.push(`${p}: public Markdown with no route`);
  }
  const trackedList = [...tracked];
  for (const [dir, url] of Object.entries(directories)) {
    if (!trackedList.some((p) => p.startsWith(`${dir}/`))) problems.push(`${dir}/: mapped but no tracked file is in it`);
    if (!urls.has(url)) problems.push(`${dir}/: maps to ${url}, which is not a route`);
  }
  return problems;
}

/**
 * Repository directories that links may point at, and the page each one
 * stands for. A link to any other directory goes to its GitHub tree page.
 */
export function buildDirectoryMap(): Record<string, string> {
  const map: Record<string, string> = {
    spec: `/spec/${standardVersions()[0]?.version ?? 'missing'}/`,
    'docs/compliance': '/compliance/',
    'docs/compliance/eu-ai-act': '/compliance/eu-ai-act/',
    'docs/compliance/iso42001': '/compliance/iso-42001/',
    'docs/compliance/nist-ai-rmf': '/compliance/nist-ai-rmf/',
    'docs/domains': '/domains/',
  };
  for (const d of loadProfiles()) map[`docs/domains/${d.key}`] = `/domains/${d.key}/`;
  for (const c of loadOntology().capabilities) map[`skills/${c.id}`] = `/capabilities/${kebab(c.id)}/`;
  for (const dir of Object.keys(COMPOSED_SKILLS)) map[`skills/${dir}`] = `/guides/skills/${dir}/`;
  return map;
}

type RowInput = Omit<Route, 'order' | 'section'>;

/** Build the full table from the content and the data. */
export function buildRoutes(): Route[] {
  const rows: Route[] = [];
  const counters = new Map<Section, number>();
  const add = (section: Section, ...items: RowInput[]): void => {
    for (const item of items) {
      const order = counters.get(section) ?? 0;
      counters.set(section, order + 1);
      rows.push({ ...item, section, order });
    }
  };
  const prose = (source: string, url: string, title: string, group?: string): RowInput =>
    group === undefined ? { source, url, title, template: 'prose' } : { source, url, title, template: 'prose', group };

  add('home', { source: null, url: '/', title: 'Home', template: 'home' });

  add(
    'start',
    { source: null, url: '/start/', title: 'Get started', template: 'listing' },
    prose('README.md', '/start/overview/', 'Overview'),
    prose('docs/QUICKSTART.md', '/start/quickstart/', 'Quickstart'),
    prose('docs/TUTORIAL.md', '/start/tutorial/', 'Tutorial'),
    prose('docs/FAQ.md', '/start/faq/', 'FAQ'),
    prose('docs/GLOSSARY.md', '/start/glossary/', 'Glossary'),
  );

  const ontology = loadOntology();
  const [currentStd, ...previousStd] = standardVersions();
  if (!currentStd) throw new Error('routes: no spec/STANDARD-v*.md file is tracked');
  const specRow = (v: StandardVersion, group?: string): RowInput => {
    const row: RowInput = { source: v.source, url: `/spec/${v.version}/`, title: `Standard v${v.version}`, template: 'spec' };
    if (group !== undefined) row.group = group;
    return row;
  };
  add(
    'spec',
    specRow(currentStd),
    prose('spec/CONFORMANCE.md', '/spec/conformance/', 'Conformance'),
    prose('tests/conformance/contrib/README.md', '/spec/conformance/contributed-fixtures/', 'Contributed fixtures'),
    {
      source: 'spec/EDGE_TYPES.md',
      url: '/spec/edge-types/',
      title: 'Edge types',
      template: 'edge-types',
      embed: true,
      data: 'schemas/capability_ontology.yaml',
    },
    { source: null, url: '/spec/diagnostics/', title: 'Diagnostics', template: 'diagnostics', data: 'core/src/diag.rs' },
    prose('spec/SECURITY.md', '/spec/security/', 'Security model'),
    { source: null, url: '/spec/schemas/', title: 'Schemas', template: 'schemas' },
    prose('docs/methodology/EXTENSION_GOVERNANCE.md', '/spec/extending/', 'Adding a capability'),
    prose('spec/CHANGELOG.md', '/spec/changelog/', 'Spec changelog'),
    ...previousStd.map((v) => specRow(v, 'Previous versions')),
  );

  add('capabilities', {
    source: null,
    url: '/capabilities/',
    title: 'Overview',
    template: 'capabilities-index',
    data: 'schemas/capability_ontology.yaml',
  });
  for (const layer of ontology.layers) {
    add('capabilities', {
      source: null,
      url: `/layers/${layer.slug}/`,
      title: layer.id,
      template: 'layer',
      group: layer.id,
      data: 'schemas/capability_ontology.yaml',
    });
    for (const id of layer.capabilities) {
      add('capabilities', {
        source: `skills/${id}/SKILL.md`,
        url: `/capabilities/${kebab(id)}/`,
        title: id,
        template: 'capability',
        group: layer.id,
        embed: true,
        data: 'schemas/capability_ontology.yaml',
      });
    }
  }

  const workflows = loadWorkflows();
  add(
    'workflows',
    { source: null, url: '/workflows/', title: 'Overview', template: 'workflows-index' },
    prose('docs/WORKFLOW_PATTERNS.md', '/workflows/patterns/', 'Composition patterns'),
    prose('docs/WORKFLOW_ROADMAP.md', '/workflows/roadmap/', 'Workflow roadmap'),
  );
  for (const wf of workflows.all) {
    add('workflows', {
      source: null,
      url: `/workflows/${wf.slug}/`,
      title: wf.slug,
      template: 'workflow',
      group: wf.catalog === 'core' ? 'Reference workflows' : (wf.domain ?? wf.source),
      data: wf.source,
    });
  }

  add('domains', {
    source: 'docs/domains/README.md',
    url: '/domains/',
    title: 'Overview',
    template: 'domains-index',
  });
  for (const d of loadProfiles()) {
    const row: RowInput = {
      source: d.readme,
      url: `/domains/${d.key}/`,
      title: d.key,
      template: 'domain',
      data: d.profileFile,
    };
    if (d.readme !== null) row.embed = true;
    add('domains', row);
  }

  add(
    'guides',
    { source: null, url: '/guides/', title: 'Overview', template: 'listing' },
    prose('docs/guides/RUNNING_WORKFLOWS.md', '/guides/running-workflows/', 'Running workflows'),
    prose('docs/guides/ORCHESTRATION_EXTENSIONS.md', '/guides/orchestration-extensions/', 'Orchestration extensions'),
    prose('docs/guides/MODALITY_HANDLING.md', '/guides/modality-handling/', 'Modality handling'),
    prose('docs/integrations/claude_agent_sdk.md', '/guides/claude-agent-sdk/', 'Claude Agent SDK'),
    prose('docs/integrations/oasf_coverage.md', '/guides/oasf-coverage/', 'OASF coverage'),
    prose('hooks/README.md', '/guides/hooks/', 'Safety hooks'),
    prose('examples/README.md', '/guides/examples/', 'Examples'),
    prose('skills/README.md', '/guides/skills/', 'Skills overview', 'Skills'),
  );
  for (const dir of Object.keys(COMPOSED_SKILLS).sort()) {
    add('guides', {
      source: `skills/${dir}/SKILL.md`,
      url: `/guides/skills/${dir}/`,
      title: dir,
      template: 'skill',
      group: 'Skills',
    });
  }
  add(
    'guides',
    prose(
      'skills/perspective-validation/CHECKLIST.md',
      '/guides/skills/perspective-validation/checklist/',
      'Perspective validation checklist',
      'Skills',
    ),
    prose('templates/README.md', '/guides/skill-authoring/', 'Overview', 'Skill authoring'),
    {
      source: 'templates/SKILL_TEMPLATE_ENHANCED.md',
      url: '/guides/skill-authoring/skill-template-enhanced/',
      title: 'Skill template',
      template: 'raw',
      group: 'Skill authoring',
    },
    prose('templates/output_contracts.md', '/guides/skill-authoring/output-contracts/', 'Output contracts', 'Skill authoring'),
    prose(
      'templates/composition_patterns.md',
      '/guides/skill-authoring/composition-patterns/',
      'Composition patterns',
      'Skill authoring',
    ),
    prose(
      'templates/verification_patterns.md',
      '/guides/skill-authoring/verification-patterns/',
      'Verification patterns',
      'Skill authoring',
    ),
  );

  const eu = 'docs/compliance/eu-ai-act';
  const iso = 'docs/compliance/iso42001';
  add(
    'compliance',
    { source: null, url: '/compliance/', title: 'Overview', template: 'listing' },
    prose(`${eu}/README.md`, '/compliance/eu-ai-act/', 'Overview', 'EU AI Act'),
    // Sidebar order from the site design (information architecture, section 3).
    ...[
      ['risk_classification.md', 'Risk classification'],
      ['annex_iv_technical_documentation.md', 'Annex IV technical documentation'],
      ['quality_management_system.md', 'Quality management system'],
      ['post_market_monitoring.md', 'Post-market monitoring'],
      ['notified_body_assessment.md', 'Notified body assessment'],
    ].map(([f, t]) => prose(`${eu}/${f}`, `/compliance/eu-ai-act/${kebab(f!)}/`, t!, 'EU AI Act')),
    prose(`${iso}/README.md`, '/compliance/iso-42001/', 'Overview', 'ISO/IEC 42001'),
    // Ordered by the standard's clauses, as in the ISO 42001 README.
    ...[
      ['stakeholder_analysis.md', 'Stakeholder analysis'],
      ['ai_policy_template.md', 'AI policy template'],
      ['risk_treatment_plan.md', 'Risk treatment plan'],
      ['competency_framework.md', 'Competency framework'],
      ['internal_audit_checklist.md', 'Internal audit checklist'],
      ['management_review.md', 'Management review'],
      ['nonconformity_procedure.md', 'Nonconformity procedure'],
    ].map(([f, t]) => prose(`${iso}/${f}`, `/compliance/iso-42001/${kebab(f!)}/`, t!, 'ISO/IEC 42001')),
    prose('docs/compliance/nist-ai-rmf/nist_ai_rmf_profile.md', '/compliance/nist-ai-rmf/', 'NIST AI RMF profile'),
  );

  add('rfcs', { source: null, url: '/rfcs/', title: 'Overview and process', template: 'rfcs-index' });
  for (const source of [...TRACKED_FILES].filter((p) => /^spec\/RFC-\d{4}-[^/]+\.md$/.test(p)).sort()) {
    const num = /RFC-(\d{4})/.exec(source)![1]!;
    add('rfcs', { source, url: `/rfcs/${num}/`, title: `RFC-${num}`, template: 'rfc' });
  }
  add('rfcs', {
    source: 'docs/proposals/OASF_SAFETY_EXTENSIONS.md',
    url: '/rfcs/proposals/oasf-safety-extensions/',
    title: 'OASF safety extensions',
    template: 'rfc',
    group: 'Proposals',
  });

  const meth = 'docs/methodology';
  const res = 'docs/research';
  add(
    'background',
    { source: null, url: '/background/', title: 'Overview', template: 'listing' },
    prose('spec/WHITEPAPER.md', '/background/whitepaper/', 'Whitepaper'),
    prose('docs/GROUNDED_AGENCY.md', '/background/grounded-agency/', 'Grounded Agency paper'),
    ...[
      ['FIRST_PRINCIPLES_REASSESSMENT.md', 'First-principles derivation'],
      ['REJECTED_CANDIDATES.md', 'Rejected candidates'],
      ['WORKFLOW_COVERAGE.md', 'Workflow coverage'],
      ['AGENT_ARCHITECTURE_RESEARCH.md', 'Agent architecture research'],
      ['SKILLS_ALIGNMENT_EVALUATION.md', 'Skills alignment evaluation'],
    ].map(([f, t]) => prose(`${meth}/${f}`, `/background/methodology/${kebab(f!)}/`, t!, 'Methodology')),
    ...[
      [`${res}/failure_taxonomy.md`, 'Failure taxonomy'],
      [`${res}/replanning_capabilities.md`, 'Replanning capabilities'],
      [`${res}/analysis/OASF_comparison.md`, 'OASF comparison'],
      [`${res}/analysis/capability_mapping.md`, 'Capability mapping'],
    ].map(([f, t]) => prose(f!, `/background/research/${kebab(f!.split('/').at(-1)!)}/`, t!, 'Research')),
    prose('benchmarks/README.md', '/background/research/benchmarks/', 'Benchmarks', 'Research'),
    prose(
      `${res}/analysis/validator-engine-disagreements-1.0.md`,
      '/background/research/validator-engine-disagreements-1-0/',
      'Validator and engine disagreements in 1.0',
      'Research',
    ),
  );

  add(
    'community',
    prose('CONTRIBUTING.md', '/community/contributing/', 'Contributing'),
    prose('spec/GOVERNANCE.md', '/community/governance/', 'Governance'),
    prose('CODE_OF_CONDUCT.md', '/community/code-of-conduct/', 'Code of conduct'),
    prose('spec/ROADMAP.md', '/community/roadmap/', 'Roadmap'),
    prose('CHANGELOG.md', '/community/release-notes/', 'Release notes'),
    { source: null, url: '/community/citation/', title: 'Cite this standard', template: 'citation', data: 'CITATION.cff' },
    prose('spec/PRESS_KIT.md', '/community/press-kit/', 'Press kit'),
  );

  return rows;
}

export function assertRoutes(
  rows: readonly Route[],
  tracked: ReadonlySet<string>,
  directories: Readonly<Record<string, string>>,
): void {
  const problems = checkRoutes(rows, tracked, directories);
  if (problems.length > 0) {
    throw new Error(`routes: ${problems.length} problem(s):\n  ${problems.join('\n  ')}`);
  }
}

export const ROUTES: readonly Route[] = buildRoutes();
export const DIRECTORY_MAP: Readonly<Record<string, string>> = buildDirectoryMap();
assertRoutes(ROUTES, TRACKED_FILES, DIRECTORY_MAP);

/** Repo paths of every Markdown source, for the content collection's pattern list. */
export function markdownSources(): string[] {
  return ROUTES.flatMap((r) => (r.source === null ? [] : [r.source]));
}

const BY_SOURCE: ReadonlyMap<string, Route> = new Map(
  ROUTES.flatMap((r) => (r.source === null ? [] : [[r.source, r] as const])),
);

export function routeForSource(source: string): Route | undefined {
  return BY_SOURCE.get(source);
}

/** Templates that render one Markdown source as its own page. */
export const MARKDOWN_TEMPLATES: ReadonlySet<Template> = new Set(['prose', 'spec', 'rfc', 'skill', 'raw']);

/**
 * Templates of generated pages that show a Markdown source inside them: the
 * embedded rows, plus the domains overview, which wraps its README in a
 * generated listing.
 */
export const WRAPPING_TEMPLATES: ReadonlySet<Template> = new Set(['capability', 'edge-types', 'domain', 'domains-index']);

/** Rows that `[...slug].astro` renders. Every Markdown row is either one of these or wrapped by a generated page. */
export function markdownPages(rows: readonly Route[] = ROUTES): Route[] {
  const pages: Route[] = [];
  for (const r of rows) {
    if (r.source === null) continue;
    if (MARKDOWN_TEMPLATES.has(r.template) && !r.embed) pages.push(r);
    else if (!WRAPPING_TEMPLATES.has(r.template)) {
      throw new Error(`routes: ${r.source} uses template ${r.template}, which neither renders nor wraps Markdown`);
    }
  }
  return pages;
}
