// Markdown copies of the capability pages, the layer pages and the
// capabilities overview, from the same data the HTML pages use.
import { capabilitiesOfLayer, loadOntology, ONTOLOGY_SOURCE, RISKS } from '../data/ontology';
import { loadVersions } from '../data/versions';
import { capabilityUsage } from '../data/workflows';
import { readRepoFile } from '../lib/repo';
import { kebab } from '../lib/routes';
import {
  contractCaption,
  contractSummary,
  contractTitle,
  edgeRules,
  neighbourGroupLabel,
  outputFields,
  outputFieldsCaption,
  outputFieldsDiffer,
  procedureMap,
  procedureMapCaption,
  procedureMapIsFigure,
  procedureMapTitle,
  safetySequence,
  sequenceCaption,
  sequenceIsFigure,
  sequenceTitle,
  neighbourhoodCaption,
  neighbourhoodTitle,
  neighbours,
  stepWords,
  usageCaption,
  chainCaption,
  chainChecks,
  compositionChain,
  exampleFields,
  exampleFieldsCaption,
  exampleFieldsIsFigure,
  exampleFieldsSame,
  exampleFieldsTitle,
  skillTools,
  exampleWorkflows,
  exampleWorkflowsCaption,
  inputGroups,
  inputGroupsCaption,
  inputGroupsIsFigure,
  inputGroupsTitle,
  verificationMap,
  verificationMapCaption,
  verificationMapIsFigure,
  verificationMapTitle,
  skillToolsCaption,
  skillToolsTitle,
  TOOL_POWER_WORDS,
} from '../lib/capability-figures';
import { currentStandardText } from '../lib/spec-figures';
import { layerLinks, layerLinksCaption, stepsCaption, stepsPerLayer, stepsTitle, riskByLayer, riskByLayerCaption, usageMatrix, usageMatrixCaption } from '../lib/layer-figures';
import { contractRows, crossLayerEdges, EDGE_LABELS, edgeGroups, safetyRows, type SchemaRow } from '../lib/views';
import { loadWorkflows } from '../data/workflows';
import { blocks, cell, code, figure, generatedLine, markdownCopy, mdLink, table } from './md';
import type { Twin } from './types';

const capLink = (id: string) => mdLink(code(id), `/capabilities/${kebab(id)}/`);

function contractTable(rows: SchemaRow[]): string {
  if (rows.length === 0) return 'None.';
  return table(
    ['Field', 'Type', 'Required', 'Description'],
    rows.map((r) => [
      code(r.path),
      cell(r.type),
      r.required ? 'Yes' : 'No',
      cell([r.description, ...r.constraints].filter(Boolean).join(' ')),
    ]),
  );
}

