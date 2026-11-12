// Markdown copies of the workflow pages and the workflows overview.
import { loadWorkflows, type Workflow } from '../data/workflows';
import { readRepoFile } from '../lib/repo';
import { kebab } from '../lib/routes';
import { composedSkillsFor, gateRows, profilesListing, schemaRows } from '../lib/views';
import { dataFlowGrid, inputsCaption, layersUsed, readsList, riskSummary, spineTable, stepList, workflowSpine } from '../lib/workflow-figures';
import { blocks, cell, code, fence, figure, generatedLine, mdLink, table } from './md';
import type { Twin } from './types';
import { domainMap, referenceMap } from '../lib/workflow-index';

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
  const spine = workflowSpine(wf);
  const map = spineTable(spine);
  const flow = dataFlowGrid(wf, spine);
  const risk = riskSummary(wf);
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
    figure(spine.title, spine.caption, table(map.headers, map.rows.map((r) => r.map((c, i) => (i === 1 && c ? code(c) : cell(c)))))),
    '## Inputs',
    inputs.length === 0
      ? 'None.'
      : figure(
          `Inputs of ${wf.id}`,
          inputsCaption(wf),
          table(['Field', 'Type', 'Required', 'Description'], inputs.map((r) => [code(r.path), cell(r.type), r.required ? 'Yes' : 'No', cell(r.description)])),
        ),
    '## Steps',
    steps.join('\n'),
    '## Risk',
    figure(risk.title, risk.caption, risk.steps.map((s) => `- Step ${s.index} (${code(s.capability)}): ${s.risk}`).join('\n')),
    '## Data flow',
    figure(flow.title, flow.caption, readsList(spine).map((l) => `- ${l}`).join('\n') || 'No step reads an earlier output.'),
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
      ['Workflow', 'Goal', 'Risk', 'Steps', 'Layers'],
      list.map((w) => [mdLink(code(w.id), `/workflows/${w.slug}/`), cell(w.goal), w.risk, String(w.steps.length), layersUsed(w).join(', ')]),
    );
  const ref = referenceMap();
  const dom = domainMap();
  const markdown = blocks(
    '# Workflows',
    `A workflow composes capabilities into ordered steps with typed bindings, gates and failure modes. The catalogs define ${wfs.all.length} workflows: ${wfs.core.length} reference workflows and ${wfs.domain.length} domain workflows. See also ${mdLink('Composition patterns', '/workflows/patterns/')}.`,
    generatedLine([...new Set(wfs.all.map((w) => w.source))]),
    '## Reference workflows',
    figure(
      ref.title,
      ref.caption,
      [
        ...ref.families.flatMap((f) => [
          `- ${code(f.parent.id)} runs:`,
          ...f.children.map((c) => `  - ${code(c.workflow.id)} (${stepList(c.steps)})`),
        ]),
        `- Run on their own: ${ref.standalone.map((w) => code(w.id)).join(', ')}`,
      ].join('\n'),
    ),
    rows(wfs.core),
    '## Domain workflows',
    figure(
      dom.title,
      dom.caption,
      table(
        ['Domain', 'In a catalog', 'Proposed'],
        dom.groups.map((g) => [mdLink(g.domain, `/domains/${g.domain}/`), g.defined.map((w) => code(w.id)).join(', ') || 'none', g.proposed.map(code).join(', ') || 'none']),
      ),
    ),
    rows(wfs.domain),
  );
  return { title: 'Workflows', description, markdown };
}
