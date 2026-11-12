// What the layer page's figures show (visual spec 3.2): the cross-layer edge
// map (F-L2) and the steps-per-layer bars (F-L4), with their captions. The
// page and its Markdown copy call the same functions.
import { EDGE_TYPES, loadOntology, type EdgeType, type Ontology } from '../data/ontology';
import { loadWorkflows, type Workflow } from '../data/workflows';
import { crossLayerEdges, type CrossLayerEdge } from './views';

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

export interface LayerLink {
  /** The layer at the other end. */
  layer: string;
  /** Edge types present, in the ontology's order. */
  types: EdgeType[];
  edges: (CrossLayerEdge & { type: EdgeType })[];
}

/**
 * Edges between a layer and each other layer, split by direction: "into"
 * holds edges whose source is outside the layer, "out" edges whose source is
 * inside it. A symmetric edge is counted once, on the side it is first
 * declared from, as crossLayerEdges() lists it. Rows are in layer order.
 */
export function layerLinks(layerId: string, ontology: Ontology = loadOntology()): { into: LayerLink[]; out: LayerLink[] } {
  const all = crossLayerEdges(layerId, ontology).flatMap((g) => g.edges.map((e) => ({ ...e, type: g.type })));
  const side = (dir: 'in' | 'out'): LayerLink[] =>
    ontology.layers
      .map((l) => {
        const edges = all.filter((e) => e.direction === dir && e.otherLayer === l.id);
        return { layer: l.id, types: EDGE_TYPES.filter((t) => edges.some((e) => e.type === t)), edges };
      })
      .filter((x) => x.edges.length > 0);
  return { into: side('in'), out: side('out') };
}

/** F-L2's caption. */
export function layerLinksCaption(layerId: string, links: { into: LayerLink[]; out: LayerLink[] }): string {
  const n = (ls: LayerLink[]) => ls.reduce((k, l) => k + l.edges.length, 0);
  const into = n(links.into);
  const out = n(links.out);
  return `${plural(into, 'edge comes', 'edges come')} into ${layerId} from ${plural(links.into.length, 'other layer', 'other layers')}, and ${plural(out, 'edge goes', 'edges go')} out of it to ${plural(links.out.length, 'layer', 'layers')}.`;
}

export interface LayerSteps {
  layer: string;
  steps: number;
}

/** Workflow steps per layer across every workflow, highest first; ties keep layer order. */
export function stepsPerLayer(workflows: Workflow[] = loadWorkflows().all, ontology: Ontology = loadOntology()): LayerSteps[] {
  return ontology.layers
    .map((l) => ({ layer: l.id, steps: workflows.reduce((k, w) => k + w.steps.filter((s) => s.layer === l.id).length, 0) }))
    .sort((a, b) => b.steps - a.steps);
}

/** F-L4's accessible name: "Workflow steps per layer; {LAYER}: {n} of {total}". */
export function stepsTitle(layerId: string, rows: LayerSteps[]): string {
  const total = rows.reduce((k, r) => k + r.steps, 0);
  return `Workflow steps per layer; ${layerId}: ${rows.find((r) => r.layer === layerId)?.steps ?? 0} of ${total}`;
}

/** F-L4's caption. */
export function stepsCaption(layerId: string, rows: LayerSteps[]): string {
  const total = rows.reduce((k, r) => k + r.steps, 0);
  const rank = rows.findIndex((r) => r.layer === layerId) + 1;
  const mine = rows[rank - 1]?.steps ?? 0;
  const pct = total === 0 ? 0 : Math.round((mine / total) * 100);
  return `${mine} of the ${total} steps in all workflows run ${layerId} capabilities (${pct}%), ${rank === 1 ? 'the most' : `the ${ordinal(rank)} most`} of the ${rows.length} layers.`;
}

function ordinal(n: number): string {
  const s = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th';
  return `${n}${s}`;
}
