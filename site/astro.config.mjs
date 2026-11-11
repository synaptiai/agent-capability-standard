import { defineConfig } from 'astro/config';
import { unified, rehypeHeadingIds } from '@astrojs/markdown-remark';
import rehypeAutolinkHeadings from 'rehype-autolink-headings';

// Astro 7 renders Markdown with Satteri unless a unified() processor is set,
// and only unified() runs remark and rehype plugins. SmartyPants is off so
// heading ids match GitHub's (it would turn "--" into an en dash first).
// The build script passes --force: a warm build skips the Markdown plugins.
export default defineConfig({
  site: 'https://acs.synapti.ai',
  output: 'static',
  trailingSlash: 'always',
  build: { format: 'directory' },
  markdown: {
    processor: unified({
      smartypants: false,
      rehypePlugins: [rehypeHeadingIds, [rehypeAutolinkHeadings, { behavior: 'append' }]],
    }),
  },
});
