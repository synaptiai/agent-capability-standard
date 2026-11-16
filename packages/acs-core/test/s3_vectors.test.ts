import { describe, expect, it } from 'vitest';
import { agentsApply, checkTask, joinMaxima, manifestMaxima, type Maxima, workflowTarget } from '../src/agents.js';
import { selectImplementation, UnsupportedDomainError, isDomainId } from '../src/domains.js';
import { isModelFamily, modelFamily } from '../src/families.js';
import { issuePath } from '../src/issues.js';
import { ONTOLOGY_VERSION } from '../src/ontology.js';
// The language-neutral vectors, read in place; the Rust core and the Python
// package are held to the same files.
import maxima from '../../../tests/conformance/agents/maxima.json' with { type: 'json' };
import domains from '../../../tests/conformance/domains/match.json' with { type: 'json' };
import families from '../../../tests/conformance/families/derive.json' with { type: 'json' };

describe('agent maxima (STANDARD v1.2.0 §5.15.1)', () => {
  it('reads the ontology the vectors cite', () => {
    expect(maxima.ontology).toBe(ONTOLOGY_VERSION);
  });
  it.each(maxima.cases.map((c) => [c.name, c] as const))('%s', (_name, c) => {
    expect(manifestMaxima({ capabilities: c.capabilities }, c.read_only)).toEqual(c.maxima as Maxima | null);
  });
  it.each(maxima.joins.map((c) => [c.name, c] as const))('join: %s', (_name, c) => {
    const each = c.manifests.map((caps) => manifestMaxima({ capabilities: caps }, c.read_only));
    expect(joinMaxima(...each)).toEqual(c.maxima as Maxima | null);
  });
  it('checks a task by name and required', () => {
    const task = { table: { type: 'string', required: true }, rows: { type: 'array' } };
    expect(checkTask({ task }, { rows: [], colour: 'x' })).toEqual({ undeclared: ['colour'], missing: ['table'] });
    expect(checkTask({}, { anything: 1 })).toEqual({ undeclared: [], missing: [] });
  });
});

describe('the version a workflow targets (STANDARD v1.2.0 §11.5, §5.15.2)', () => {
  // [spec_version, header, target, agents apply]
  const cases: [unknown, string | null, [number, number] | null, boolean][] = [
    ['1.2', null, [1, 2], true],
    ['1.2.0', '1.1.0', [1, 2], true],
    ['1.1', '1.2.0', [1, 1], false],
    [undefined, '1.2.0', [1, 2], true],
    [undefined, '1.1.0', [1, 1], false],
    [undefined, null, null, false],
    ['1.10', null, [1, 10], true],
    ['2.0', null, [2, 0], true],
    // A spec_version that is not a string, or does not parse, gives way to
    // the header, as in the core.
    [1.2, '1.1.0', [1, 1], false],
    ['1.2.0.1', '1.2.0', [1, 2], true],
    ['v1.2', null, null, false],
  ];
  it.each(cases)('spec_version %j, header %j', (spec, header, target, apply) => {
    const workflow: Record<string, unknown> = spec === undefined ? {} : { spec_version: spec };
    expect(workflowTarget(workflow, header)).toEqual(target);
    expect(agentsApply(workflow, header)).toBe(apply);
  });
});

describe('domain selection (STANDARD v1.2.0 §5.2.4)', () => {
  it.each(domains.cases.map((c) => [c.name, c] as const))('%s', (_name, c) => {
    if (c.expect === null) {
      expect(() => selectImplementation(c.domain, c.implementations)).toThrow(UnsupportedDomainError);
    } else {
      expect(selectImplementation(c.domain, c.implementations)).toBe(c.expect);
    }
  });
  it('knows the grammar', () => {
    expect(isDomainId('image.3d')).toBe(true);
    expect(isDomainId('plan-invalidation')).toBe(false);
    try {
      selectImplementation('x', []);
    } catch (e) {
      expect((e as UnsupportedDomainError).reason).toBe('unsupported_domain');
    }
  });
});

describe('model families (STANDARD v1.2.0 §5.15)', () => {
  it.each(families.cases.map((c) => [c.model_id, c] as const))('%s', (_id, c) => {
    expect(modelFamily(c.model_id)).toBe(c.family);
    if (c.family !== null) expect(isModelFamily(c.family)).toBe(true);
  });
});

describe('issue paths (STANDARD v1.2.0 §9.8)', () => {
  it('projects workflow, step and field', () => {
    expect(issuePath({ workflow: 'review', step: 1, field: 'gates[0].when' })).toBe('review.steps[1].gates[0].when');
    expect(issuePath({ workflow: 'w', field: 'triggers[0].schedule.cron' })).toBe('w.triggers[0].schedule.cron');
    expect(issuePath({ workflow: 'w', step: 0 })).toBe('w.steps[0]');
    expect(issuePath({ field: 'catalog.exports[1]' })).toBe('catalog.exports[1]');
    expect(issuePath({ workflow: 'w' })).toBe('w');
  });
});
