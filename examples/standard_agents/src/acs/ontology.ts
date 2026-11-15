/**
 * Types and safety-flag rules over the generated ontology table.
 */
import type { Json } from './canonical.js';
import { CAPABILITIES, ONTOLOGY_VERSION, REQUIRES } from './ontology.gen.js';

export { CAPABILITIES, ONTOLOGY_VERSION, REQUIRES };

/** The version of the Agent Capability Standard this binding follows. */
export const STANDARD_VERSION = '1.1.0';

export type CapabilityId = keyof typeof CAPABILITIES;
export type Layer = (typeof CAPABILITIES)[CapabilityId]['layer'];
export type Risk = 'low' | 'medium' | 'high';

export interface SafetyFlags {
  risk: Risk;
  mutation: boolean;
  requires_checkpoint: boolean;
  requires_approval: boolean;
}

/**
 * Flags a tool may declare on top of its capability's. A tool can make a
 * capability stricter, never weaker (STANDARD v1.1.0 §5.2.1), so the two
 * `requires_*` flags can only be raised.
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
  evidence_anchors: Json[];
  /** A number from 0 to 1, which the wrapper checks at run time. */
  confidence: number;
}

/** The output a capability must return: the ontology's required output fields. */
export type CapabilityOutput<C extends CapabilityId> = {
  [K in (typeof CAPABILITIES)[C]['output_required'][number]]: K extends keyof FieldTypes ? FieldTypes[K] : Json;
} & { [key: string]: Json };

const RISK_ORDER: Record<Risk, number> = { low: 0, medium: 1, high: 2 };

export function isCapability(id: string): id is CapabilityId {
  return Object.hasOwn(CAPABILITIES, id);
}

/**
 * A tool's effective flags: the stricter of its declaration and the
 * ontology's. Booleans are OR-ed and `risk` is the higher level. A weaker
 * declaration has no effect and is reported (W602), except `mutation: false`
 * on a capability the ontology marks `mutation_overridable`.
 */
export function effectiveFlags(
  capability: CapabilityId,
  declared: DeclaredFlags = {},
): { flags: SafetyFlags; warnings: string[] } {
  const node = CAPABILITIES[capability];
  const warnings: string[] = [];

  let risk: Risk = node.risk;
  if (declared.risk !== undefined) {
    if (RISK_ORDER[declared.risk] > RISK_ORDER[risk]) risk = declared.risk;
    else if (RISK_ORDER[declared.risk] < RISK_ORDER[risk]) {
      warnings.push(`W602: risk '${declared.risk}' is weaker than the ontology's '${node.risk}' and has no effect`);
    }
  }

  let mutation: boolean = node.mutation;
  if (declared.mutation === true) mutation = true;
  else if (declared.mutation === false && node.mutation) {
    if (node.mutation_overridable) mutation = false;
    else warnings.push(`W602: mutation false is weaker than the ontology's value and has no effect`);
  }

  return {
    flags: {
      risk,
      mutation,
      requires_checkpoint: node.requires_checkpoint || declared.requires_checkpoint === true,
      requires_approval: node.requires_approval || declared.requires_approval === true,
    },
    warnings,
  };
}

/** The capabilities that must have run before `capability` (`requires` edges). */
export function prerequisites(capability: CapabilityId): CapabilityId[] {
  return REQUIRES.filter(([, to]) => to === capability).map(([from]) => from);
}
