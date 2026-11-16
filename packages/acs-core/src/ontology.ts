/**
 * The capability ontology as TypeScript types, over the generated table
 * (`ontology.gen.ts`, from `schemas/capability_ontology.yaml`).
 */
import type { Json } from './canonical.js';
import type { EvidenceAnchor } from './evidence.js';
import {
  CAPABILITIES,
  ONTOLOGY_VERSION,
  REQUIRES,
  SPEC_VERSIONS,
  STANDARD_VERSION,
  TRUST_CLASSES,
} from './ontology.gen.js';

export { CAPABILITIES, ONTOLOGY_VERSION, REQUIRES, SPEC_VERSIONS, STANDARD_VERSION, TRUST_CLASSES };

export type CapabilityId = keyof typeof CAPABILITIES;
export type Layer = (typeof CAPABILITIES)[CapabilityId]['layer'];
export type Risk = 'low' | 'medium' | 'high';
export type TrustClass = (typeof TRUST_CLASSES)[number];

export interface SafetyFlags {
  risk: Risk;
  mutation: boolean;
  requires_checkpoint: boolean;
  requires_approval: boolean;
}

/**
 * Flags a tool or step may declare on top of its capability's. A
 * declaration can make a capability stricter, never weaker (STANDARD v1.2.0
 * §5.2.1), so the two `requires_*` flags can only be raised.
 */
export interface DeclaredFlags {
  risk?: Risk;
  mutation?: boolean;
  requires_checkpoint?: true;
  requires_approval?: true;
}

/**
 * The JSON types of the required output fields the ontology types the same
 * way wherever it declares them. Every other required field is any JSON.
 */
interface FieldTypes {
  /**
   * Evidence anchors (§6.5); a bare string or another object is a
   * deprecated legacy form, accepted until 2.0.
   */
  evidence_anchors: Array<EvidenceAnchor | string | Json>;
  /** A number from 0 to 1, which the wrapper checks at run time. */
  confidence: number;
}

/** The output a capability must return: the ontology's required output fields. */
export type CapabilityOutput<C extends CapabilityId> = {
  [K in (typeof CAPABILITIES)[C]['output_required'][number]]: K extends keyof FieldTypes ? FieldTypes[K] : Json;
} & { [key: string]: Json };

export function isCapability(id: string): id is CapabilityId {
  return Object.hasOwn(CAPABILITIES, id);
}

/** The capabilities that must have run before `capability` (`requires` edges). */
export function prerequisites(capability: CapabilityId): CapabilityId[] {
  return REQUIRES.filter(([, to]) => to === capability).map(([from]) => from);
}

/**
 * The prerequisites of a call that performs several capabilities
 * (STANDARD 1.2.0 §5.18.1): the union of each one's `requires` sources, in
 * the order of the edges.
 */
export function prerequisitesOf(capabilities: readonly CapabilityId[]): CapabilityId[] {
  const wanted = new Set<CapabilityId>(capabilities);
  const found: CapabilityId[] = [];
  for (const [from, to] of REQUIRES) {
    if (wanted.has(to) && !found.includes(from)) found.push(from);
  }
  return found;
}
