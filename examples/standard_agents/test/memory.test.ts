// The memory tools (STANDARD 1.2.0 §4.5): the session cases of the memory
// vectors, read in place, and the refusal of secrets (§6.7).
import { afterEach, describe, expect, it } from 'vitest';
import type { Json } from '@synaptiai/acs-core';
import type { ProfileFlags, ProfilePolicy } from '@synaptiai/acs-core/wasm';
import vectors from '../../../tests/conformance/memory/store.json' with { type: 'json' };
import { acsAnnotation } from '../src/acs/grounded.js';
import { configureLayer, resetLayer } from '../src/acs/layer.js';
import { MemoryRefusal, memoryTools, persistEntry, recallEntry } from '../src/acs/memory.js';
import { effectiveFlags, type CapabilityId } from '../src/acs/ontology.js';
import { bindingProfiles, type BindingProfiles } from '../src/acs/profiles.js';
import { memoryThread } from './memory_thread.js';

type Op = {
  at?: number;
  context?: Record<string, unknown>;
  persist?: Record<string, unknown>;
  recall?: Record<string, unknown>;
  expect?: Record<string, unknown>;
  error?: string;
  end?: unknown;
};
type Case = { name: string; scopes: string[]; config?: { max_value_bytes?: number }; ops: Op[] };

const fill = (value: unknown, keys: unknown[]): unknown => {
  if (typeof value === 'string') {
    if (value === '{{default}}') return 'session';
    if (value === '{{unprovided}}') return 'x-unprovided';
    const m = /^\{\{key:(\d+)\}\}$/.exec(value);
    return m ? keys[Number(m[1])] : value;
  }
  if (Array.isArray(value)) return value.map((v) => fill(v, keys));
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, fill(v, keys)]));
  }
  return value;
};

const matches = (expected: unknown, actual: unknown): boolean => {
  if (expected !== null && typeof expected === 'object' && !Array.isArray(expected)) {
    if (actual === null || typeof actual !== 'object') return false;
    return Object.entries(expected).every(([k, v]) => {
      const a = (actual as Record<string, unknown>)[k];
      if (!(k in (actual as object))) return false;
      if (k === 'data') return JSON.stringify(a) === JSON.stringify(v);
      if (k === 'stored_at' || k === 'expires_at') return Date.parse(String(a)) === Date.parse(String(v));
      return matches(v, a);
    });
  }
  if (Array.isArray(expected)) {
    return Array.isArray(actual) && expected.length === actual.length && expected.every((e, i) => matches(e, actual[i]));
  }
  return expected === actual;
};

// The cases whose scopes this store provides: session (the default) only,
// and the refusal of a scope it does not provide.
const cases = (vectors.cases as Case[]).filter((c) => c.scopes.every((s) => s === 'session' || s === '{{default}}'));

describe('memory vectors (session)', () => {
  it('runs the session cases', () => {
    expect(vectors.status).toBe('normative');
    expect(cases.map((c) => c.name)).toContain('unprovided_scope');
    expect(cases.length).toBeGreaterThanOrEqual(14);
  });
  it.each(cases.map((c) => [c.name, c] as const))('%s', async (_name, c) => {
    const t = memoryThread();
    const keys: unknown[] = [];
    for (const [i, op] of c.ops.entries()) {
      if (op.end !== undefined) {
        keys.push(null);
        continue;
      }
      const context = { ...vectors.context, ...(op.context ?? {}) } as Record<string, unknown>;
      // One thread is one session: another session is another thread.
      const store = context['session'] === vectors.context.session ? t.state : memoryThread().state;
      const now = op.at ?? 0;
      const input = fill(op.persist ?? op.recall, keys) as Record<string, unknown>;
      const run = () =>
        op.persist !== undefined
          ? persistEntry(store, input, now, { ...(c.config?.max_value_bytes !== undefined ? { max_value_bytes: c.config.max_value_bytes } : {}) })
          : recallEntry(store, input, now);
      if (op.error !== undefined) {
        await expect(run(), `op ${i}`).rejects.toMatchObject({ reason: op.error });
        keys.push(null);
        continue;
      }
      const out = await run();
      expect(matches(fill(op.expect, keys), out), `op ${i}: ${JSON.stringify(out)}`).toBe(true);
      keys.push(out['key'] ?? null);
    }
  });
});

