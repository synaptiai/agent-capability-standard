// Text equivalents, in the Markdown copies, of the figures on the edge types
// page and the Standard page (visual spec 6.1) that show more than the table,
// list or fence they sit beside. Each block uses the same caption function as
// the page's <figcaption>.
import { loadCatalogSchema } from '../data/catalog-schema';
import { loadOntology, type EdgeTypeInfo } from '../data/ontology';
import { edgeTypesCaption, gateBranches, gateCaption, layerModelCaption, safetyCritical, safetyCriticalCaption, stepAnatomy, stepAnatomyCaption } from '../lib/spec-figures';
import {
  CHAIN_SECTIONS,
  chainCaption,
  changesCaption,
  EDGE_TYPES_SOURCE,
  edgeCardCaption,
  edgeChanges,
  edgeExample,
  edgeMatrixCaption,
  exampleChains,
  fieldsCaption,
  fieldTable,
  layerPairCounts,
  summaryCaption,
} from '../lib/edge-figures';
import { readRepoFile } from '../lib/repo';
import { edgeTypeCount, safetyRows } from '../lib/views';
import { cell, code, figure, table } from './md';
import { specEarlyBlocks, specLateBlocks, specTailBlocks } from './spec-figures';
import { slotBlocks } from './spec-slot-blocks';
import { SPEC_SLOTS } from '../lib/spec-slots';
import { loadVersions } from '../data/versions';

/**
 * The edge types page's figures, one block each in page order, under the
 * source text (visual spec 6.1): the seven type cards, the summary table with
 * its counts, the edge properties, the three example chains and the 1.1.0
 * changes. The two generated figures that follow ("Edges of each type, as
 * declared" and the matrix) are written by edgeTypesTwin where the page draws
 * them.
 */
export function edgeTypesFigureBlocks(): string[] {
  const o = loadOntology();
  const yes = (b: boolean) => (b ? 'Yes' : 'No');
  const unit = (t: EdgeTypeInfo, n: number) => (t.symmetric ? (n === 1 ? 'pair' : 'pairs') : n === 1 ? 'edge' : 'edges');
  const cards = o.edgeTypes.map((t) => {
    const ex = edgeExample(t);
    const n = edgeTypeCount(t);
    return figure(
      `${t.id}: ${ex.sentence}`,
      edgeCardCaption(t),
      table(['Example', 'From', 'To', 'Transitive', 'Symmetric', 'Count'], [[cell(ex.sentence), code(ex.from), code(ex.to), yes(t.transitive), yes(t.symmetric), `${n} ${unit(t, n)}`]]),
    );
  });
  const properties = fieldTable(readRepoFile(EDGE_TYPES_SOURCE), 'Edge Properties', EDGE_TYPES_SOURCE);
  const chains = CHAIN_SECTIONS.map((h) => {
    const cs = exampleChains(h);
    return figure(h, chainCaption(cs), cs.flatMap((c) => c.edges.map((e) => `- ${code(e.from)} ${code(e.type)} ${code(e.to)}`)).join('\n'));
  });
  const changes = edgeChanges();
  return [
    '## Figures on this page',
    ...cards,
    figure(
      'Edge type summary, with counts',
      summaryCaption(o),
      table(
        ['Type', 'Edges, a symmetric pair once', 'Transitive', 'Symmetric'],
        o.edgeTypes.map((t) => [code(t.id), String(edgeTypeCount(t)), yes(t.transitive), yes(t.symmetric)]),
      ),
    ),
    figure('Edge properties', fieldsCaption(properties, 'An edge has'), table(['Field', 'Type', 'Required', 'Description'], properties.map((p) => [code(p.name), cell(p.type), yes(p.required), cell(p.description)]))),
    ...chains,
    figure(
      'What changed in 1.1.0',
      changesCaption(changes),
      table(['Edge', '1.0.0', '1.1.0', 'Why'], changes.map((c) => [`${code(c.from)} → ${code(c.to)}`, c.before ? code(c.before) : 'new', c.after ? code(c.after) : 'removed', cell(c.why)])),
    ),
  ];
}

/** The all-edges matrix of the edge types page as layer-pair counts. */
export function edgeMatrixBlock(): string {
  const o = loadOntology();
  const { layers, counts } = layerPairCounts(o);
  return figure(
    'Every edge in the ontology, as a matrix',
    edgeMatrixCaption(o),
    `Edges between layers, rows by the \`from\` layer and columns by the \`to\` layer, a symmetric pair counted once. The per-type lists below give every edge.\n\n${table(
      ['From \\ to', ...layers],
      layers.map((l, i) => [l, ...counts[i]!.map(String)]),
    )}`,
  );
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
  const rich = [
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
  return slotBlocks(SPEC_SLOTS, loadVersions().standard.current.source, rich);
}
