// Text equivalents, in the Markdown copies, of the figures on the edge types
// page and the Standard page (visual spec 6.1) that show more than the table,
// list or fence they sit beside. Each block uses the same caption function as
// the page's <figcaption>.
import { loadOntology } from '../data/ontology';
import { edgeExample, edgeMatrixCaption, layerPairCounts } from '../lib/edge-figures';
import { edgeTypeCount } from '../lib/views';
import { cell, code, figure, table } from './md';

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
