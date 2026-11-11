// Helpers for pages generated from data. Links written by a template do not
// pass through remark-repo-links, so every one is built here and checked:
// - a site URL must be a row of the route table;
// - a spec section must be a heading of the current Standard;
// - a diagnostic code must be in the diagnostics table;
// - a repository path from a YAML file goes through the shared resolver.
// Headings a template adds get ids with the `ref-` prefix, so they cannot take
// an id that a heading of an embedded Markdown source already has.
import GithubSlugger from 'github-slugger';
import { loadDiagnostics } from '../data/diagnostics';
import { loadOntology } from '../data/ontology';
import { loadWorkflows } from '../data/workflows';
import { standardVersions } from '../data/versions';
import { anchorsOf } from './anchors';
import { repoResolver } from './links';
import { readRepoFile } from './repo';
import { kebab, ROUTES, type Route } from './routes';

export const REF_PREFIX = 'ref-';

/** A fresh id maker for one page: `ref-` plus the GitHub slug, unique within the page. */
export function refSlugger(): (text: string) => string {
  const slugger = new GithubSlugger();
  return (text) => `${REF_PREFIX}${slugger.slug(text)}`;
}

const URLS: ReadonlySet<string> = new Set(ROUTES.map((r) => r.url));

/** A site URL, checked against the route table. */
export function pageHref(url: string): string {
  const [path, frag] = url.split('#');
  if (!URLS.has(path!)) throw new Error(`generated: ${url} is not a route`);
  return frag === undefined ? path! : `${path}#${frag}`;
}

export function routeByUrl(url: string): Route {
  const r = ROUTES.find((x) => x.url === url);
  if (!r) throw new Error(`generated: no route for ${url}`);
  return r;
}

export function routesByTemplate(template: Route['template']): Route[] {
  return ROUTES.filter((r) => r.template === template);
}

export function capabilityHref(id: string): string {
  if (!loadOntology().byId.has(id)) throw new Error(`generated: unknown capability ${id}`);
  return pageHref(`/capabilities/${kebab(id)}/`);
}

export function layerHref(layerId: string): string {
  const layer = loadOntology().layers.find((l) => l.id === layerId);
  if (!layer) throw new Error(`generated: unknown layer ${layerId}`);
  return pageHref(`/layers/${layer.slug}/`);
}

export function workflowHref(id: string): string {
  const wf = loadWorkflows().byId.get(id);
  if (!wf) throw new Error(`generated: unknown workflow ${id}`);
  return pageHref(`/workflows/${wf.slug}/`);
}

export function domainHref(key: string): string {
  return pageHref(`/domains/${key}/`);
}

export function diagnosticHref(code: string): string {
  const d = loadDiagnostics().find((x) => x.code === code);
  if (!d) throw new Error(`generated: ${code} is not a diagnostic code of the current Standard`);
  return pageHref(`/spec/diagnostics/#${d.anchor}`);
}

export function isDiagnosticCode(code: string): boolean {
  return loadDiagnostics().some((x) => x.code === code);
}

/** The current Standard's page and source. */
export function currentStandard(): { url: string; source: string; version: string } {
  const current = standardVersions()[0];
  if (!current) throw new Error('generated: no Standard version is tracked');
  return { url: pageHref(`/spec/${current.version}/`), source: current.source, version: current.version };
}

/** The heading of a numbered section of the current Standard: "5.2.1 Safety Flags" or "5. Workflow DSL". */
function specSection(section: string): { slug: string; text: string } {
  const { source } = currentStandard();
  const entry = anchorsOf(source, readRepoFile).entries.find(
    (e) => e.text.startsWith(`${section} `) || e.text.startsWith(`${section}. `),
  );
  if (!entry) throw new Error(`generated: the current Standard has no section ${section}`);
  return entry;
}

/** Link to a numbered section of the current Standard, e.g. "5.2.1". */
export function specSectionHref(section: string): string {
  return `${currentStandard().url}#${specSection(section).slug}`;
}

/**
 * A repository path written in a YAML file (a workflow's `profile`, an input's
 * `ref`, a step's `mapping_ref`), relative to the repository root. It must be
 * a tracked file; YAML files link to GitHub.
 */
export function repoPathHref(path: string, from: string): string {
  const r = repoResolver()(from, `/${path}`, 'html');
  if (!r.ok) throw new Error(`generated: ${path}: ${r.reason}`);
  return r.url;
}

/** Plain text and inline code spans of a table cell written in Markdown. */
export type Inline = { code: boolean; text: string }[];

/**
 * Split a one-line Markdown cell into text and code spans. Only code spans are
 * supported; links, emphasis or HTML in a cell fail the build so nothing is
 * shown as raw Markdown.
 */
export function inlineMarkdown(md: string): Inline {
  const out: Inline = [];
  const parts = md.split('`');
  if (parts.length % 2 === 0) throw new Error(`generated: unbalanced backticks in "${md}"`);
  parts.forEach((text, i) => {
    const code = i % 2 === 1;
    if (!code && /\]\(|\*\*|<[a-z/]|(^|\s)_\S/i.test(text)) {
      throw new Error(`generated: "${md}" has Markdown other than code spans`);
    }
    if (text !== '') out.push({ code, text: code ? text : text.replace(/\\\|/g, '|') });
  });
  return out;
}
