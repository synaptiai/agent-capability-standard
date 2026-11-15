/**
 * Effective safety flags (STANDARD v1.2.0 §5.2.1).
 */
import { CAPABILITIES, type CapabilityId, type DeclaredFlags, type Risk, type SafetyFlags } from './ontology.js';

const RISK_ORDER: Record<Risk, number> = { low: 0, medium: 1, high: 2 };

/**
 * A tool's or step's effective flags: the stricter of its declaration and
 * the ontology's. Booleans are OR-ed and `risk` is the higher level. A
 * weaker declaration has no effect and is reported (W602), except
 * `mutation: false` on a capability the ontology marks
 * `mutation_overridable`.
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
