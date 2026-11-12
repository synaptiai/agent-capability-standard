// Text equivalents, in a page's Markdown copy, of the figures the prose and
// RFC templates draw that the source text does not already hold (visual spec
// 6.1): F-O1 on the OASF safety proposal and the RFC lifecycle track. Box
// diagrams, pattern fences and table marks keep their source text, which is
// their own text equivalent.
import { getEntry, render } from 'astro:content';
import { allowedRfcStatuses } from '../lib/rfcs';
import type { PageMeta } from '../plugins/remark-page-meta';
import { lifecycleSentence, rfcLifecycle } from '../lib/prose-page';
import type { Route } from '../lib/routes';
import { OASF_PROPOSAL } from '../plugins/rehype-prose-figures';
import { oasfMapTwin } from './oasf';

/** Blocks to append to a prose or RFC page's copy. */
export async function proseFigureBlocks(route: Route): Promise<string[]> {
  const out: string[] = [];
  if (route.template === 'rfc') {
    const entry = await getEntry('docs', route.source!);
    const page = entry ? ((await render(entry)).remarkPluginFrontmatter.page as PageMeta | undefined) : undefined;
    if (page?.status) out.push(`**Lifecycle.** ${lifecycleSentence(rfcLifecycle(page.status, allowedRfcStatuses(), route.source!), page.date)}`);
  }
  if (route.source === OASF_PROPOSAL) out.push(oasfMapTwin());
  return out;
}
