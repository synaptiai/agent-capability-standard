// Effective safety flags of a workflow step, per Standard 1.1.0 §5.2.1:
// - risk, mutation, requires_checkpoint and requires_approval default to the
//   capability's ontology values;
// - the effective value is the stricter of the step's declaration and the
//   ontology (booleans are OR-ed, risk is the higher level);
// - a weaker declaration has no effect and is a W602 downgrade, except
//   `mutation: false` on a `mutation_overridable` capability, which is honoured.
// A step whose effective requires_checkpoint is true needs a checkpoint before
// it (F501), reported as V102 where the ontology's `requires` edge from
// `checkpoint` already demands one (§4.3, §4.4).
import type { Capability, Risk } from '../data/ontology';

export type SafetyFlag = 'risk' | 'mutation' | 'requires_checkpoint' | 'requires_approval';

export interface EffectiveFlags {
  risk: Risk;
  mutation: boolean;
  requires_checkpoint: boolean;
  requires_approval: boolean;
  /** Flags the step declares weaker than the ontology (each one is W602). */
  downgrades: SafetyFlag[];
  /** Whether a checkpoint step must run before this step, and why. */
  checkpoint: {
    needed: boolean;
    via: 'requires-edge' | 'flag' | null;
    /** The diagnostic a validator reports when no checkpoint runs before it. */
    code: 'V102' | 'F501' | null;
  };
}

const RISK_ORDER: Record<Risk, number> = { low: 0, medium: 1, high: 2 };

function declaredRisk(v: unknown): Risk | undefined {
  return typeof v === 'string' && v in RISK_ORDER ? (v as Risk) : undefined;
}

function declaredBool(v: unknown): boolean | undefined {
  return typeof v === 'boolean' ? v : undefined;
}

/**
 * Whether a capability needs a checkpoint before it (Standard §4.4): its
 * `requires_checkpoint` flag is set or a `requires` edge runs to it from
 * `checkpoint` (rollback has only the edge).
 */
export function capabilityNeedsCheckpoint(cap: Capability): boolean {
  return cap.requires_checkpoint || cap.edgesIn.requires.includes('checkpoint');
}

export function effectiveFlags(step: Record<string, unknown>, cap: Capability): EffectiveFlags {
  const downgrades: SafetyFlag[] = [];

  const stepMutation = declaredBool(step.mutation);
  let mutation: boolean;
  if (cap.mutation && cap.mutation_overridable && stepMutation === false) {
    mutation = false;
  } else {
    mutation = cap.mutation || stepMutation === true;
    if (cap.mutation && stepMutation === false) downgrades.push('mutation');
  }

  const stepCheckpoint = declaredBool(step.requires_checkpoint);
  const requires_checkpoint = cap.requires_checkpoint || stepCheckpoint === true;
  if (cap.requires_checkpoint && stepCheckpoint === false) downgrades.push('requires_checkpoint');

  const stepApproval = declaredBool(step.requires_approval);
  const requires_approval = cap.requires_approval || stepApproval === true;
  if (cap.requires_approval && stepApproval === false) downgrades.push('requires_approval');

  // Reported last, in the order the reference validator reports W602.
  const stepRisk = declaredRisk(step.risk);
  let risk = cap.risk;
  if (stepRisk !== undefined) {
    if (RISK_ORDER[stepRisk] > RISK_ORDER[cap.risk]) risk = stepRisk;
    else if (RISK_ORDER[stepRisk] < RISK_ORDER[cap.risk]) downgrades.push('risk');
  }

  const viaEdge = cap.edgesIn.requires.includes('checkpoint');
  const checkpoint: EffectiveFlags['checkpoint'] = viaEdge
    ? { needed: true, via: 'requires-edge', code: 'V102' }
    : requires_checkpoint
      ? { needed: true, via: 'flag', code: 'F501' }
      : { needed: false, via: null, code: null };

  return { risk, mutation, requires_checkpoint, requires_approval, downgrades, checkpoint };
}
