// The text files for agents and crawlers: llms.txt (in the llmstxt.org
// layout: when to use the standard, the interfaces for agents, and each
// section's main pages), one llms.txt per section listing every page's
// Markdown copy, llms-full.txt (the
// Specification, Capabilities and Workflows sections in one file), robots.txt and
// the sitemap. All are built from the route table.
import { loadVersions, olderVersionNote } from '../data/versions';
import { homeDescription, opening } from './home';
import { SITE_ORIGIN } from './links';
import { ROUTES, SECTIONS, type Route, type Section } from './routes';
import { GITHUB_BASE, githubBlobUrl, readRepoFile } from './repo';
import { pageLastModified } from './page-dates';
import {
  AGENT_SKILLS_INDEX_PATH,
  AGENTS_MD_PATH,
  AI_CATALOG_PATH,
  API_INDEX_PATH,
  ARD_PATH,
  DEVELOPERS_PATH,
  LLMS_FULL_PATH,
  LLMS_TXT_PATH,
  MCP_PATH,
  MCP_SERVER_CARD_PATH,
  OPENAPI_PATH,
  SECTION_LLMS,
} from './agent-contract';
import { shortDescription } from '../plugins/remark-page-meta';
import { twinFor } from '../twins';
import { fence, mdUrl } from '../twins/md';

export const SITEMAP_PATH = '/sitemap.xml';

const summaryLine = homeDescription;

function versionsLine(): string {
  const v = loadVersions();
  const currentText = readRepoFile(v.standard.current.source);
  const previous = v.standard.previous
    .map((p) => `${p.version}${olderVersionNote(p.version, currentText).stillSupported ? ' (still supported)' : ''}`)
    .join(', ');
  return [
    `Current: Standard ${v.standard.current.version} (${v.standard.current.status}).`,
    previous && `Previous: Standard ${previous}.`,
    `Ontology ${v.ontology}. Claude Code plugin ${v.plugin}.`,
  ]
    .filter(Boolean)
    .join(' ');
}

const ordered = (rows: readonly Route[]) => [...rows].sort((a, b) => a.order - b.order);

/** A list line for a page's Markdown copy, its description cut to `max` characters. */
async function copyLine(r: Route, max: number): Promise<string> {
  const t = await twinFor(r);
  const desc = t.description ? `: ${shortDescription(t.description.replace(/\s+/g, ' '), max)}` : '';
  const label = r.group && r.template !== 'layer' ? `${t.title} (${r.group})` : t.title;
  return `- [${label.replace(/[[\]]/g, '')}](${mdUrl(r.url)})${desc}`;
}

/** The sections that have pages besides the home page, each with its own llms.txt. */
export function llmsSections(): { id: Section; label: string; url: string; rows: Route[] }[] {
  return SECTIONS.filter((s) => s.id !== 'home')
    .map((s) => ({ id: s.id, label: s.label, url: `/${s.id}/${SECTION_LLMS}`, rows: ordered(ROUTES.filter((r) => r.section === s.id)) }))
    .filter((s) => s.rows.length > 0);
}

/**
 * The pages the root llms.txt lists for a section: the pages outside any
 * sidebar group, each group's overview, and the layer pages. The section's
 * own llms.txt lists them all.
 */
export function shortList(rows: readonly Route[]): Route[] {
  return rows.filter((r) => !r.group || r.template === 'layer' || r.title === 'Overview');
}

