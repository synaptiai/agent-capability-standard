// Writes the Cloudflare Pages worker into the build output when the site is
// built (astro.config.mjs, astro:build:done): dist/_worker.js, bundled from
// src/worker/entry.ts with rolldown, and dist/_routes.json, which keeps the
// static assets from invoking it. Why advanced mode: src/worker/entry.ts.
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'rolldown';
import { loadVersions } from '../data/versions';
import type { WorkerConfig } from '../worker/env';
import { SITE_ORIGIN } from './origin';
import { redirectRules } from './redirects';

export const WORKER_FILE = '_worker.js';
export const ROUTES_FILE = '_routes.json';

/**
 * Paths that never run the worker. Each names files the build writes (the
 * dist test checks that every rule matches one), and none of them is a page,
 * a Markdown copy, /api/, /mcp or /.well-known/, which the worker handles.
 */
export const ROUTES_EXCLUDE = [
  '/_astro/*',
  '/pagefind/*',
  '/fonts/*',
  '/favicon.png',
  '/favicon.svg',
  '/og.png',
  '/robots.txt',
  '/sitemap.xml',
  '/llms.txt',
  '/llms-full.txt',
] as const;

export function routesJson(): string {
  return `${JSON.stringify({ version: 1, include: ['/*'], exclude: [...ROUTES_EXCLUDE] }, null, 2)}\n`;
}

export function workerConfig(): WorkerConfig {
  const v = loadVersions();
  return { version: v.plugin, standardVersion: v.standard.current.version, origin: SITE_ORIGIN, redirects: redirectRules() };
}

/** Bundle the worker into `distDir` and write its routes file. Returns the bundle's size in bytes. */
export async function writeWorker(distDir: string): Promise<number> {
  const entry = fileURLToPath(new URL('../worker/entry.ts', import.meta.url));
  const out = await build({
    input: entry,
    platform: 'neutral',
    transform: { define: { __ACS_WORKER_CONFIG__: JSON.stringify(workerConfig()) } },
    output: { format: 'esm', file: path.join(distDir, WORKER_FILE), codeSplitting: false },
    write: true,
  });
  writeFileSync(path.join(distDir, ROUTES_FILE), routesJson());
  return out.output.reduce((n, o) => n + (o.type === 'chunk' ? o.code.length : 0), 0);
}
