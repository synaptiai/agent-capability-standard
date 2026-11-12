// The figure gap (visual spec 3.12, 4.2 and 6.3): the longest vertical run of
// a page between two information figures, and the runs a page may leave
// without a figure. No imports, so scripts/check-runs.mjs can load it with
// plain `node`.
//
// A run is measured in CSS pixels at a 1440px wide, 900px high viewport,
// from the top of the page body to the first figure, between figures, and
// from the last figure to the bottom of the body (header, sidebar and footer
// excluded). The height of the exempt sections a run crosses is subtracted
// before it is compared with the limit of two viewport heights.

/** The viewport the gap is measured at, and the limit in viewport heights. */
export const RUN_VIEWPORT = { width: 1440, height: 900 } as const;
export const RUN_LIMIT_VH = 2;
/** The spec's target, reported for every page but never enforced. */
export const RUN_TARGET_VH = 1;

/**
 * What counts as an information figure (visual spec 4.2): a `figure.fig`, or
 * any element marked `data-info-figure` (an enriched table, an ASCII or tree
 * panel), whose drawing is at least this big. The drawing is the figure's
 * `.fig__drawing` when it has one, otherwise the element itself.
 */
export const INFO_FIGURE_SELECTOR = 'figure.fig, [data-info-figure]';
export const MIN_DRAWING = { width: 96, height: 64 } as const;

/**
 * Why a run may be long (visual spec 3.12): (a) narrative with nothing a
 * figure can be drawn from; (b) commands and code; (c) references.
 */
export type RunCategory = 'a' | 'b' | 'c';

export interface ExemptRun {
  /**
   * A page URL ('/spec/1.1.0/'), a URL pattern in which `*` stands for one
   * path segment (the RFC pages are '/rfcs/' + '*' + '/'), or a whole template ('template:domain').
   */
  page: string;
  /**
   * The id of the heading that opens the exempt section, which runs to the
   * next heading of the same or a higher level; '*' is the whole body.
   */
  anchor: string;
  category: RunCategory;
  /**
   * 'section' (the default) exempts the whole section. 'first-tall-fence'
   * exempts only the first code block in the section that is taller than one
   * viewport, and nothing when there is none.
   */
  extent?: 'section' | 'first-tall-fence';
  /** The spec's words for the run. */
  run: string;
}