/** The rows of the README's "When to Use This" table: [what you have, what the standard provides]. */
export function whenToUseRows(): [string, string][] {
  const readme = readRepoFile('README.md');
  const at = readme.search(/^### When to Use This\s*$/m);
  if (at === -1) throw new Error('agent-files: README.md has no "### When to Use This" section');
  const rows: [string, string][] = [];
  for (const line of readme.slice(at).split('\n').slice(1)) {
    if (/^#{1,6}\s/.test(line) || /^---\s*$/.test(line)) break;
    const cells = line.split('|').slice(1, -1).map((c) => c.trim());
    if (cells.length !== 2 || /^-+$/.test(cells[0]!) || /^If you have/.test(cells[0]!)) continue;
    rows.push([cells[0]!, cells[1]!]);
  }
  if (rows.length === 0) throw new Error('agent-files: the "When to Use This" table in README.md has no rows');
  return rows;
}

/** The "When to use this standard" section of llms.txt and the agents guide. */
export function whenToUse(): string {
  const current = loadVersions().standard.current.version;
  const lines = [
    '## When to use this standard',
    '',
    'Consult it when you design, review or run a multi-step agent workflow and need to know:',
    '',
    `- which capability a step uses, and its typed input and output contract: [Capabilities](${mdUrl('/capabilities/')});`,
    `- which steps must come first: a checkpoint before \`mutate\`, \`send\` and \`rollback\`, and the other ordering edges: [Edge types](${mdUrl('/spec/edge-types/')});`,
    `- whether a workflow is valid, and what a validator error or warning code means: [Diagnostics](${mdUrl('/spec/diagnostics/')});`,
    `- the normative rules themselves: [Standard v${current}](${mdUrl(`/spec/${current}/`)}).`,
    '',
    'The README puts it this way:',
    '',
    ...whenToUseRows().map(([have, gives]) => `- ${have}: ${gives.charAt(0).toLowerCase()}${gives.slice(1)}.`),
  ];
  return lines.join('\n');
}

/** Links to the interfaces for agents, shared by llms.txt and the agents guide. */
export function agentLinks(): string[] {
  const o = SITE_ORIGIN;
  return [
    `- [Guide for agents](${o}${AGENTS_MD_PATH}): how to read this site as Markdown, query its data and use its skills.`,
    `- [Data API](${o}${OPENAPI_PATH}): the OpenAPI 3.1 description of a read-only JSON API under ${o}/api/v1/ (GET only, no key); start at [the API index](${o}${API_INDEX_PATH}).`,
    `- [MCP server card](${o}${MCP_SERVER_CARD_PATH}): a read-only MCP server that searches and reads the standard, at \`${o}${MCP_PATH}\` (Streamable HTTP; send JSON-RPC with POST).`,
    `- [Developers](${o}${DEVELOPERS_PATH}index.md): the API, the MCP server and the Markdown copies on one page.`,
    `- [Agent skills index](${o}${AGENT_SKILLS_INDEX_PATH}): every skill of the Claude Code plugin as a SKILL.md file, with its SHA-256 digest.`,
    `- [Resource catalog](${o}${ARD_PATH}): the agent resources above in Agentic Resource Discovery form (also at ${o}${AI_CATALOG_PATH}).`,
    `- [AGENTS.md](${githubBlobUrl('AGENTS.md')}): instructions for coding agents that work on the repository.`,
    `- [llms-full.txt](${o}${LLMS_FULL_PATH}): the current Standard, every capability page and every workflow page in one file.`,
  ];
}

export async function llmsTxt(): Promise<string> {
  const out = [
    '# Agent Capability Standard',
    '',
    `> ${summaryLine()}`,
    '',
    versionsLine(),
    '',
    `Every page of ${SITE_ORIGIN} has a Markdown copy at its URL followed by index.md; the home page's is [${SITE_ORIGIN}/index.md](${mdUrl('/')}). Below, each section lists its main pages and links its own llms.txt, which lists every page of the section.`,
    '',
    whenToUse(),
    '',
    '## For agents',
    '',
    ...agentLinks(),
  ];
  for (const section of llmsSections()) {
    out.push('', `## ${section.label}`, '', `- [All ${section.rows.length} pages of ${section.label}](${SITE_ORIGIN}${section.url})`);
    for (const r of shortList(section.rows)) out.push(await copyLine(r, 120));
  }
  return `${out.join('\n')}\n`;
}

/** /<section>/llms.txt: every page of one section, in sidebar order. */
export async function sectionLlmsTxt(id: Section): Promise<string> {
  const section = llmsSections().find((s) => s.id === id);
  if (!section) throw new Error(`agent-files: no section ${id} with pages`);
  const overview = section.rows[0]!;
  const intro = (await twinFor(overview)).description;
  const out = [`# Agent Capability Standard: ${section.label}`, ''];
  if (intro) out.push(`> ${intro.replace(/\s+/g, ' ')}`, '');
  out.push(
    `The ${section.rows.length} pages of the ${section.label} section, as Markdown copies. The whole site is listed from [llms.txt](${SITE_ORIGIN}${LLMS_TXT_PATH}).`,
    '',
    '## Pages',
    '',
  );
  for (const r of section.rows) out.push(await copyLine(r, 160));
  return `${out.join('\n')}\n`;
}

/** /llms.md: llms.txt, served as Markdown for agents that ask for a .md file. */
export async function llmsMd(): Promise<string> {
  return llmsTxt();
}

/** /agents.md: how an agent should use this site. */
export function agentsMd(): string {
  const o = SITE_ORIGIN;
  const example = mdUrl('/capabilities/');
  const install = opening().install;
  return `${[
    '# Using this site from an agent',
    '',
    `> ${summaryLine()}`,
    '',
    versionsLine(),
    '',
    'This site is the documentation of the Agent Capability Standard. Everything on it is public and read-only, and nothing needs a key or an account.',
    '',
    whenToUse(),
    '',
    '## Read the pages as Markdown',
    '',
    `- Every page has a Markdown copy at its URL followed by \`index.md\`: the capabilities overview at ${o}/capabilities/ has its copy at ${example}. Each HTML page names its copy in a \`<link rel="alternate" type="text/markdown">\` element.`,
    '- Each copy opens with YAML front matter: `title`, `description`, `canonical` (the HTML page) and `last_updated` (the date of the last commit to the files the page is built from), then the page as Markdown with a top-level heading.',
    '- A figure on a page appears in its copy as a paragraph that starts with **Figure:**, followed by a table or a list with the same data.',
    `- [llms.txt](${o}${LLMS_TXT_PATH}) lists the main pages of each section and links one llms.txt per section, which lists every page. [llms-full.txt](${o}${LLMS_FULL_PATH}) holds the current Standard, every capability page and every workflow page in one file.`,
    '',
    '## Query the data and the MCP server',
    '',
    ...agentLinks().filter((l) => !l.includes(AGENTS_MD_PATH) && !l.includes(LLMS_FULL_PATH)),
    '',
    '## Use the skills',
    '',
    `Each capability and each composed workflow is also a skill of the Claude Code plugin. The [agent skills index](${o}${AGENT_SKILLS_INDEX_PATH}) lists every skill with its name, description, the URL of its SKILL.md and that file's SHA-256 digest. To install them all as the plugin (${install.label}):`,
    '',
    fence('bash', install.commands.join('\n')),
    '',
    '## Report a problem',
    '',
    `Open an issue at ${githubIssuesUrl()}. A security vulnerability is the exception: report it privately, as the [security model](${mdUrl('/spec/security/')}) describes.`,
  ].join('\n')}\n`;
}

/** The repository's issue tracker. */
export function githubIssuesUrl(): string {
  return `${GITHUB_BASE}/issues`;
}

/**
 * Routes in llms-full.txt: the Specification, Capabilities and Workflows
 * sections in manifest order. Older Standards are left out, so the file holds
 * one Standard; their own Markdown copies are listed in llms.txt.
 */
export function fullTextRoutes(): Route[] {
  const older = new Set(loadVersions().standard.previous.map((p) => `/spec/${p.version}/`));
  // The current Standard first, then the section's other pages (its listing among them) in sidebar order.
  const spec = ordered(ROUTES.filter((r) => r.section === 'spec' && !older.has(r.url)));
  return [
    ...spec.filter((r) => r.template === 'spec'),
    ...spec.filter((r) => r.template !== 'spec'),
    ...ordered(ROUTES.filter((r) => r.section === 'capabilities')),
    ...ordered(ROUTES.filter((r) => r.section === 'workflows')),
  ];
}

export async function llmsFullTxt(): Promise<string> {
  const parts = [`# Agent Capability Standard\n\n> ${summaryLine()}\n\n${versionsLine()}\n\nThis file holds the current Standard and the rest of the Specification section, every capability page and every workflow page. Older Standards are left out; llms.txt links their Markdown copies. Each page starts with a comment that gives its URL.\n`];
  for (const r of fullTextRoutes()) {
    const t = await twinFor(r);
    parts.push(`<!-- ${mdUrl(r.url)} -->\n\n${t.markdown}`);
  }
  return parts.join('\n');
}