export function capabilityTwin(capId: string, skillSource: string): Twin {
  const ontology = loadOntology();
  const cap = ontology.byId.get(capId);
  if (!cap) throw new Error(`twins: unknown capability ${capId}`);
  const groups = edgeGroups(cap, ontology);
  const usage = capabilityUsage(cap.id);
  const relationships =
    groups.length === 0
      ? 'No edge in the ontology starts or ends at this capability.'
      : groups
          .flatMap((g) =>
            g.symmetric
              ? [`- ${code(g.type)}: ${EDGE_LABELS[g.type].out} ${g.related.map(capLink).join(', ')}`]
              : [
                  ...(g.outgoing.length > 0 ? [`- ${code(g.type)}: ${EDGE_LABELS[g.type].out} ${g.outgoing.map(capLink).join(', ')}`] : []),
                  ...(g.incoming.length > 0 ? [`- ${code(g.type)}: ${EDGE_LABELS[g.type].in} ${g.incoming.map(capLink).join(', ')}`] : []),
                ],
          )
          .join('\n');
  const near = neighbours(cap, ontology);
  const neighbourhood =
    near.length === 0
      ? null
      : figure(
          neighbourhoodTitle(cap, near),
          neighbourhoodCaption(cap, near),
          table(
            ['Capability', 'Row', 'Relationships'],
            near.map((x) => [
              capLink(x.id),
              neighbourGroupLabel(x.group, cap.id),
              x.relations.map((r) => `${code(r.type)} (${{ in: 'into', out: 'out of', 'both-ways': 'both ways' }[r.direction]})`).join(', '),
            ]),
          ),
        );
  const summary = contractSummary(cap);
  const skillText = readRepoFile(skillSource);
  const fields = outputFields(cap, skillText, skillSource);
  // The page marks these in the skill's Field Definitions table; the copy keeps the source table as written, so it lists them here.
  const outputBlock = [
    outputFieldsCaption(cap, fields),
    table(
      ['Field of the skill\'s output', 'In the output contract'],
      [
        ...fields.skill.map((f) => [code(f.name), f.inContract ? (f.required ? 'Yes, required' : 'Yes, optional') : 'No, the skill\'s own']),
        ...fields.missing.map((m) => [code(m), 'Yes, but the skill leaves it out']),
      ],
    ),
  ].join('\n\n');
  const proc = procedureMap(skillText, skillSource);
  const procedureBlock = procedureMapIsFigure(proc)
    ? figure(
        procedureMapTitle(cap),
        procedureMapCaption(cap, proc),
        table(
          ['Step', 'Inputs it uses by name', 'Output fields it uses by name'],
          proc.steps.map((s) => [`${s.n}. ${s.title}`, s.reads.map(code).join(', '), s.writes.map(code).join(', ')]),
        ),
      )
    : null;
  const chain = compositionChain(skillText);
  const checks = chainChecks(cap, chain);
  const chainBlock =
    checks.length === 0
      ? null
      : figure(
          `The neighbours the skill lists for ${cap.id}, checked against the ontology and the catalogs`,
          chainCaption(cap, chain, checks),
          table(
            ['Listed as', 'Capability', 'Ontology edge', 'Next to it in a workflow'],
            checks.map((c) => [
              c.side === 'follows' ? 'commonly follows' : 'commonly precedes',
              capLink(c.id),
              c.edges.length === 0 ? 'none' : c.edges.map((e) => `${code(e.type)}${e.dir === 'into' ? ' (into it)' : ''}`).join(', '),
              c.adjacent === 0 ? 'never' : `${c.adjacent} times`,
            ]),
          ),
        );
  const allowed = /^allowed-tools:\s*(.+)$/m.exec(skillText)?.[1]?.trim();
  const tools = allowed ? skillTools(cap, allowed, skillSource) : null;
  const toolsBlock = tools
    ? figure(skillToolsTitle(cap), skillToolsCaption(cap, tools), table(['What they can do', 'Tools'], tools.groups.map((g) => [TOOL_POWER_WORDS[g.power], g.tools.map(code).join(', ') || 'none'])))
    : null;
  const ig = inputGroups(skillText, skillSource);
  const inputsBlock = inputGroupsIsFigure(ig)
    ? figure(inputGroupsTitle(cap), inputGroupsCaption(cap, ig), table(['Extension', 'Inputs'], ig.groups.map((g) => [g.extension ? code(g.extension) : 'none', g.inputs.map((x) => `${code(x.name)}${x.required ? ' (required)' : ''}`).join(', ')])))
    : null;
  const xw = exampleWorkflows(skillText);
  const xwBlock =
    xw.length === 0 || exampleFieldsIsFigure(exampleFields(skillText, skillSource)) && outputFieldsDiffer(fields)
      ? null
      : figure(`The catalog workflows the examples of the ${cap.id} skill run`, exampleWorkflowsCaption(cap, xw), table(['Workflow', 'Steps', 'Examples'], xw.map((r) => [mdLink(code(r.id), `/workflows/${loadWorkflows().byId.get(r.id)!.slug}/`), String(loadWorkflows().byId.get(r.id)!.steps.length), r.examples.join(', ')])));
  const vm = verificationMap(skillText, skillSource);
  const verificationBlock = verificationMapIsFigure(vm)
    ? figure(verificationMapTitle(cap), verificationMapCaption(cap, vm), table(['Check', 'Inputs it uses by name', 'Output fields it uses by name'], vm.checks.map((c) => [`${c.n}. ${cell(c.text)}`, c.reads.map(code).join(', '), c.writes.map(code).join(', ')])))
    : null;
  const ex = exampleFields(skillText, skillSource);
  const examplesBlock = exampleFieldsIsFigure(ex)
    ? figure(exampleFieldsTitle(cap), exampleFieldsCaption(cap, ex), table(['Example', 'Output fields it writes out'], ex.examples.map((e) => [cell(e.title), e.shows.map(code).join(', ') || 'none'])))
    : exampleFieldsSame(ex)
      ? exampleFieldsCaption(cap, ex)
      : null;
  const std = currentStandardText();
  const rules = edgeRules(std.text, std.source);
  const seq = safetySequence(cap, ontology);
  const seqRows = [
    ...seq.before.flatMap((x) => x.types.map((t) => [`Before ${cap.id}`, capLink(x.id), code(t), rules[t].level, rules[t].code])),
    ...(seq.approval ? [['Approval', 'Each use needs approval', code('requires_approval'), '', '']] : []),
    ...seq.after.flatMap((x) => x.types.map((t) => [`After ${cap.id}`, capLink(x.id), code(t), rules[t].level, rules[t].code])),
    ...seq.apart.map((id) => ['Never in the same parallel group', capLink(id), code('conflicts_with'), rules.conflicts_with.level, rules.conflicts_with.code]),
  ];
  const sequenceBlock = sequenceIsFigure(seq)
    ? figure(sequenceTitle(cap), sequenceCaption(cap, seq, rules), table(['Where', 'Capability', 'Rule', 'Enforcement', 'Diagnostic'], seqRows))
    : sequenceCaption(cap, seq, rules);
  const usedList = usage.map((u) => `- ${mdLink(code(u.workflowId), `/workflows/${u.slug}/`)}: ${stepWords(u.steps)}`).join('\n');
  const used = usage.length === 0 ? usageCaption(cap, usage) : figure(`${cap.id} in workflows`, usageCaption(cap, usage), usedList);
  const markdown = blocks(
    `# ${cap.id}`,
    cap.description,
    generatedLine([ONTOLOGY_SOURCE, skillSource]) + ` Ontology version ${loadVersions().ontology}.`,
    `Layer: ${mdLink(cap.layer, `/layers/${ontology.layers.find((l) => l.id === cap.layer)!.slug}/`)}`,
    '## Safety',
    table(['Property', 'Value'], safetyRows(cap).map((r) => [r.term, r.value])),
    sequenceBlock,
    '## Relationships',
    neighbourhood,
    relationships,
    '## Contract',
    `**Figure: ${contractTitle(cap, summary)}.** ${contractCaption(cap, summary)} The tables below list every field.`,
    '### Inputs',
    contractTable(contractRows(cap.input_schema)),
    '### Outputs',
    contractTable(contractRows(cap.output_schema)),
    outputBlock,
    '## Used in workflows',
    used,
    '## Claude Code skill',
    toolsBlock,
    inputsBlock,
    procedureBlock,
    examplesBlock,
    xwBlock,
    verificationBlock,
    chainBlock,
    markdownCopy(skillSource, skillText, { shiftHeadings: 1 }),
  );
  return { title: cap.id, description: cap.description, markdown };
}

