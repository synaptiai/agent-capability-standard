// Markdown copies of the capability pages, the layer pages and the
// capabilities overview, from the same data the HTML pages use.
import { capabilitiesOfLayer, loadOntology, ONTOLOGY_SOURCE, RISKS, type Capability } from '../data/ontology';
import { loadVersions } from '../data/versions';
import { capabilityUsage } from '../data/workflows';
import { readRepoFile } from '../lib/repo';
import { kebab } from '../lib/routes';
import {
  contractCaption,
  contractSummary,
  contractTitle,
  neighbourGroupLabel,
  neighbourhoodCaption,
  neighbourhoodTitle,
  neighbours,
  stepWords,
  usageCaption,
} from '../lib/capability-figures';
import { layerLinks, layerLinksCaption, stepsCaption, stepsPerLayer, stepsTitle } from '../lib/layer-figures';
import { contractRows, crossLayerEdges, EDGE_LABELS, edgeGroups, layerUsage, safetyRows, type SchemaRow } from '../lib/views';
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

export function flagLines(cap: Capability): string[] {
  return [
    `- Layer: ${mdLink(cap.layer, `/layers/${loadOntology().layers.find((l) => l.id === cap.layer)!.slug}/`)}`,
    `- Risk: ${cap.risk}`,
    `- Mutates state: ${cap.mutation ? 'yes' : 'no'}`,
    `- Checkpoint required: ${cap.requires_checkpoint ? 'yes' : 'no'}`,
    `- Approval required: ${cap.requires_approval ? 'yes' : 'no'}`,
    ...(cap.mutation_overridable ? ['- A step may declare `mutation: false`'] : []),
  ];
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
  const usedList = usage.map((u) => `- ${mdLink(code(u.workflowId), `/workflows/${u.slug}/`)}: ${stepWords(u.steps)}`).join('\n');
  const used = usage.length === 0 ? usageCaption(cap, usage) : figure(`${cap.id} in workflows`, usageCaption(cap, usage), usedList);
  const markdown = blocks(
    `# ${cap.id}`,
    cap.description,
    generatedLine([ONTOLOGY_SOURCE, skillSource]) + ` Ontology version ${loadVersions().ontology}.`,
    flagLines(cap).join('\n'),
    '## Safety',
    table(['Property', 'Value'], safetyRows(cap).map((r) => [r.term, r.value])),
    '## Relationships',
    neighbourhood,
    relationships,
    '## Contract',
    `**Figure: ${contractTitle(cap, summary)}.** ${contractCaption(cap, summary)} The tables below list every field.`,
    '### Inputs',
    contractTable(contractRows(cap.input_schema)),
    '### Outputs',
    contractTable(contractRows(cap.output_schema)),
    '## Used in workflows',
    used,
    '## Claude Code skill',
    markdownCopy(skillSource, readRepoFile(skillSource), { shiftHeadings: 1 }),
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
  const usage = layerUsage(layer.id);
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
    usage.length === 0
      ? 'No workflow uses a capability of this layer.'
      : usage
          .map((u) => `- ${mdLink(code(u.workflow.id), `/workflows/${u.workflow.slug}/`)}: ${u.capabilities.map(code).join(', ')}`)
          .join('\n'),
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
    '## Counts',
    table(['Risk', 'Capabilities'], RISKS.map((r) => [r, String(ontology.capabilities.filter((c) => c.risk === r).length)])),
    `${ontology.capabilities.filter((c) => c.mutation).length} of the ${n} capabilities change state.`,
    table(['Edge type', 'Edges'], ontology.edgeTypes.map((t) => [code(t.id), String(t.edges.length)])),
  );
  return { title: 'Capabilities', description, markdown };
}

