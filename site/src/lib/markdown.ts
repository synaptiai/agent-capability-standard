// The Markdown pipeline, in one place so astro.config.mjs and the tests run the
// same chain. Order matters:
// - remark: links are rewritten first, so the page-meta block keeps rewritten
//   links; the HTML allowlist sees the raw HTML nodes.
// - Astro runs Shiki after remark and before the rehype plugins listed here.
// - rehype: rehypeHeadingIds runs first so the autolink plugin and everything
//   after it see the ids (Astro's own later pass keeps ids already set).
//   Keywords and callouts come last.
// SmartyPants is off so heading ids match GitHub's (it would turn "--" into an
// en dash before the ids are made).
import { rehypeHeadingIds, type ShikiConfig, type UnifiedProcessorOptions } from '@astrojs/markdown-remark';
import rehypeAutolinkHeadings from 'rehype-autolink-headings';
import rehypeCallouts from '../plugins/rehype-callouts';
import rehypeKeywords from '../plugins/rehype-keywords';
import remarkHtmlAllowlist from '../plugins/remark-html-allowlist';
import remarkPageMeta from '../plugins/remark-page-meta';
import remarkRepoLinks from '../plugins/remark-repo-links';
import { ROUTES } from './routes';

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
  remarkPlugins: [remarkRepoLinks, remarkPageMeta, remarkHtmlAllowlist],
  rehypePlugins: [
    rehypeHeadingIds,
    [
      rehypeAutolinkHeadings,
      { behavior: 'append', properties: { className: ['heading-anchor'], ariaHidden: 'true', tabIndex: -1 } },
    ],
    [rehypeKeywords, { sources: KEYWORD_SOURCES }],
    rehypeCallouts,
  ],
};