describe('secret_in_data', () => {
  it.each([
    ['a GitHub token in data', { key: 'k', data: { token: `ghp_${'a'.repeat(36)}` } }, '/token'],
    ['a bearer header in a nested member', { key: 'k', data: { req: { headers: { Authorization: 'Bearer abcdefghijklmnopqrstuvwx' } } } }, '/req/headers/Authorization'],
    ['a registered secret in the key', { key: 'pw-s3cret-value', data: 1 }, 'the key'],
    // Headers as name/value pairs (a HAR) and [name, value] tuples (security round 1, batch 6).
    ['a header pair', { key: 'k', data: { headers: [{ name: 'Authorization', value: 'Basic dXNlcjpodW50ZXIyMDI2' }] } }, '/headers/0/value'],
    ['a header tuple', { key: 'k', data: { headers: [['X-Api-Key', 'k3y9f8e7d6c5b4a3']] } }, '/headers/0/1'],
  ] as const)('%s: refused, nothing stored', async (_name, input, where) => {
    const t = memoryThread();
    const refused = persistEntry(t.state, input, 0, { secrets: ['s3cret-value'] });
    await expect(refused).rejects.toBeInstanceOf(MemoryRefusal);
    await expect(refused).rejects.toMatchObject({ reason: 'secret_in_data' });
    const message = await refused.catch((e: Error) => e.message);
    expect(message).toContain(where);
    expect(message).not.toMatch(/ghp_|abcdefghijklmnop|s3cret/);
    expect([...t.values.keys()].filter((k) => k.startsWith('acs:memory:'))).toEqual([]);
  });
});

// A registered secret given as a JSON number (a card number, a PIN) is
// refused as its string form is: the JSON text the store keeps holds it
// (§6.7; security round 4, batch 5).
describe('a registered secret given as a number', () => {
  afterEach(() => resetLayer());
  const CARD = '4111111111111111';

  it('is refused by persistEntry, at its member, and nothing is stored', async () => {
    const t = memoryThread();
    for (const data of [{ card: 4111111111111111 }, { cards: [7, 4111111111111111] }, 4111111111111111]) {
      const refused = persistEntry(t.state, { key: 'k', data }, 0, { secrets: [CARD] });
      await expect(refused).rejects.toMatchObject({ reason: 'secret_in_data' });
      expect(await refused.catch((e: Error) => e.message)).not.toContain(CARD);
    }
    expect([...t.values.keys()].filter((k) => k.startsWith('acs:memory:'))).toEqual([]);
    // A number that holds none is stored.
    expect(await persistEntry(t.state, { key: 'k', data: { count: 4111 } }, 1, { secrets: [CARD] })).toMatchObject({ stored: true });
  });

  it('is refused by the persist tool, with the layer secrets, as the string is', async () => {
    configureLayer({ secrets: [CARD] });
    const { persist } = memoryTools();
    const t = memoryThread();
    for (const data of [{ card: CARD }, { card: 4111111111111111 }]) {
      const result = await persist.execute(t.state, { key: 'card', data });
      expect(result.status).toBe('error');
      expect(result.error_code).toBe('F504');
    }
    expect([...t.values.entries()].filter(([k]) => k.startsWith('acs:memory:'))).toEqual([]);
    expect([...t.values.values()].join('\n')).not.toContain(CARD);
  });
});

describe('unsupported_ttl', () => {
  it('refuses a ttl that ends the entry after the last date-time, and stores nothing', async () => {
    const t = memoryThread();
    for (const ttl of ['P100000000D', 'P3000000D']) {
      const refused = persistEntry(t.state, { key: 'k', data: 1, ttl }, 1);
      await expect(refused).rejects.toMatchObject({ reason: 'unsupported_ttl' });
    }
    expect([...t.values.keys()].filter((k) => k.startsWith('acs:memory:'))).toEqual([]);
    expect(await recallEntry(t.state, { key: 'k' }, 2)).toMatchObject({ found: false });
    expect(await persistEntry(t.state, { key: 'k', data: 2, ttl: 'P1D' }, 3)).toMatchObject({ stored: true });
    expect(await recallEntry(t.state, { key: 'k' }, 4)).toMatchObject({ found: true, data: 2 });
  });
});

