// Markdown copies of the workflow pages and the workflows overview.
import { loadWorkflows, type Workflow } from '../data/workflows';
import { readRepoFile } from '../lib/repo';
import { kebab } from '../lib/routes';
import { composedSkillsFor, gateRows, profilesListing, schemaRows } from '../lib/views';
import { blocks, cell, code, fence, generatedLine, mdLink, table } from './md';
import type { Twin } from './types';

/** The workflow's own text in its catalog file: its top-level key up to the next one, comments kept. */
export function workflowYaml(wf: Workflow): string {
  const lines = readRepoFile(wf.source).split('\n');
  const start = lines.findIndex((l) => l === `${wf.id}:` || l.startsWith(`${wf.id}: `));
  if (start === -1) throw new Error(`twins: ${wf.source} has no top-level key ${wf.id}`);
  let end = lines.findIndex((l, i) => i > start && /^[A-Za-z_][\w-]*:/.test(l));
  if (end === -1) end = lines.length;
  // Comment lines just above the next key belong to that key.
  while (end - 1 > start && /^(#.*)?$/.test(lines[end - 1]!)) end -= 1;
  return lines.slice(start, end).join('\n');
}

function stepFlags(wf: Workflow, i: number): string {
  const e = wf.steps[i]!.effective;
  const flags = [`risk ${e.risk}`];
  if (e.mutation) flags.push('changes state');
  if (e.checkpoint.needed) flags.push('needs a checkpoint before it');
  if (e.requires_approval) flags.push('needs approval');
  return flags.join(', ');
}

export function workflowTwin(workflowId: string): Twin {
  const wf = loadWorkflows().byId.get(workflowId);
  if (!wf) throw new Error(`twins: unknown workflow ${workflowId}`);
  const inputs = schemaRows(wf.inputs);
  const steps = wf.steps.map((s, i) => {
    const gates = gateRows(s).map((g) => `   - Gate: when ${code(g.when)}, ${g.action}${g.message ? `: ${g.message}` : ''}`);
    return [
      `${s.index}. ${mdLink(code(s.capability), `/capabilities/${kebab(s.capability)}/`)}: ${s.purpose}${s.store_as ? ` Stores ${code(s.store_as)}.` : ''} (${stepFlags(wf, i)})`,
      ...gates,
    ].join('\n');
  });
  const profiles = profilesListing(wf.id);
  const skills = composedSkillsFor(wf.id);
  const related = [
    ...(wf.domain ? [`- Domain: ${mdLink(wf.domain, `/domains/${wf.domain}/`)}`] : []),
    ...profiles.map((p) => `- Listed by the ${mdLink(p.key, `/domains/${p.key}/`)} profile`),
    ...skills.map((d) => `- Composed skill: ${mdLink(d, `/guides/skills/${d}/`)}`),
    ...wf.invokedBy.map((id) => `- Invoked by ${mdLink(code(id), `/workflows/${loadWorkflows().byId.get(id)!.slug}/`)}`),
  ];
  const markdown = blocks(
    `# ${wf.goal}`,
    generatedLine([wf.source]),
    [
      `- Workflow id: ${code(wf.id)}`,
      `- Risk: ${wf.risk}`,
      `- Catalog: ${wf.catalog === 'core' ? 'reference workflows' : `domain workflows (${wf.domain ?? 'no domain'})`}`,
      ...(wf.standardVersion ? [`- Declares Standard ${wf.standardVersion}`] : []),
      `- Steps: ${wf.steps.length}`,
    ].join('\n'),
    wf.description,
    '## Inputs',
    inputs.length === 0
      ? 'None.'
      : table(['Field', 'Type', 'Required', 'Description'], inputs.map((r) => [code(r.path), cell(r.type), r.required ? 'Yes' : 'No', cell(r.description)])),
    '## Steps',
    steps.join('\n'),
    wf.success.length > 0 && '## Success criteria',
    wf.success.length > 0 && wf.success.map((s) => `- ${s}`).join('\n'),
    related.length > 0 && '## Related',
    related.length > 0 && related.join('\n'),
    '## Validate it',
    fence('sh', `python tools/validate_workflows.py --catalog ${wf.source}`),
    '## Workflow YAML',
    fence('yaml', workflowYaml(wf)),
  );
  return { title: wf.id, description: wf.goal, markdown };
}

export function workflowsIndexTwin(): Twin {
  const wfs = loadWorkflows();
  const description = `The ${wfs.all.length} workflows of the reference and domain catalogs: ${wfs.core.length} reference workflows and ${wfs.domain.length} domain workflows.`;
  const rows = (list: Workflow[]) =>
    table(
      ['Workflow', 'Goal', 'Risk', 'Steps'],
      list.map((w) => [mdLink(code(w.id), `/workflows/${w.slug}/`), cell(w.goal), w.risk, String(w.steps.length)]),
    );
  const markdown = blocks(
    '# Workflows',
    `A workflow composes capabilities into ordered steps with typed bindings, gates and failure modes. The catalogs define ${wfs.all.length} workflows: ${wfs.core.length} reference workflows and ${wfs.domain.length} domain workflows. See also ${mdLink('Composition patterns', '/workflows/patterns/')}.`,
    generatedLine([...new Set(wfs.all.map((w) => w.source))]),
    '## Reference workflows',
    rows(wfs.core),
    '## Domain workflows',
    rows(wfs.domain),
  );
  return { title: 'Workflows', description, markdown };
}
