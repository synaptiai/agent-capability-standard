// The Markdown pipeline, in one place so astro.config.mjs and the tests run the
// same chain. Order matters:
// - remark: links are rewritten first, so the page-meta block keeps rewritten
//   links; the HTML allowlist sees the raw HTML nodes; mermaid fences become
//   figures last, before Shiki would highlight them as code.
// - Astro runs Shiki after remark and before the rehype plugins listed here.
// - rehype: rehypeHeadingIds runs first so the autolink plugin and everything
//   after it see the ids (Astro's own later pass keeps ids already set).
//   Keywords and callouts come next, then the figure marks (chapter glyphs,
//   the edge summary table), then tables are wrapped and task lists marked.
//   The capability-skill step (numbered procedure steps, collapsed examples)
//   runs last, on the finished tree of each capability skill.
// SmartyPants is off so heading ids match GitHub's (it would turn "--" into an
// en dash before the ids are made).
import { rehypeHeadingIds, type ShikiConfig, type UnifiedProcessorOptions } from '@astrojs/markdown-remark';
import rehypeAutolinkHeadings from 'rehype-autolink-headings';
import rehypeCallouts from '../plugins/rehype-callouts';
import rehypeCapabilitySkill from '../plugins/rehype-capability-skill';
import rehypeFigureMarks from '../plugins/rehype-figure-marks';
import rehypeKeywords from '../plugins/rehype-keywords';
import rehypeSpecSlots from '../plugins/rehype-spec-slots';
import rehypeTables from '../plugins/rehype-tables';
import rehypeTaskLists from '../plugins/rehype-task-lists';
import remarkHtmlAllowlist from '../plugins/remark-html-allowlist';
import remarkMermaid from '../plugins/remark-mermaid';
import remarkPageMeta from '../plugins/remark-page-meta';
import remarkRepoLinks from '../plugins/remark-repo-links';
import { loadVersions } from '../data/versions';
import { ROUTES, routeForSource } from './routes';

/**
 * Pages whose requirement keywords are marked: both versions of the Standard,
 * the RFCs, and the normative companions named in the site design.
 */
export const KEYWORD_SOURCES: ReadonlySet<string> = new Set([
  ...ROUTES.filter((r) => r.source !== null && (r.template === 'spec' || /^spec\/RFC-\d{4}-/.test(r.source))).map(
    (r) => r.source!,
  ),
  'spec/CONFORMANCE.md',
  'spec/EDGE_TYPES.md',
  'spec/SECURITY.md',
]);

/** Keyword sources that have no route; a renamed file would otherwise lose its marking silently. */
export function unroutedKeywordSources(
  sources: Iterable<string>,
  routeFor: (source: string) => unknown = routeForSource,
): string[] {
  return [...sources].filter((s) => routeFor(s) === undefined);
}

const unrouted = unroutedKeywordSources(KEYWORD_SOURCES);
if (unrouted.length > 0) {
  throw new Error(`markdown: KEYWORD_SOURCES names files with no route: ${unrouted.join(', ')}`);
}

/**
 * Code highlighting. The css-variables theme writes `var(--astro-code-*)`
 * colours, which the design system sets per theme. Shiki has no EBNF grammar,
 * so the spec's one ebnf block is shown as plain text.
 */
export const SHIKI_CONFIG: ShikiConfig = {
  theme: 'css-variables',
  langAlias: { ebnf: 'text' },
};

export const PROCESSOR_OPTIONS: UnifiedProcessorOptions = {
  smartypants: false,
  remarkPlugins: [remarkRepoLinks, remarkPageMeta, remarkHtmlAllowlist, remarkMermaid],
  rehypePlugins: [
    rehypeHeadingIds,
    [
      rehypeAutolinkHeadings,
      { behavior: 'append', properties: { className: ['heading-anchor'], ariaHidden: 'true', tabIndex: -1 } },
    ],
    [rehypeKeywords, { sources: KEYWORD_SOURCES }],
    rehypeCallouts,
    [
      rehypeFigureMarks,
      {
        standards: new Set(ROUTES.filter((r) => r.template === 'spec' && r.source !== null).map((r) => r.source!)),
        current: loadVersions().standard.current.source,
        edgeTypes: 'spec/EDGE_TYPES.md',
      },
    ],
    [rehypeSpecSlots, { current: loadVersions().standard.current.source }],
    rehypeTables,
    rehypeTaskLists,
    rehypeCapabilitySkill,
  ],
};
