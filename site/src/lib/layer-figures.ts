// What the layer page's figures show (visual spec 3.2): the cross-layer edge
// map (F-L2) and the steps-per-layer bars (F-L4), with their captions. The
// page and its Markdown copy call the same functions.
import { EDGE_TYPES, loadOntology, RISKS, type EdgeType, type Ontology, type Risk } from '../data/ontology';
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

export interface LayerLinks {
  into: LayerLink[];
  out: LayerLink[];
  /** Symmetric edges (conflicts_with, alternative_to), which run both ways: the capability page's "Either way". */
  either: LayerLink[];
}

/** Rows of LayerLinks in the order the figure and the copy list them. */
export const LAYER_LINK_SIDES = ['into', 'out', 'either'] as const;

/**
 * Edges between a layer and each other layer, split by direction: "into"
 * holds edges whose source is outside the layer, "out" edges whose source is
 * inside it, and "either" the symmetric edges, which have no direction (each
 * pair once, as crossLayerEdges() lists it). Rows are in layer order.
 */
export function layerLinks(layerId: string, ontology: Ontology = loadOntology()): LayerLinks {
  const groups = crossLayerEdges(layerId, ontology);
  const all = groups.flatMap((g) => g.edges.map((e) => ({ ...e, type: g.type, symmetric: g.symmetric })));
  const side = (keep: (e: (typeof all)[number]) => boolean): LayerLink[] =>
    ontology.layers
      .map((l) => {
        const edges = all.filter((e) => keep(e) && e.otherLayer === l.id).map(({ symmetric: _s, ...e }) => e);
        return { layer: l.id, types: EDGE_TYPES.filter((t) => edges.some((e) => e.type === t)), edges };
      })
      .filter((x) => x.edges.length > 0);
  return { into: side((e) => !e.symmetric && e.direction === 'in'), out: side((e) => !e.symmetric && e.direction === 'out'), either: side((e) => e.symmetric) };
}

/** True when every row has the same number of edges, so bars would all be one length. */
export function layerLinksEqual(links: LayerLinks): boolean {
  const counts = new Set(LAYER_LINK_SIDES.flatMap((k) => links[k].map((l) => l.edges.length)));
  return counts.size <= 1;
}

/** F-L2's caption. */
export function layerLinksCaption(layerId: string, links: LayerLinks): string {
  const n = (ls: LayerLink[]) => ls.reduce((k, l) => k + l.edges.length, 0);
  const parts = [
    ...(links.into.length > 0 ? [`${plural(n(links.into), 'edge comes', 'edges come')} into ${layerId} from ${plural(links.into.length, 'other layer', 'other layers')}`] : []),
    ...(links.out.length > 0 ? [`${plural(n(links.out), 'edge goes', 'edges go')} out of ${layerId} to ${plural(links.out.length, 'other layer', 'other layers')}`] : []),
    ...(links.either.length > 0 ? [`${plural(n(links.either), 'edge runs', 'edges run')} both ways with ${plural(links.either.length, 'other layer', 'other layers')}`] : []),
  ];
  const text = parts.length === 0 ? `No edge joins ${layerId} to another layer` : parts.length === 1 ? parts[0]! : `${parts.slice(0, -1).join(', ')} and ${parts.at(-1)}`;
  const first = links.into[0] ?? links.out[0] ?? links.either[0];
  const same = first && layerLinksEqual(links) ? ` Every row has ${plural(first.edges.length, 'edge', 'edges')}, so the figure prints the count and draws no bars.` : '';
  return `${text}.${same}`;
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
  // A share that rounds to 0 but is not 0 prints as "<1%".
  const share = pct === 0 && mine > 0 ? '<1' : String(pct);
  return `${mine} of the ${total} steps in all workflows run ${layerId} capabilities (${share}%), ${rank === 1 ? 'the most' : `the ${ordinal(rank)} most`} of the ${rows.length} layers.`;
}

function ordinal(n: number): string {
  const s = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th';
  return `${n}${s}`;
}

