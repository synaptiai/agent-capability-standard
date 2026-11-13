// /<section>/llms.txt: every page of one section, as Markdown copies. The
// root llms.txt links each of these.
import type { APIRoute, GetStaticPaths } from 'astro';
import { llmsSections, sectionLlmsTxt } from '../../lib/agent-files';
import type { Section } from '../../lib/routes';

export const getStaticPaths = (() => llmsSections().map((s) => ({ params: { section: s.id } }))) satisfies GetStaticPaths;

export const GET: APIRoute = async ({ params }) =>
  new Response(await sectionLlmsTxt(params.section as Section), { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