/** The exempt runs of visual spec 3.12, by page and heading anchor. */
export const EXEMPT_RUNS: readonly ExemptRun[] = [
  { page: '/spec/1.1.0/', anchor: '13-references', category: 'c', run: '§13 References' },
  { page: '/spec/1.1.0/', anchor: 'appendix-a-layer-reference', category: 'c', run: 'Appendix A' },
  { page: '/spec/1.1.0/', anchor: 'appendix-b-reserved-identifiers', category: 'c', run: 'Appendix B' },
  { page: '/spec/1.1.0/', anchor: 'appendix-c-changes-from-100', category: 'c', run: 'Appendix C' },
  { page: '/start/overview/', anchor: 'why-this-matters', category: 'a', run: 'Why This Matters' },
  { page: '/start/overview/', anchor: 'quick-start', category: 'b', run: 'Quick Start' },
  { page: '/start/overview/', anchor: 'claude-agent-sdk-integration', category: 'b', run: 'Claude Agent SDK Integration' },
  { page: '/start/overview/', anchor: 'installation', category: 'b', run: 'Installation' },
  { page: '/start/overview/', anchor: 'validation', category: 'b', run: 'Validation' },
  { page: '/start/overview/', anchor: 'license', category: 'c', run: 'License' },
  { page: '/start/overview/', anchor: 'citation', category: 'c', run: 'Citation' },
  { page: '/start/overview/', anchor: 'contributing', category: 'c', run: 'Contributing' },
  { page: '/guides/claude-agent-sdk/', anchor: 'quick-start', category: 'b', run: 'Quick Start' },
  { page: '/guides/claude-agent-sdk/', anchor: 'using-groundedclient', category: 'b', run: 'Using GroundedClient' },
  { page: '/guides/claude-agent-sdk/', anchor: 'using-wrap_options-low-level', category: 'b', run: 'Using wrap_options()' },
  { page: '/guides/claude-agent-sdk/', anchor: 'configuration-options', category: 'b', run: 'Configuration Options' },
  { page: '/guides/claude-agent-sdk/', anchor: 'using-with-capability-skills', category: 'b', run: 'Using with Capability Skills' },
  // Added at integration, read from the guide's source: each of these
  // sections is code fences with a one-line lead-in (category b).
  { page: '/guides/claude-agent-sdk/', anchor: 'structured-output', category: 'b', run: 'Structured Output (one config fence)' },
  { page: '/guides/claude-agent-sdk/', anchor: 'budget-enforcement', category: 'b', run: 'Budget Enforcement (one config fence)' },
  { page: '/guides/claude-agent-sdk/', anchor: 'evidence-anchors', category: 'b', run: 'Evidence Anchors and Evidence Format (two fences)' },
  { page: '/guides/claude-agent-sdk/', anchor: 'validation', category: 'b', run: 'Validation (one shell fence)' },
  { page: '/guides/claude-agent-sdk/', anchor: 'troubleshooting', category: 'b', run: 'Troubleshooting (three errors, each a fix as a fence)' },
  { page: '/guides/claude-agent-sdk/', anchor: 'api-reference', category: 'b', run: 'API Reference (class and function signatures as fences)' },
  // Added at integration: the overview's Documentation section is five
  // tables of document links, each with a one-line purpose; nothing in it
  // has an order, a count or an id to draw (category a).
  { page: '/start/overview/', anchor: 'documentation', category: 'a', run: 'Documentation (tables of document links)' },
  // Added at integration: rollback's Intent is one paragraph and two plain
  // lists (success criteria, compatible schemas), the same narrative every
  // capability page has (category a). It is listed for rollback only, the one
  // capability page whose run through it is over the limit: rollback's skill
  // has two inputs (too few for the Inputs table to count as a figure) and its
  // procedure names a field in one step only (too few for F-C7).
  { page: '/capabilities/rollback/', anchor: 'intent', category: 'a', run: 'Intent (paragraph and plain lists)' },
  {
    page: 'template:capability',
    anchor: 'examples',
    category: 'b',
    extent: 'first-tall-fence',
    run: 'the open first example, when its fence alone is taller than one viewport',
  },
  // Added at integration: the "Live Context" section of the audit, search and
  // verify skills is a list of shell commands the skill runs at load time
  // (category b); it has nothing else to draw.
  { page: 'template:capability', anchor: 'live-context', category: 'b', run: 'Live Context (shell commands the skill runs)' },
  { page: 'template:domain', anchor: 'customization-guide', category: 'b', run: 'Customization Guide' },
  { page: 'template:domain', anchor: 'integration-examples', category: 'b', run: 'Integration Examples' },
  // The numbered RFCs only: the OASF proposal under /rfcs/proposals/ is a
  // report-only page whose gap the spec wants reported, not exempted.
  { page: '/rfcs/*/', anchor: '*', category: 'a', run: 'the RFC body' },
  { page: '/community/citation/', anchor: '*', category: 'a', run: 'the citation page' },
  { page: '/compliance/eu-ai-act/', anchor: 'reading-order', category: 'a', run: 'Reading Order' },
  { page: '/compliance/eu-ai-act/', anchor: 'document-register', category: 'a', run: 'Document Register' },
];

/**
 * The pages where a run over the limit fails the check (visual spec 4.2):
 * every generated template, the current Standard, the overview,
 * WORKFLOW_PATTERNS and the SDK guide. Every other page is reported only.
 */
export const ENFORCED_TEMPLATES: readonly string[] = [
  'home',
  'capability',
  'layer',
  'workflow',
  'domain',
  'capabilities-index',
  'workflows-index',
  'domains-index',
  'rfcs-index',
  'listing',
  'edge-types',
  'diagnostics',
];
export const ENFORCED_URLS: readonly string[] = ['/spec/1.1.0/', '/start/overview/', '/workflows/patterns/', '/guides/claude-agent-sdk/'];

