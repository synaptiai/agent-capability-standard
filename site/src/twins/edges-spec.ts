// Text equivalents, in the Markdown copies, of the figures on the edge types
// page and the Standard page (visual spec 6.1) that show more than the table,
// list or fence they sit beside. Each block uses the same caption function as
// the page's <figcaption>.
import { loadCatalogSchema } from '../data/catalog-schema';
import { loadOntology } from '../data/ontology';
import { edgeTypesCaption, gateBranches, gateCaption, layerModelCaption, safetyCritical, safetyCriticalCaption, stepAnatomy, stepAnatomyCaption } from '../lib/spec-figures';
import { edgeExample, edgeMatrixCaption, layerPairCounts } from '../lib/edge-figures';
import { edgeTypeCount, safetyRows } from '../lib/views';
import { cell, code, figure, table } from './md';
import { specEarlyBlocks, specLateBlocks, specTailBlocks } from './spec-figures';

/** The edge types page: each type card's example sentence, and the matrix as layer-pair counts. */
export function edgeTypesFigureBlocks(): string[] {
  const o = loadOntology();
  const { layers, counts } = layerPairCounts(o);
  return [
    '## Figures on this page',
    figure(
      'Edge type cards',
      `Each edge type's card draws the first edge of that type in the ontology.`,
      table(
        ['Type', 'Example', 'Transitive', 'Symmetric', 'Count'],
        o.edgeTypes.map((t) => {
          const n = edgeTypeCount(t);
          const unit = t.symmetric ? (n === 1 ? 'pair' : 'pairs') : n === 1 ? 'edge' : 'edges';
          return [code(t.id), cell(edgeExample(t).sentence), t.transitive ? 'Yes' : 'No', t.symmetric ? 'Yes' : 'No', `${n} ${unit}`];
        }),
      ),
    ),
    figure(
      'Every edge in the ontology, as a matrix',
      edgeMatrixCaption(o),
      `Edges between layers, rows by the \`from\` layer and columns by the \`to\` layer, a symmetric pair counted once. The per-type lists under "All edges" give every edge.\n\n${table(
        ['From \\ to', ...layers],
        layers.map((l, i) => [l, ...counts[i]!.map(String)]),
      )}`,
    ),
  ];
}

/**
 * The current Standard: the figures of chapters 4 and 5 that show ontology
 * or schema data the section's own table does not hold (visual spec 3.9,
 * "twin block"). Figures that redraw their section's table, fence or
 * sentence need no block: the source is their text equivalent.
 */
export function specFigureBlocks(): string[] {
  const o = loadOntology();
  const schema = loadCatalogSchema();
  const yes = (b: boolean) => (b ? 'Yes' : 'No');
  return [
    '## Figures on this page',
    ...specEarlyBlocks().slice(0, 2),
    figure(
      'Layer model, from §4.2',
      layerModelCaption(o),
      table(['Layer', 'Capabilities', 'Cognitive mapping'], o.layers.map((l) => [l.id, l.capabilities.map(code).join(', '), cell(l.cognitive_mapping)])),
    ),
    figure(
      'Edge types, from §4.3',
      edgeTypesCaption(o),
      table(
        ['Type', 'Example', 'Transitive', 'Symmetric', 'Count'],
        o.edgeTypes.map((t) => {
          const n = edgeTypeCount(t);
          return [code(t.id), cell(edgeExample(t).sentence), yes(t.transitive), yes(t.symmetric), `${n} ${t.symmetric ? 'pairs' : 'edges'}`];
        }),
      ),
    ),
    figure(
      'Safety-critical capabilities, from §4.4',
      safetyCriticalCaption(o),
      table(
        ['Capability', ...safetyRows(safetyCritical(o)[0]!).map((r) => r.term)],
        safetyCritical(o).map((c) => [code(c.id), ...safetyRows(c).map((r) => cell(r.value))]),
      ),
    ),
    figure(
      'Step anatomy, from §5.2',
      stepAnatomyCaption(schema),
      table(
        ['Group', 'Field', 'Type', 'Required'],
        stepAnatomy(schema).flatMap((g) => g.slots.map((s) => [g.title, code(s.name), code(s.type), yes(s.required)])),
      ),
    ),
    ...specEarlyBlocks().slice(2),
    figure(
      'Gate outcomes, from §5.6',
      gateCaption(schema),
      table(['Phase', 'Actions'], gateBranches(schema).map((b) => [b.phase, b.actions.map(code).join(', ')])),
    ),
    ...specLateBlocks(),
    ...specTailBlocks(),
  ];
}