export interface UsageMatrix {
  /** The layer's capabilities, in periodic-table order: the columns. */
  capabilities: string[];
  /** One row per workflow that runs a capability of the layer, in catalog order. */
  rows: { workflow: Workflow; counts: number[] }[];
  /** The largest cell, for the heat scale. */
  max: number;
}

/** F-L3: steps per workflow and capability of the layer. */
export function usageMatrix(layerId: string, workflows: Workflow[] = loadWorkflows().all, ontology: Ontology = loadOntology()): UsageMatrix {
  const capabilities = ontology.layers.find((l) => l.id === layerId)?.capabilities ?? [];
  const rows = workflows
    .map((workflow) => ({ workflow, counts: capabilities.map((c) => workflow.steps.filter((s) => s.capability === c).length) }))
    .filter((r) => r.counts.some((n) => n > 0));
  return { capabilities, rows, max: Math.max(0, ...rows.flatMap((r) => r.counts)) };
}

/** F-L3's caption. */
export function usageMatrixCaption(layerId: string, m: UsageMatrix): string {
  if (m.rows.length === 0) return `No reference or domain workflow uses a capability of ${layerId}.`;
  const steps = m.rows.reduce((k, r) => k + r.counts.reduce((a, b) => a + b, 0), 0);
  const per = m.capabilities.map((c, i) => ({ c, steps: m.rows.reduce((k, r) => k + r.counts[i]!, 0), workflows: m.rows.filter((r) => r.counts[i]! > 0).length }));
  const top = [...per].sort((a, b) => b.workflows - a.workflows || b.steps - a.steps)[0]!;
  const unused = per.filter((p) => p.steps === 0).map((p) => p.c);
  const tail = unused.length === 0 ? '' : `; ${unused.length === 1 ? unused[0] : `${unused.slice(0, -1).join(', ')} and ${unused.at(-1)}`} ${unused.length === 1 ? 'is' : 'are'} in none`;
  return `${plural(m.rows.length, 'workflow runs', 'workflows run')} ${layerId} capabilities in ${plural(steps, 'step', 'steps')}; ${top.c} is in the most workflows, ${top.workflows}${tail}.`;
}

export interface RiskByLayer {
  layers: string[];
  /** One row per risk level, low to high; counts in layer order. */
  rows: { risk: Risk; counts: number[] }[];
  max: number;
}

/** F-CI1: capabilities per risk level and layer. */
export function riskByLayer(ontology: Ontology = loadOntology()): RiskByLayer {
  const layers = ontology.layers.map((l) => l.id);
  const rows = RISKS.map((risk) => ({ risk, counts: layers.map((l) => ontology.capabilities.filter((c) => c.layer === l && c.risk === risk).length) }));
  return { layers, rows, max: Math.max(0, ...rows.flatMap((r) => r.counts)) };
}

/** F-CI1's caption: where the medium- and high-risk capabilities sit. */
export function riskByLayerCaption(m: RiskByLayer): string {
  const where = (risk: Risk) => {
    const row = m.rows.find((r) => r.risk === risk)!;
    const total = row.counts.reduce((a, b) => a + b, 0);
    const at = m.layers.map((l, i) => ({ l, n: row.counts[i]! })).filter((x) => x.n > 0).map((x) => `${x.n} in ${x.l}`);
    const list = at.length <= 1 ? at.join('') : `${at.slice(0, -1).join(', ')} and ${at.at(-1)}`;
    return total === 0 ? `no ${risk}-risk capability` : `${plural(total, `${risk}-risk capability`, `${risk}-risk capabilities`)} (${list})`;
  };
  const low = m.rows.find((r) => r.risk === 'low')!.counts.reduce((a, b) => a + b, 0);
  return `${low} of the ${m.rows.reduce((k, r) => k + r.counts.reduce((a, b) => a + b, 0), 0)} capabilities are low risk; there are ${where('high')} and ${where('medium')}.`;
}
