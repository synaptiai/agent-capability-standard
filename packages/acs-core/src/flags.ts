/**
 * Effective safety flags (STANDARD v1.2.0 §5.2.1).
 */
import { CAPABILITIES, type CapabilityId, type DeclaredFlags, type Risk, type SafetyFlags } from './ontology.js';

export const RISK_LEVELS: readonly Risk[] = ['low', 'medium', 'high'];

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

/** The stricter of two sets of flags, flag by flag: booleans OR-ed, the higher risk. */
export function joinFlags(a: SafetyFlags, b: SafetyFlags): SafetyFlags {
  return {
    risk: RISK_ORDER[a.risk] >= RISK_ORDER[b.risk] ? a.risk : b.risk,
    mutation: a.mutation || b.mutation,
    requires_checkpoint: a.requires_checkpoint || b.requires_checkpoint,
    requires_approval: a.requires_approval || b.requires_approval,
  };
}

/** No flag set: the identity of `joinFlags`, and a control-only tool's flags. */
export const NO_FLAGS: SafetyFlags = { risk: 'low', mutation: false, requires_checkpoint: false, requires_approval: false };

/**
 * The effective flags of a call that performs several capabilities
 * (STANDARD 1.2.0 §5.18.1, §5.18.3): the strictest across the ontology's
 * flags of every capability, combined with the declaration. A declared flag
 * weaker than that is reported (W602) and has no effect, except `mutation:
 * false` on a `mutation_overridable` capability that is the only one named.
 * With one capability this is `effectiveFlags`.
 */
export function effectiveFlagsOf(
  capabilities: readonly CapabilityId[],
  declared: DeclaredFlags | { risk?: Risk; mutation?: boolean; requires_checkpoint?: boolean; requires_approval?: boolean } = {},
): { flags: SafetyFlags; warnings: string[] } {
  if (capabilities.length === 0) throw new Error('effectiveFlagsOf needs at least one capability');
  let base = NO_FLAGS;
  for (const capability of capabilities) {
    const node = CAPABILITIES[capability];
    base = joinFlags(base, {
      risk: node.risk,
      mutation: node.mutation,
      requires_checkpoint: node.requires_checkpoint,
      requires_approval: node.requires_approval,
    });
  }
  const warnings: string[] = [];
  let risk: Risk = base.risk;
  if (declared.risk !== undefined) {
    if (RISK_ORDER[declared.risk] > RISK_ORDER[risk]) risk = declared.risk;
    else if (RISK_ORDER[declared.risk] < RISK_ORDER[risk]) {
      warnings.push(`W602: risk '${declared.risk}' is weaker than the ontology's '${base.risk}' and has no effect`);
    }
  }
  let mutation = base.mutation;
  if (declared.mutation === true) mutation = true;
  else if (declared.mutation === false && base.mutation) {
    const only = capabilities.length === 1 ? CAPABILITIES[capabilities[0]!] : undefined;
    if (only?.mutation_overridable) mutation = false;
    else warnings.push(`W602: mutation false is weaker than the ontology's value and has no effect`);
  }
  const flag = (name: 'requires_checkpoint' | 'requires_approval'): boolean => {
    if (declared[name] === false && base[name]) {
      warnings.push(`W602: ${name} false is weaker than the ontology's value and has no effect`);
    }
    return base[name] || declared[name] === true;
  };
  return {
    flags: { risk, mutation, requires_checkpoint: flag('requires_checkpoint'), requires_approval: flag('requires_approval') },
    warnings,
  };
}
