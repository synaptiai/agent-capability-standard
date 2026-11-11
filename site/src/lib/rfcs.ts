// The RFC rows the RFC overview and its Markdown copy show: every RFC page
// with its status, target and date, read from the RFC's header lines. An RFC
// status outside the ones spec/GOVERNANCE.md allows fails the build.
import { getEntry, render } from 'astro:content';
import type { PageMeta } from '../plugins/remark-page-meta';
import { pageHref, routesByTemplate } from './generated';
import { readRepoFile } from './repo';
import { ROUTES } from './routes';
import { governanceStatuses } from './governance';

export function allowedRfcStatuses(): string[] {
  return governanceStatuses(readRepoFile('spec/GOVERNANCE.md'));
}

export interface RfcRow {
  url: string;
  label: string;
  title: string;
  status: string;
  target: string | null;
  targetUrl: string | null;
  date: string | null;
  numbered: boolean;
}

export async function rfcRows(): Promise<RfcRow[]> {
  const allowed = allowedRfcStatuses();
  const rows: RfcRow[] = [];
  for (const r of routesByTemplate('rfc')) {
    const entry = await getEntry('docs', r.source!);
    if (!entry) throw new Error(`rfcs: no docs entry for ${r.source}`);
    const { remarkPluginFrontmatter } = await render(entry);
    const page = remarkPluginFrontmatter.page as PageMeta | undefined;
    if (!page?.title) throw new Error(`rfcs: ${r.source} has no title`);
    const num = /^\/rfcs\/(\d{4})\/$/.exec(r.url)?.[1] ?? null;
    const status = page.status;
    if (!status) throw new Error(`rfcs: ${r.source} has no Status line`);
    if (num !== null && !allowed.includes(status)) {
      throw new Error(`rfcs: ${r.source} has status "${status}"; spec/GOVERNANCE.md allows ${allowed.join(', ')}`);
    }
    const target = page.meta.find((m) => m.key === 'Target')?.value ?? null;
    const targetVersion = target ? /Standard v(\d+\.\d+\.\d+)/.exec(target)?.[1] : undefined;
    const targetUrl = targetVersion && ROUTES.some((x) => x.url === `/spec/${targetVersion}/`) ? pageHref(`/spec/${targetVersion}/`) : null;
    rows.push({
      url: r.url,
      label: num ? `RFC-${num}` : r.title,
      title: num ? page.title.replace(/^RFC-\d{4}:\s*/, '') : page.title,
      status,
      target,
      targetUrl,
      date: page.date,
      numbered: num !== null,
    });
  }
  return rows;
}
