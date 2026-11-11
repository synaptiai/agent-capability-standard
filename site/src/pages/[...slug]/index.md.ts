// The Markdown copy of every page, at <route>index.md (the home page's is
// /index.md). src/twins/ writes each one; the 404 page has none.
import type { APIRoute, GetStaticPaths } from 'astro';
import { ROUTES, type Route } from '../../lib/routes';
import { twinFor } from '../../twins';

export const getStaticPaths = (() =>
  ROUTES.map((route) => ({
    params: { slug: route.url.replace(/^\/|\/$/g, '') || undefined },
    props: { route },
  }))) satisfies GetStaticPaths;

export const GET: APIRoute = async ({ props }) => {
  const { markdown } = await twinFor((props as { route: Route }).route);
  return new Response(markdown, { headers: { 'Content-Type': 'text/markdown; charset=utf-8' } });
};
