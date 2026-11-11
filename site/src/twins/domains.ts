// Markdown copies of the domain pages and the domains overview: the README as
// written, then the profile values and the workflows the profile lists.
import { loadProfiles } from '../data/profiles';
import { loadWorkflows } from '../data/workflows';
import { readRepoFile } from '../lib/repo';
import { PROPOSED_WORKFLOW_STATUS } from '../lib/status';
import { toYaml } from '../lib/views';
import { blocks, cell, code, fence, generatedLine, markdownCopy, mdLink, table } from './md';
import type { Twin } from './types';

export function domainTwin(key: string, description: string | null): Twin {
  const d = loadProfiles().find((p) => p.key === key);
  if (!d) throw new Error(`twins: unknown domain ${key}`);
  const wfs = loadWorkflows();
  const readme = d.readme ? markdownCopy(d.readme, readRepoFile(d.readme), { sourceNote: true }) : `# ${d.key} domain\n`;
  const title = /^# (.+)$/m.exec(readme)?.[1] ?? `${d.key} domain`;
  const workflows = d.workflows.map((w) => {
    const wf = wfs.byId.get(w.id);
    return w.defined && wf ? `- ${mdLink(code(w.id), `/workflows/${wf.slug}/`)}: ${wf.goal}` : `- ${code(w.id)}: ${PROPOSED_WORKFLOW_STATUS}`;
  });
  const markdown = blocks(
    readme,
    '## Profile values',
    `${generatedLine([d.profileFile])} Profile version ${d.version}. Where the text above repeats a value, this one is authoritative.`,
    d.description,
    fence('yaml', toYaml(d.profile)),
    '## Workflows in this profile',
    workflows.length === 0 ? 'The profile lists no workflows.' : workflows.join('\n'),
  );
  return { title, description: description ?? d.description, markdown };
}

export function domainsIndexTwin(source: string, description: string | null): Twin {
  const profiles = loadProfiles();
  const readme = markdownCopy(source, readRepoFile(source), { sourceNote: true });
  const title = /^# (.+)$/m.exec(readme)?.[1] ?? 'Domains';
  const markdown = blocks(
    readme,
    '## Domain profiles',
    generatedLine(profiles.map((p) => p.profileFile)),
    table(
      ['Domain', 'Description', 'Workflows in a catalog'],
      profiles.map((p) => [mdLink(p.key, `/domains/${p.key}/`), cell(p.description), String(p.workflows.filter((w) => w.defined).length)]),
    ),
  );
  return { title, description, markdown };
}
