/**
 * The binding fixtures (tests/conformance/bindings/, STANDARD 1.2.0 §10.4)
 * through `checkBindings`, with the same expectations as the Python loader.
 */
import { describe, expect, it } from 'vitest';
import { annotationRecord, checkBindings, parseDuration, parseRecord } from '../src/binding.js';
import { effectiveFlagsOf } from '../src/flags.js';
import { parseJsonExact } from '../src/ijson.js';
import { prerequisitesOf } from '../src/ontology.js';

interface Fixture {
  description: string;
  ontology: string;
  needs?: string[];
  records: unknown[];
  offered?: Record<string, string | null>;
  host_actions?: { action: string; tool: string }[];
  host_takes_checkpoints?: boolean;
  expect: {
    errors: { code: string; tool: string }[];
    warnings: { code: string; tool: string }[];
    effective: Record<string, { risk: string; mutation: boolean; requires_checkpoint: boolean; requires_approval: boolean }>;
  };
}

// Read as text and parsed exactly, so that an integer literal beyond 2^53
// reaches the loader as the fixture states it, not rounded by JSON.parse.
const FIXTURES = import.meta.glob<string>('../../../tests/conformance/bindings/*.json', {
  eager: true,
  query: '?raw',
  import: 'default',
});
const CASES = Object.entries(FIXTURES).map(
  ([path, text]) => [path.split('/').pop()!.replace('.json', ''), parseJsonExact(text) as Fixture] as const,
);

const pairs = (list: { code: string; location?: { tool: string }; tool?: string }[]) =>
  list.map((d) => `${d.code} ${d.location?.tool ?? d.tool}`).sort();

describe('binding fixtures', () => {
  it('reads all of them', () => {
    expect(CASES).toHaveLength(33);
  });

  it.each(CASES)('%s', (_name, fixture) => {
    const options =
      fixture.offered !== undefined || fixture.host_actions !== undefined
        ? {
            offered: fixture.offered ?? {},
            hostActions: fixture.host_actions ?? [],
            hostTakesCheckpoints: fixture.host_takes_checkpoints ?? false,
          }
        : {};
    const { effective, diagnostics } = checkBindings(fixture.records, options);
    expect(pairs(diagnostics.filter((d) => d.severity === 'error'))).toEqual(pairs(fixture.expect.errors));
    expect(pairs(diagnostics.filter((d) => d.severity === 'warning'))).toEqual(pairs(fixture.expect.warnings));
    const flags = Object.fromEntries(
      Object.entries(effective).map(([tool, b]) => [
        tool,
        { risk: b.risk, mutation: b.mutation, requires_checkpoint: b.requires_checkpoint, requires_approval: b.requires_approval },
      ]),
    );
    expect(flags).toEqual(fixture.expect.effective);
  });
});

describe('parseRecord', () => {
  it('reads a full record', () => {
    const { binding, errors } = parseRecord({
      tool: 't',
      ontology: '2.2.0',
      standard: '1.2',
      capability: 'send',
      domain: 'email',
      flags: { risk: 'high' },
      additional_capabilities: ['mutate'],
      invokes: ['other'],
      approval: { min_approvers: 2, role: 'ops', expires: 'PT10M' },
      destination: '/to',
      'x-vendor': 1,
    });
    expect(errors).toEqual([]);
    expect(binding?.approval).toEqual({ min_approvers: 2, role: 'ops', expires_ms: 600_000 });
    expect(binding?.destination).toBe('/to');
  });

  it.each([
    [{ ontology: '2.2.0', capability: 'mutate' }, 'S304', 'tool'],
    [{ tool: 't', ontology: '2.2.0' }, 'S304', 'capability'],
    [{ tool: 't', ontology: '2.2.0', capability: 'mutate', surprise: 1 }, 'S303', 'surprise'],
    [{ tool: 't', ontology: '2.2.0', capability: 'mutate', control: true }, 'S303', 'capability'],
    [{ tool: 't', ontology: '2.2.0', capability: 'mutate', approval: { expires: '0s' } }, 'S303', 'approval.expires'],
    [{ tool: 't', ontology: '2.2.0', capability: 'mutate', approval: { min_approvers: 0 } }, 'S303', 'approval.min_approvers'],
    [{ tool: 't', ontology: '2.2.0', capability: 'mutate', approval: { min_approvers: 1.5 } }, 'S303', 'approval.min_approvers'],
    [{ tool: 't', ontology: '2.2.0', capability: 'mutate', flags: { risk: 'extreme' } }, 'S303', 'flags.risk'],
    [{ tool: 't', ontology: '2.2.0', capability: 'send', destination: 'to' }, 'S303', 'destination'],
    // A member with no I-JSON form (§5.14), vendor data included.
    [{ tool: 't', ontology: '2.2.0', capability: 'search', 'x-build': 2 ** 60 }, 'S303', 'x-build'],
    [{ tool: 't', ontology: '2.2.0', capability: 'search', 'x-note': 'a\ud800' }, 'S303', 'x-note'],
    [{ tool: 't', ontology: '2.2.0', capability: 'search', 'x-when': new Date(0) }, 'S303', 'x-when'],
    [{ tool: 't\udc00', ontology: '2.2.0', capability: 'search' }, 'S303', 'tool'],
  ])('refuses %j', (record, code, field) => {
    const { binding, errors } = parseRecord(record);
    expect(binding).toBeNull();
    expect(errors.map((e) => [e.code, e.location.field])).toContainEqual([code, field]);
  });
});

