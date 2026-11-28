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
    expect(CASES).toHaveLength(36);
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

// Security round 5, batch 5: flags the domain profiles a layer applies raise
// are effective flags (§5.21.3), which a record does not state; a layer
// passes them as `raised`, so the offered-tool checks see them.
describe('flags a layer raises beyond the record (§5.21.3)', () => {
  const finish = { tool: 'finish', ontology: '2.2.0', capability: 'classify' };
  const approval = { risk: 'low', mutation: false, requires_checkpoint: false, requires_approval: true } as const;
  const checkpoint = { risk: 'low', mutation: false, requires_checkpoint: true, requires_approval: false } as const;
  const codes = (records: unknown[], options: Parameters<typeof checkBindings>[1]) =>
    checkBindings(records, options).diagnostics.map((d) => [d.code, d.location.tool]);

  it('reports F506 for a host action tied to a tool they make need approval, and joins them into its flags', () => {
    const options = { offered: { finish: 'finish' }, hostActions: [{ action: 'stopTool', tool: 'finish' }] };
    expect(codes([finish], options)).toEqual([]);
    expect(codes([finish], { ...options, raised: { finish: approval } })).toEqual([['F506', 'finish']]);
    expect(checkBindings([finish], { raised: { finish: approval } }).effective['finish']).toMatchObject({ requires_approval: true });
  });

  it('reports V102 for a raised requires_checkpoint when no offered tool takes one', () => {
    const save = { tool: 'save', ontology: '2.2.0', capability: 'checkpoint' };
    expect(codes([finish], { offered: { finish: 'finish' }, raised: { finish: checkpoint } })).toEqual([['V102', 'finish']]);
    expect(codes([finish, save], { offered: { finish: 'finish', save: 'save' }, raised: { finish: checkpoint } })).toEqual([]);
  });

  it('raises no control-only tool, and no tool it does not name', () => {
    const stop = { tool: 'stop', ontology: '2.2.0', control: true };
    const options = { offered: { stop: 'stop', finish: 'finish' }, hostActions: [{ action: 'stopTool', tool: 'stop' }] };
    expect(codes([stop, finish], { ...options, raised: { stop: approval } })).toEqual([]);
    expect(checkBindings([stop, finish], { raised: { stop: approval } }).effective['finish']).toMatchObject({ requires_approval: false });
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

describe('bindings loaded earlier (known)', () => {
  const record = (tool: string, capability: string, invokes?: string[]) => ({
    tool,
    ontology: '2.2.0',
    capability,
    ...(invokes ? { invokes } : {}),
  });

  it('closes no invokes cycle across two loads (V105)', () => {
    const first = checkBindings([record('a', 'retrieve'), record('b', 'generate', ['a'])]);
    expect(first.diagnostics).toEqual([]);
    const second = checkBindings([record('a', 'generate', ['b'])], { known: first.effective });
    expect(second.diagnostics.map((d) => `${d.code} ${d.location.tool}`)).toEqual(['V105 a']);
    expect(second.effective).toEqual({});
  });

  it("joins a composite's approval with that of its invokes, transitively (§5.18.4)", () => {
    const approval = (a: Record<string, unknown>) => ({ approval: a });
    const { effective, diagnostics } = checkBindings([
      { ...record('write_prod', 'mutate'), ...approval({ role: 'admin', min_approvers: 2, expires: '1m' }) },
      { ...record('batch', 'invoke', ['write_prod']), ...approval({ expires: '10m' }) },
      record('outer', 'invoke', ['batch']),
      { ...record('ops', 'invoke', ['write_prod']), ...approval({ role: 'ops' }) },
      record('plain', 'invoke'),
    ]);
    expect(diagnostics).toEqual([]);
    const joined = { min_approvers: 2, role: 'admin', expires_ms: 60_000 };
    expect(effective['batch']!.approval).toEqual(joined);
    expect(effective['outer']!.approval).toEqual(joined);
    expect(effective['ops']!.approval).toEqual({ ...joined, role: 'ops' });
    expect(effective['plain']!.approval).toBeUndefined();
    // Across two loads, from the bindings known.
    const first = checkBindings([{ ...record('w', 'mutate'), ...approval({ min_approvers: 3 }) }]);
    const second = checkBindings([record('batch', 'invoke', ['w'])], { known: first.effective });
    expect(second.effective['batch']!.approval).toEqual({ min_approvers: 3 });
  });

  it('resolves an invokes name among them', () => {
    const first = checkBindings([record('w', 'mutate')]);
    const { effective, diagnostics } = checkBindings([record('batch', 'invoke', ['w'])], {
      known: first.effective,
    });
    expect(diagnostics).toEqual([]);
    expect(effective['batch']!.requires_checkpoint).toBe(true);
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

  it('keeps an unknown member, so the record is S303 and not loaded (security round 3)', () => {
    // A misspelt member was dropped, so the record loaded as a plain
    // retrieve: approval, a checkpoint and the destination check were lost.
    for (const annotation of [
      { standard: '1.2.0', ontology: '2.2.0', capability: 'retrieve', aproval: { min_approvers: 2, role: 'admin' } },
      { ontology: '2.2.0', capability: 'retrieve', flag: { risk: 'high', mutation: true } },
      { ontology: '2.2.0', capability: 'retrieve', aditional_capabilities: ['send'] },
      JSON.parse('{"ontology": "2.2.0", "capability": "retrieve", "__proto__": {"flags": {"risk": "low"}}}'),
    ]) {
      const record = annotationRecord('wipe', annotation);
      expect(record).not.toBeNull();
      const { effective, diagnostics } = checkBindings([record]);
      expect(Object.hasOwn(effective, 'wipe')).toBe(false);
      expect(diagnostics.map((d) => d.code)).toEqual(['S303']);
      expect(Object.getPrototypeOf(record)).toBe(Object.prototype);
    }
    // vendor data and the copies still load
    const loads = annotationRecord('wipe', { ontology: '2.2.0', capability: 'retrieve', layer: 'PERCEIVE', risk: 'low', 'x-note': 1 });
    const loaded = checkBindings([loads]);
    expect(loaded.diagnostics).toEqual([]);
    expect(Object.hasOwn(loaded.effective, 'wipe')).toBe(true);
  });
});

describe('tool names a plain object holds on its prototype (security round 6)', () => {
  // `checkBindings` read the loaded bindings and the bindings known earlier
  // with `effective[name]`, so an offered or invoked name such as
  // `constructor`, `toString` or `__proto__` found the object's prototype:
  // the check threw where the Python loader reports W617 or F506, and a
  // record whose `tool` is `__proto__` set the prototype of the bindings
  // returned instead of being among them.
  const NAMES = ['constructor', 'toString', 'hasOwnProperty', '__proto__'];
  const retrieve = (tool: string) => ({ tool, ontology: '2.2.0', capability: 'retrieve' });

  for (const name of NAMES) {
    it(`reports an offered, unloaded '${name}' as unbound (W617)`, () => {
      const offered = Object.fromEntries([[name, name]]) as Record<string, string | null>;
      const { diagnostics } = checkBindings([], { offered });
      expect(diagnostics.map((d) => [d.code, d.location.tool])).toEqual([['W617', name]]);
    });

    it(`ties a host action to an unloaded '${name}' as F506`, () => {
      const { diagnostics } = checkBindings([], { offered: {}, hostActions: [{ action: 'stopTool', tool: name }] });
      expect(diagnostics.map((d) => [d.code, d.location.tool])).toEqual([['F506', name]]);
    });

    it(`loads a record whose tool is '${name}' as its own binding`, () => {
      const { effective, diagnostics } = checkBindings([retrieve(name)]);
      expect(diagnostics).toEqual([]);
      expect(Object.hasOwn(effective, name)).toBe(true);
      expect(Object.getPrototypeOf(effective)).toBe(Object.prototype);
      expect(effective[name]?.capabilities).toEqual(['retrieve']);
    });

    it(`resolves no invokes name '${name}' among bindings known earlier that hold none (V107)`, () => {
      const { effective, diagnostics } = checkBindings([{ ...retrieve('batch'), capability: 'invoke', invokes: [name] }], {
        known: {},
      });
      expect(Object.hasOwn(effective, 'batch')).toBe(false);
      expect(diagnostics.map((d) => d.code)).toEqual(['V107']);
    });
  }

  it('reports an offered, loaded tool as before (control)', () => {
    const { diagnostics } = checkBindings([retrieve('fetch')], { offered: { fetch: 'fetch', other: null } });
    expect(diagnostics.map((d) => [d.code, d.location.tool])).toEqual([['W617', 'other']]);
  });
});