export function layerTwin(layerId: string): Twin {
  const ontology = loadOntology();
  const layer = ontology.layers.find((l) => l.id === layerId);
  if (!layer) throw new Error(`twins: unknown layer ${layerId}`);
  const caps = capabilitiesOfLayer(ontology, layer.id);
  const sentence = `${layer.description.replace(/\.$/, '')}.`;
  const crossing = crossLayerEdges(layer.id, ontology);
  const markdown = blocks(
    `# ${layer.id}`,
    sentence,
    generatedLine([ONTOLOGY_SOURCE]),
    `Layer ${layer.order + 1} of ${ontology.layers.length}. Cognitive mapping: ${layer.cognitive_mapping}.`,
    '## Capabilities',
    table(
      ['Capability', 'Description', 'Risk', 'Mutates state'],
      caps.map((c) => [capLink(c.id), cell(c.description), c.risk, c.mutation ? 'Yes' : 'No']),
    ),
    '## Edges to other layers',
    crossing.length === 0
      ? 'No edge connects this layer to another layer.'
      : figure(
          `Edges between ${layer.id} and other layers`,
          layerLinksCaption(layer.id, layerLinks(layer.id, ontology)),
          table(
            ['Direction', 'Other layer', 'Edges', 'Types'],
            (['into', 'out'] as const).flatMap((d) =>
              layerLinks(layer.id, ontology)[d].map((l) => [d === 'into' ? `Into ${layer.id}` : `Out of ${layer.id}`, l.layer, String(l.edges.length), l.types.map(code).join(', ')]),
            ),
          ),
        ),
    crossing.length === 0
      ? null
      : crossing
          .map((g) => [`### ${g.type}`, ...g.edges.map((e) => `- ${capLink(e.from)} to ${capLink(e.to)} (${e.otherLayer})`)].join('\n\n'))
          .join('\n\n'),
    '## Workflows that use this layer',
    figure(stepsTitle(layer.id, stepsPerLayer()), stepsCaption(layer.id, stepsPerLayer()), table(['Layer', 'Steps'], stepsPerLayer().map((r) => [r.layer, String(r.steps)]))),
    (() => {
      const m = usageMatrix(layer.id);
      if (m.rows.length === 0) return usageMatrixCaption(layer.id, m);
      return figure(
        `Workflows that use ${layer.id} capabilities`,
        usageMatrixCaption(layer.id, m),
        table(['Workflow', ...m.capabilities.map(code)], m.rows.map((r) => [mdLink(code(r.workflow.id), `/workflows/${r.workflow.slug}/`), ...r.counts.map((c) => (c === 0 ? '' : String(c)))])),
      );
    })(),
  );
  return { title: layer.id, description: `${sentence} ${layer.capabilities.length} capabilities.`, markdown };
}

