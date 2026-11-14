// The Markdown copy of every page, at <route>index.md (the home page's is
// /index.md). src/twins/ writes each one; the 404 page has none. Each opens
// with front matter (lib/copy-frontmatter.ts).
import type { APIRoute, GetStaticPaths } from 'astro';
import { ROUTES, type Route } from '../../lib/routes';
import { twinFor } from '../../twins';
import { servedCopy } from '../../lib/copy-frontmatter';

export const getStaticPaths = (() =>
  ROUTES.map((route) => ({
    params: { slug: route.url.replace(/^\/|\/$/g, '') || undefined },
    props: { route },
  }))) satisfies GetStaticPaths;

export const GET: APIRoute = async ({ props }) => {
  const { route } = props as { route: Route };
  return new Response(servedCopy(route, await twinFor(route)), { headers: { 'Content-Type': 'text/markdown; charset=utf-8' } });
};