/**
 * Crawlers of AI search and of agents fetching a page for a user, named so
 * their policy is explicit. Each gets the same rule as every other crawler.
 */
export const NAMED_AGENTS = ['OAI-SearchBot', 'ChatGPT-User', 'Claude-SearchBot', 'Claude-User', 'PerplexityBot', 'Perplexity-User'] as const;

/**
 * Allow everything to every crawler. The named crawlers get their own group
 * with the same single rule, so the file says the same thing for everyone.
 */
export function robotsTxt(): string {
  const groups = [['*'], [...NAMED_AGENTS]].map((agents) => `${agents.map((a) => `User-agent: ${a}`).join('\n')}\nAllow: /`);
  return `${groups.join('\n\n')}\n\nSitemap: ${SITE_ORIGIN}${SITEMAP_PATH}\n`;
}

/**
 * Every HTML page of the site; the 404 page has no route, Markdown copies and
 * text files are not pages. Each URL's lastmod is the date of the last commit
 * to a file the page is built from (lib/page-dates.ts).
 */
export function sitemapXml(): string {
  const urls = ROUTES.map((r) => {
    const lastmod = pageLastModified(r);
    return `  <url><loc>${SITE_ORIGIN}${r.url}</loc>${lastmod ? `<lastmod>${lastmod}</lastmod>` : ''}</url>`;
  });
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.join('\n')}\n</urlset>\n`;
}