export function capabilitiesIndexTwin(): Twin {
  const ontology = loadOntology();
  const n = ontology.capabilities.length;
  const description = `The ${n} capabilities of the ontology in ${ontology.layers.length} layers, with their risk levels and safety flags.`;
  const markdown = blocks(
    '# Capabilities',
    `The ontology defines ${n} atomic capabilities in ${ontology.layers.length} layers. Each capability has a typed input and output contract, a risk level and safety flags. Workflows compose them; see ${mdLink('Workflows', '/workflows/')}.`,
    generatedLine([ONTOLOGY_SOURCE]),
    ...ontology.layers.map((l) =>
      blocks(
        `## ${mdLink(l.id, `/layers/${l.slug}/`)}`,
        table(
          ['Capability', 'Description', 'Risk'],
          capabilitiesOfLayer(ontology, l.id).map((c) => [capLink(c.id), cell(c.description), c.risk]),
        ),
      ),
    ),
    '## Risk by layer',
    (() => {
      const m = riskByLayer(ontology);
      return figure('Capabilities by risk level and layer', riskByLayerCaption(m), table(['Risk', ...m.layers], m.rows.map((r) => [r.risk, ...r.counts.map((c) => (c === 0 ? '' : String(c)))])));
    })(),
    table(['Risk', 'Capabilities'], RISKS.map((r) => [r, String(ontology.capabilities.filter((c) => c.risk === r).length)])),
    `${ontology.capabilities.filter((c) => c.mutation).length} of the ${n} capabilities change state.`,
    table(['Edge type', 'Edges'], ontology.edgeTypes.map((t) => [code(t.id), String(t.edges.length)])),
  );
  return { title: 'Capabilities', description, markdown };
}

