import { defineConfig } from 'astro/config';
import { unified } from '@astrojs/markdown-remark';
import { rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { checkDist, formatDistReport } from './src/lib/check-dist';
import { checkBuiltSlugs } from './src/lib/check-slugs';
import { formatLinkStats, linkStats } from './src/lib/links';
import { spaceBuiltPages } from './src/lib/search-text';
import { REDIRECTS_FILE, redirectsFile } from './src/lib/redirects';
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
//
// ACS_ASTRO_CACHE_DIR (an absolute path) gives a build its own cache, so the
// dist test can build while another Astro command runs in site/ without the
// two reading each other's content cache.
const cacheDir = process.env.ACS_ASTRO_CACHE_DIR;
for (const dir of [cacheDir ?? fileURLToPath(new URL('./node_modules/.astro', import.meta.url)), fileURLToPath(new URL('./.astro', import.meta.url))]) {
  rmSync(path.join(dir, 'data-store.json'), { force: true });
}

export default defineConfig({
  site: 'https://acs.synapti.ai',
  ...(cacheDir ? { cacheDir } : {}),
  output: 'static',
  trailingSlash: 'always',
  build: { format: 'directory' },
  markdown: {
    processor: unified(PROCESSOR_OPTIONS),
    shikiConfig: SHIKI_CONFIG,
  },
  integrations: [
    {
      // The design preview page, only while running `astro dev`; it is never built.
      name: 'acs-design-preview',
      hooks: {
        'astro:config:setup': ({ command, injectRoute }) => {
          if (command === 'dev') {
            injectRoute({ pattern: '/design-preview', entrypoint: new URL('./src/dev/DesignPreview.astro', import.meta.url) });
          }
        },
      },
    },
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
          // Every route is built, nothing else is, and generated pages keep
          // their own heading ids apart from their sources' ids.
          const dist = checkDist(fileURLToPath(dir));
          const distProblems = formatDistReport(dist);
          if (distProblems.length > 0) {
            throw new Error(`built site:\n  ${distProblems.join('\n  ')}`);
          }
          // Search breaks words only at some closing tags; add the missing spaces before Pagefind runs.
          logger.info(`search: spaced table headers and term lists on ${spaceBuiltPages(fileURLToPath(dir))} pages`);
          // The /spec/ redirect names the current version, so it is written here rather than kept in public/.
          writeFileSync(new URL(REDIRECTS_FILE, dir), redirectsFile());
          logger.info(`redirects: ${redirectsFile().trim().split('\n').join('; ')}`);
          logger.info(`pages: every one of the ${dist.pages} routes has a page; no id is repeated; every heading has an id; generated headings use ref- ids`);
        },
      },
    },
  ],
});
