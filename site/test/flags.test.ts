// Expected values are read by hand from the YAML and the Standard, not from
// the implementation:
// - ontology flags: schemas/capability_ontology.yaml nodes `execute`, `mutate`,
//   `rollback`, `checkpoint`, `audit`, `persist`, `observe`, and the three
//   `requires` edges from `checkpoint` (to mutate, send, rollback);
// - step declarations: schemas/workflow_catalog.yaml, workflow
//   `debug_code_change` (steps 7 checkpoint, 8 execute, 10 rollback, 11 audit)
//   and `clarify_intent` (its audit step);
// - the rule: Standard 1.1.0 §5.2.1 and §4.4.
import { describe, expect, it } from 'vitest';
import { loadOntology } from '../src/data/ontology';
import { loadWorkflows, type Step } from '../src/data/workflows';
import { effectiveFlags } from '../src/lib/flags';

const ontology = loadOntology();
const cap = (id: string) => {
  const c = ontology.byId.get(id);
  if (!c) throw new Error(`no capability ${id}`);
  return c;
};
const step = (wf: string, capability: string): Step => {
  const s = loadWorkflows().byId.get(wf)?.steps.find((x) => x.capability === capability);
  if (!s) throw new Error(`no ${capability} step in ${wf}`);
  return s;
};

describe('effective flags on catalog steps', () => {
  it('debug_code_change execute: the step raises every flag, so the step values apply', () => {
    // Ontology execute: risk medium, mutation false, requires_approval true, no requires_checkpoint.
    // Step 8 declares risk high, mutation true, requires_checkpoint true, requires_approval true.
    const s = step('debug_code_change', 'execute');
    expect(s.index).toBe(8);
    expect(s.effective).toEqual({
      risk: 'high',
      mutation: true,
      requires_checkpoint: true,
      requires_approval: true,
      downgrades: [],
      // No `requires` edge reaches execute, so a missing checkpoint is F501 (§5.2.1).
      checkpoint: { needed: true, via: 'flag', code: 'F501' },
    });
  });

  it('debug_code_change checkpoint: a higher declared risk takes effect', () => {
    // Ontology checkpoint: risk low, mutation true. Step 7 declares risk medium and false for the rest.
    const s = step('debug_code_change', 'checkpoint');
    expect(s.index).toBe(7);
    expect(s.effective).toEqual({
      risk: 'medium',
      mutation: true,
      requires_checkpoint: false,
      requires_approval: false,
      downgrades: [],
      checkpoint: { needed: false, via: null, code: null },
    });
  });

  it('debug_code_change rollback: needs a checkpoint through its requires edge, not its flag', () => {
    // Ontology rollback: risk medium, mutation true, no requires_checkpoint flag;
    // edge checkpoint -requires-> rollback. Step 10 declares requires_checkpoint false,
    // which is not a downgrade because the ontology flag is false too.
    const s = step('debug_code_change', 'rollback');
    expect(s.index).toBe(10);
    expect(s.effective.requires_checkpoint).toBe(false);
    expect(s.effective.downgrades).toEqual([]);
    expect(s.effective.checkpoint).toEqual({ needed: true, via: 'requires-edge', code: 'V102' });
  });

  it('clarify_intent audit: mutation false is honoured because audit is mutation_overridable', () => {
    // Ontology audit: risk low, mutation true, mutation_overridable true. Step declares mutation false.
    const s = step('clarify_intent', 'audit');
    expect(s.effective.mutation).toBe(false);
    expect(s.effective.risk).toBe('low');
    expect(s.effective.downgrades).toEqual([]);
  });

  it('debug_code_change audit: mutation false honoured and risk raised to medium', () => {
    const s = step('debug_code_change', 'audit');
    expect(s.index).toBe(11);
    expect(s.effective.mutation).toBe(false);
    expect(s.effective.risk).toBe('medium');
  });
});

describe('effective flags on synthetic steps (§5.2.1)', () => {
  it('ignores every weaker declaration on mutate and reports each as a downgrade', () => {
    // Ontology mutate: risk high, mutation, requires_checkpoint and requires_approval all true.
    const f = effectiveFlags(
      { risk: 'low', mutation: false, requires_checkpoint: false, requires_approval: false },
      cap('mutate'),
    );
    expect(f.risk).toBe('high');
    expect(f.mutation).toBe(true);
    expect(f.requires_checkpoint).toBe(true);
    expect(f.requires_approval).toBe(true);
    // Order follows the reference validator's W602 reports (core/src/validate/semantics.rs).
    expect(f.downgrades).toEqual(['mutation', 'requires_checkpoint', 'requires_approval', 'risk']);
    // "reported as V102 instead where the ontology's requires edge from checkpoint already demands it"
    expect(f.checkpoint).toEqual({ needed: true, via: 'requires-edge', code: 'V102' });
  });

  it('does not honour mutation false on a capability that is not mutation_overridable', () => {
    // Ontology persist: mutation true, no mutation_overridable.
    const f = effectiveFlags({ mutation: false }, cap('persist'));
    expect(f.mutation).toBe(true);
    expect(f.downgrades).toEqual(['mutation']);
  });

  it('applies a stricter declaration on observe (the §5.2.1 example)', () => {
    // Ontology observe: risk low, no requires_approval.
    const f = effectiveFlags({ requires_approval: true }, cap('observe'));
    expect(f.requires_approval).toBe(true);
    expect(f.downgrades).toEqual([]);
  });

  it('uses the ontology values when the step declares nothing', () => {
    const f = effectiveFlags({}, cap('send'));
    expect([f.risk, f.mutation, f.requires_checkpoint, f.requires_approval]).toEqual(['high', true, true, true]);
  });

  it('raises requires_checkpoint on a capability without one, which then needs F501', () => {
    const f = effectiveFlags({ requires_checkpoint: true }, cap('generate'));
    expect(f.requires_checkpoint).toBe(true);
    expect(f.checkpoint).toEqual({ needed: true, via: 'flag', code: 'F501' });
  });
});
