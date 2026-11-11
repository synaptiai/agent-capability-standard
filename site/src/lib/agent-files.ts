// The text files for agents and crawlers: llms.txt (every page's Markdown
// copy, by section, in the llmstxt.org layout), llms-full.txt (the
// Specification, Capabilities and Workflows sections in one file), robots.txt and
// the sitemap. All are built from the route table.
import { loadVersions, olderVersionNote } from '../data/versions';
import { readRepoFile } from './repo';
import { homeDescription } from './home';
import { SITE_ORIGIN } from './links';
import { ROUTES, SECTIONS, type Route } from './routes';
import { shortDescription } from '../plugins/remark-page-meta';
import { twinFor } from '../twins';
import { mdUrl } from '../twins/md';

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

export async function llmsTxt(): Promise<string> {
  const out = [
    '# Agent Capability Standard',
    '',
    `> ${summaryLine()}`,
    '',
    versionsLine(),
    '',
    `Every page of ${SITE_ORIGIN} has a Markdown copy at its URL followed by index.md. This file lists all of them.`,
  ];
  for (const section of SECTIONS) {
    const rows = ordered(ROUTES.filter((r) => r.section === section.id));
    if (rows.length === 0) continue;
    out.push('', `## ${section.label}`, '');
    for (const r of rows) {
      const t = await twinFor(r);
      const desc = t.description ? `: ${shortDescription(t.description.replace(/\s+/g, ' '), 160)}` : '';
      const label = r.group && r.template !== 'layer' ? `${t.title} (${r.group})` : t.title;
      out.push(`- [${label.replace(/[[\]]/g, '')}](${mdUrl(r.url)})${desc}`);
    }
  }
  return `${out.join('\n')}\n`;
}

/**
 * Routes in llms-full.txt: the Specification, Capabilities and Workflows
 * sections in manifest order. Older Standards are left out, so the file holds
 * one Standard; their own Markdown copies are listed in llms.txt.
 */
export function fullTextRoutes(): Route[] {
  const older = new Set(loadVersions().standard.previous.map((p) => `/spec/${p.version}/`));
  return [
    ...ordered(ROUTES.filter((r) => r.section === 'spec' && !older.has(r.url))),
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

export function robotsTxt(): string {
  return `User-agent: *\nAllow: /\n\nSitemap: ${SITE_ORIGIN}${SITEMAP_PATH}\n`;
}

/** Every HTML page of the site; the 404 page has no route, Markdown copies and text files are not pages. */
export function sitemapXml(): string {
  const urls = ROUTES.map((r) => `  <url><loc>${SITE_ORIGIN}${r.url}</loc></url>`);
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.join('\n')}\n</urlset>\n`;
}