/** Whether a page is in the enforced scope. */
export function isEnforced(url: string, template: string): boolean {
  return ENFORCED_URLS.includes(url) || ENFORCED_TEMPLATES.includes(template);
}

/** Whether an entry's `page` names this page, by URL, URL pattern or template. */
export function pageMatches(page: string, url: string, template: string): boolean {
  if (page.startsWith('template:')) return page === `template:${template}`;
  if (!page.includes('*')) return page === url;
  const escape = (part: string) => part.replace(/[.+?^$()|[\]\\{}]/g, '\\$&');
  const re = new RegExp('^' + page.split('*').map(escape).join('[^/]+') + '$');
  return re.test(url);
}

/** The exempt runs that apply to a page, by its URL and its template. */
export function exemptRunsFor(url: string, template: string, runs: readonly ExemptRun[] = EXEMPT_RUNS): ExemptRun[] {
  return runs.filter((r) => pageMatches(r.page, url, template));
}

/** The label a run report gives an exempt section: its anchor and category. */
export function exemptLabel(e: ExemptRun): string {
  return `${e.anchor === '*' ? 'whole body' : `#${e.anchor}`} (${e.category})`;
}

export interface Span {
  top: number;
  bottom: number;
}

/** The geometry of one page, in page coordinates (CSS pixels from the top of the document). */
export interface PageGeometry {
  /** The page body: the main column without breadcrumb, actions and prev/next links. */
  body: Span;
  /** Every information figure whose drawing meets MIN_DRAWING. */
  figures: Span[];
  /** Every exempt section found on the page, by the label of its entry. */
  exempt: (Span & { label: string; key?: string })[];
}

export interface Run extends Span {
  /** Height of the run. */
  height: number;
  /** Height of the exempt sections inside the run. */
  exempt: number;
  /** The run less its exempt sections: the value compared with the limit. */
  net: number;
  /** Labels of the exempt sections the run crosses. */
  labels: string[];
}

/** Length of the union of spans, clipped to `within`. */
function covered(spans: readonly Span[], within: Span): number {
  const clipped = spans
    .map((s) => ({ top: Math.max(s.top, within.top), bottom: Math.min(s.bottom, within.bottom) }))
    .filter((s) => s.bottom > s.top)
    .sort((a, b) => a.top - b.top);
  let total = 0;
  let end = -Infinity;
  for (const s of clipped) {
    if (s.top >= end) {
      total += s.bottom - s.top;
      end = s.bottom;
    } else if (s.bottom > end) {
      total += s.bottom - end;
      end = s.bottom;
    }
  }
  return total;
}

/**
 * Every run of a page without a figure, top to bottom: from the body's top to
 * the first figure, between figures (overlapping or nested figures merge), and
 * from the last figure to the body's bottom. Figures outside the body are
 * clipped to it. Runs of zero height are left out.
 */
export function measureRuns(page: PageGeometry): Run[] {
  const { body } = page;
  const figs = page.figures
    .map((f) => ({ top: Math.max(f.top, body.top), bottom: Math.min(f.bottom, body.bottom) }))
    .filter((f) => f.bottom > f.top)
    .sort((a, b) => a.top - b.top || a.bottom - b.bottom);
  const gaps: Span[] = [];
  let cursor = body.top;
  for (const f of figs) {
    if (f.top > cursor) gaps.push({ top: cursor, bottom: f.top });
    cursor = Math.max(cursor, f.bottom);
  }
  if (body.bottom > cursor) gaps.push({ top: cursor, bottom: body.bottom });
  return gaps.map((g) => {
    const height = g.bottom - g.top;
    const exempt = covered(page.exempt, g);
    const labels = page.exempt.filter((e) => Math.min(e.bottom, g.bottom) > Math.max(e.top, g.top)).map((e) => e.label);
    return { ...g, height, exempt, net: height - exempt, labels };
  });
}

/** The run with the largest net height, or null for a page with no run. */
export function longestRun(runs: readonly Run[]): Run | null {
  return runs.reduce<Run | null>((best, r) => (best === null || r.net > best.net ? r : best), null);
}
