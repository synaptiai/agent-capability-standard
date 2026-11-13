// Entry point of the Cloudflare Pages worker, bundled into dist/_worker.js
// by src/lib/worker-build.ts when the site is built.
//
// Why "advanced mode" (_worker.js) and not a functions/ folder:
// - The deploy job in .github/workflows/site.yml downloads the built dist/
//   artifact and runs `wrangler pages deploy dist` with no checkout of the
//   repository. Wrangler compiles a functions/ folder only from the directory
//   it runs in, so site/functions/ would never be deployed; a _worker.js
//   inside dist/ is deployed with the files, by that same command, unchanged.
// - The bundle is one self-contained ES module that uses only web-standard
//   APIs (no node: imports, no compatibility flags), because no wrangler
//   configuration file reaches the deploy either.
//
// Which requests run it: dist/_routes.json (written next to it) sends every
// path to the worker except the static assets that never need it (scripts,
// styles, the search index, fonts, images, robots.txt, the sitemap and
// llms.txt). Those stay free, unlimited static requests; every other request
// counts against the Workers plan (100,000 a day on the Free plan).
//
// Cloudflare's documentation says _headers and _redirects are not applied to
// responses a worker returns, so the worker applies the same rules itself
// (static-rules.ts).

import type { Env, WorkerConfig } from './env';
import { createHandler } from './site';

declare const __ACS_WORKER_CONFIG__: WorkerConfig;

const handle = createHandler(__ACS_WORKER_CONFIG__);

export default {
  fetch(request: Request, env: Env): Promise<Response> {
    return handle(request, env);
  },
};
