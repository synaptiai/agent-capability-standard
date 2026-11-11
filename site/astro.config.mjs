import { defineConfig } from 'astro/config';
import { unified } from '@astrojs/markdown-remark';
import { rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { checkBuiltSlugs } from './src/lib/check-slugs';
import { formatLinkStats, linkStats } from './src/lib/links';
import { markdownSources } from './src/lib/routes';
import { PROCESSOR_OPTIONS, SHIKI_CONFIG } from './src/lib/markdown';

// Astro 7 renders Markdown with Satteri unless a unified() processor is set,
// and only unified() runs remark and rehype plugins. The plugin chain, its
// order and the Shiki settings live in src/lib/markdown.ts so the tests use
// the same ones.
//
// A warm build reuses the rendered Markdown cached in the content data store
// and skips the plugins, and with them the link checks. So the cache is
// removed whenever this config loads, and every build (`npm run build`,
// which also passes --force, or a plain `astro build`) renders every source.
for (const dir of ['node_modules/.astro', '.astro']) {
  rmSync(new URL(`./${dir}/data-store.json`, import.meta.url), { force: true });
}

export default defineConfig({
  site: 'https://acs.synapti.ai',
  output: 'static',
  trailingSlash: 'always',
  build: { format: 'directory' },
  markdown: {
    processor: unified(PROCESSOR_OPTIONS),
    shikiConfig: SHIKI_CONFIG,
  },
  integrations: [
    {
      name: 'acs-markdown-report',
      hooks: {
        'astro:build:done': ({ dir, logger }) => {
          // A warm build reuses cached renders and skips the link plugin, so
          // the link checks must be seen to have run on every source.
          const expected = markdownSources().length;
          if (linkStats.size !== expected) {
            throw new Error(`links: checked ${linkStats.size} of ${expected} Markdown sources; the content cache was reused`);
          }
          logger.info(`links: ${formatLinkStats()}`);
          // Every built Markdown page must carry the ids github-slugger gives its source.
          const slugs = checkBuiltSlugs(fileURLToPath(dir));
          if (slugs.problems.length > 0) {
            throw new Error(`heading ids differ from github-slugger run on the source:\n  ${slugs.problems.join('\n  ')}`);
          }
          logger.info(`heading ids: ${slugs.headings} ids on ${slugs.pages} pages equal github-slugger run on their sources`);
        },
      },
    },
  ],
});