describe('diagnostic fields (§9.8: keys joined by a dot)', () => {
  it('names a weaker flag by its path in the record', () => {
    const { diagnostics } = checkBindings([
      { tool: 'w', ontology: '2.2.0', capability: 'mutate', flags: { risk: 'low', requires_approval: false } },
    ]);
    expect(diagnostics.map((d) => [d.code, d.location.field])).toEqual([
      ['W602', 'flags.risk'],
      ['W602', 'flags.requires_approval'],
    ]);
  });
});

describe('parseDuration', () => {
  it.each([
    ['250ms', 250],
    ['30s', 30_000],
    ['5m', 300_000],
    ['2h', 7_200_000],
    ['1d', 86_400_000],
    ['0s', 0],
    ['PT1H30M', 5_400_000],
    ['P1D', 86_400_000],
    ['P1DT2H', 93_600_000],
    ['PT0.5S', 500],
    ['PT1M0.25S', 60_250],
    ['PT0.000000001S', 1],
  ])('%s is %d ms', (text, ms) => {
    expect(parseDuration(text)).toBe(ms);
  });

  it.each(['P', 'PT', 'P1DT', '1w', 'PT1.S', 'PT.5S', 'PT1M1H', '10', 'PT1H1H', 'P1Y'])('%s is not a duration', (text) => {
    expect(parseDuration(text)).toBeNull();
  });
});

describe('flags over several capabilities', () => {
  it('takes the strictest flags and every prerequisite', () => {
    expect(effectiveFlagsOf(['plan', 'mutate']).flags).toEqual({
      risk: 'high',
      mutation: true,
      requires_checkpoint: true,
      requires_approval: true,
    });
    expect(prerequisitesOf(['plan', 'mutate', 'rollback'])).toEqual(['checkpoint']);
  });

  it('honours mutation: false only on a single overridable capability', () => {
    expect(effectiveFlagsOf(['audit'], { mutation: false }).flags.mutation).toBe(false);
    const both = effectiveFlagsOf(['audit', 'persist'], { mutation: false });
    expect(both.flags.mutation).toBe(true);
    expect(both.warnings[0]).toMatch(/^W602/);
    expect(effectiveFlagsOf(['mutate'], { requires_checkpoint: false }).warnings[0]).toMatch(/^W602/);
  });
});

describe('annotationRecord', () => {
  it('reads the record members and ignores the copies', () => {
    expect(
      annotationRecord('write', {
        standard: '1.2.0',
        ontology: '2.2.0',
        tool: 'other',
        capability: 'mutate',
        layer: 'PERCEIVE',
        risk: 'low',
        requires_checkpoint: false,
        invokes: ['x'],
        'x-note': 1,
      }),
    ).toEqual({ tool: 'write', standard: '1.2.0', ontology: '2.2.0', capability: 'mutate', invokes: ['x'], 'x-note': 1 });
    expect(annotationRecord('write', null)).toBeNull();
  });
});
