// Markdown copies of the domain pages and the domains overview: the README as
// written, then the profile values and the workflows the profile lists.
import { loadProfiles } from '../data/profiles';
import { loadWorkflows } from '../data/workflows';
import { readRepoFile } from '../lib/repo';
import { PROPOSED_WORKFLOW_STATUS } from '../lib/status';
import {
  approvalLadder,
  checkpointCaption,
  checkpointHeader,
  checkpointPolicy,
  complianceCaption,
  complianceRows,
  evidenceCaption,
  evidencePolicy,
  ladderCaption,
  OUTCOME_WORD,
  policyWord,
  rankedSources,
  sourcesCaption,
  trustCaption,
  workflowCardCaption,
} from '../lib/domain-figures';
import { sortedTrustWeights, toYaml } from '../lib/views';
import { blocks, cell, code, fence, figure, generatedLine, markdownCopy, mdLink, table } from './md';
import type { Twin } from './types';

export function domainTwin(key: string, description: string | null): Twin {
  const d = loadProfiles().find((p) => p.key === key);
  if (!d) throw new Error(`twins: unknown domain ${key}`);
  const wfs = loadWorkflows();
  const readme = d.readme ? markdownCopy(d.readme, readRepoFile(d.readme), { sourceNote: true }) : `# ${d.key} domain\n`;
  const title = /^# (.+)$/m.exec(readme)?.[1] ?? `${d.key} domain`;
  const workflows = d.workflows.map((w) => {
    const wf = wfs.byId.get(w.id);
    return w.defined && wf
      ? `- ${mdLink(code(w.id), `/workflows/${wf.slug}/`)}: ${wf.goal} ${workflowCardCaption(wf)}`
      : `- ${code(w.id)}: ${PROPOSED_WORKFLOW_STATUS}`;
  });
  const markdown = blocks(
    readme,
    '## Profile values',
    `${generatedLine([d.profileFile])} Profile version ${d.version}. Where the text above repeats a value, this one is authoritative.`,
    d.description,
    fence('yaml', toYaml(d.profile)),
    ...profileFigures(d.profile),
    '## Workflows in this profile',
    workflows.length === 0 ? 'The profile lists no workflows.' : workflows.join('\n'),
  );
  return { title, description: description ?? d.description, markdown };
}

/** The "**Figure:**" blocks of the domain page's figures (visual spec 3.5), with the page's captions. */
function profileFigures(p: Record<string, unknown>): string[] {
  const out: string[] = [];
  const weights = sortedTrustWeights(p);
  if (weights.length > 0) {
    out.push(figure('Trust weight per source, highest first', trustCaption(p), table(['Source', 'Weight'], weights.map((w) => [code(w.source), w.weight.toFixed(2)]))));
  }
  const ladder = approvalLadder(p);
  if (ladder) {
    const rows = ladder.rows.map((r) => [r.level, OUTCOME_WORD[r.outcome]]);
    const body = table(['Risk level', 'Outcome'], rows);
    out.push(figure('What happens at each risk level', ladderCaption(ladder), ladder.blocked.length > 0 ? `${body}\n\nNever autonomous: ${ladder.blocked.map(code).join(', ')}.` : body));
  }
  const policy = checkpointPolicy(p);
  if (policy && policy.triggers.length > 0) {
    const header = checkpointHeader(policy);
    const list = policy.triggers.map((t) => `- ${code(t.name)}: ${policyWord(t.level)}`).join('\n');
    out.push(figure('When a checkpoint is made', checkpointCaption(policy), header ? `${header}.\n\n${list}` : list));
  }
  const e = evidencePolicy(p);
  if (e && (e.minimumConfidence !== null || e.anchorTypes.length > 0 || e.grounding.length > 0)) {
    const rows = [
      ...(e.minimumConfidence === null ? [] : [`- Minimum confidence: ${e.minimumConfidence.toFixed(2)}`]),
      ...(e.anchorTypes.length > 0 ? [`- Evidence anchor types: ${e.anchorTypes.map(code).join(', ')}`] : []),
      ...(e.grounding.length > 0 ? [`- Must cite evidence: ${e.grounding.map(code).join(', ')}`] : []),
    ];
    out.push(figure('What a claim must carry', evidenceCaption(e), rows.join('\n')));
  }
  const sources = rankedSources(p);
  if (sources.length > 0) {
    out.push(figure('Sources and their default trust', sourcesCaption(sources), table(['Source', 'Type', 'Default trust'], sources.map((s) => [cell(s.name), code(s.type), s.trust.toFixed(2)]))));
  }
  const compliance = complianceRows(p);
  if (compliance && compliance.length > 0) {
    out.push(figure('Compliance markers', complianceCaption(compliance), table(['Marker', 'Value'], compliance.map((r) => [code(r.key), r.value]))));
  }
  return out;
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
