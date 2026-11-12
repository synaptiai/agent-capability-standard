// Marks the boxes of a diagram that name a capability, so the drawing can
// give them the capability's symbol on its layer tint (visual spec 1.2: a
// layer colour always comes with a symbol or name). A label names a
// capability when its first word, alone or before "(", is an ontology id:
// "checkpoint" and "rollback(recovery_point)" do, "verify step" does not.
import { loadOntology } from '../../data/ontology';
import { capabilitySymbol } from '../views';
import type { Diagram } from './parse';

export function capabilityOfLabel(label: string): string | null {
  const m = /^([a-z][a-z_]*)(?:\(|$)/.exec(label.trim());
  if (!m) return null;
  return loadOntology().byId.has(m[1]!) ? m[1]! : null;
}

export function markCapabilities(d: Diagram): Diagram {
  const o = loadOntology();
  for (const n of d.nodes) {
    const id = capabilityOfLabel(n.label);
    if (id) n.capability = { id, layer: o.byId.get(id)!.layer, symbol: capabilitySymbol(id) };
  }
  return d;
}