describe('memoryTools', () => {
  it('persists and recalls through grounded tools', async () => {
    const now = { t: 1_000 };
    const { persist, recall } = memoryTools({ now: () => now.t });
    const t = memoryThread();
    const stored = await persist.execute(t.state, { key: 'k', data: { a: 1 }, ttl: '1s' });
    expect(stored.status).toBe('success');
    const found = await recall.execute(t.state, { key: 'k' });
    expect(found.status).toBe('success');
    expect(String(found.result)).toContain('"found":true');
    now.t = 2_000;
    const gone = await recall.execute(t.state, { key: 'k' });
    expect(String(gone.result)).toContain('"found":false');
  });
  it('refuses a scope other than session', async () => {
    const { persist } = memoryTools();
    const result = await persist.execute(memoryThread().state, { key: 'k', data: 1, scope: 'global' });
    expect(result.status).toBe('error');
    expect(result.error).toContain('unsupported_scope');
  });
});

// The memory tools apply domain profiles as any grounded tool does
// (STANDARD 1.2.0 §5.21.1): their own (`profiles`) and the layer's
// (`configureLayer({ profiles })`), so none escapes a profile's persist
// checkpoint or person requirement (security round 1, batch 5).
describe('memoryTools under domain profiles', () => {
  const NO_RULES: ProfilePolicy = { minimum_confidence: null, grounding: [], destinations: [], trust_weights: {} };
  /** A healthcare-like profile: checkpoint before persist, a person for every call. */
  const healthcare = (): BindingProfiles =>
    bindingProfiles(
      {
        checkProfiles: () => ({ diagnostics: [], suggestions: [] }),
        profileFlags: (_p: Json[], c: CapabilityId): ProfileFlags => {
          const { flags } = effectiveFlags(c);
          return { ...flags, requires_checkpoint: flags.requires_checkpoint || c === 'persist', requires_approval: true, person: true };
        },
        profilePolicy: () => NO_RULES,
      },
      [{ domain: 'healthcare' }],
      { onWarning: () => {} },
    );
  const DX = { key: 'dx', data: { patient: 'p-17', note: 'suspected sepsis' } };

  it('applies the profiles given to them', async () => {
    const { persist, recall } = memoryTools({ profiles: healthcare() });
    const t = memoryThread();
    const stored = await persist.execute(t.state, DX);
    expect(stored.error_code).toBe('F502');
    expect(stored.error).toContain("person's approval");
    expect((await recall.execute(t.state, { key: 'dx' })).error_code).toBe('F502');
    expect(acsAnnotation(persist)).toMatchObject({ requires_checkpoint: true, requires_approval: true });
  });

  it("applies the layer's profiles, and refuses a call once they change after the tools were defined", async () => {
    try {
      configureLayer({ profiles: healthcare() });
      const { persist } = memoryTools();
      const t = memoryThread();
      expect((await persist.execute(t.state, DX)).error_code).toBe('F502');
      // Defined before the profiles were lifted: its flags were the profiled ones.
      resetLayer();
      const refused = await persist.execute(t.state, DX);
      expect(refused.error_code).toBe('R407');
      expect(refused.error).toContain('after this tool was defined');
      // Defined with no profile in force, then a profile put in force.
      const plain = memoryTools().persist;
      configureLayer({ profiles: healthcare() });
      expect((await plain.execute(t.state, DX)).error_code).toBe('R407');
    } finally {
      resetLayer();
    }
  });

  it('refuses a profile policy carrying rules configureLayer does not put in force', () => {
    expect(() => configureLayer({ profilePolicy: { ...NO_RULES, minimum_confidence: 0.9 } })).toThrow(/§5\.21\.4/);
    expect(() =>
      configureLayer({ profilePolicy: { ...NO_RULES, grounding: [{ require: ['detect'], kinds: null }] } }),
    ).toThrow(/§5\.21\.4/);
    configureLayer({ profilePolicy: { ...NO_RULES, destinations: [['https://ok.example/*']] } });
    resetLayer();
  });
});
