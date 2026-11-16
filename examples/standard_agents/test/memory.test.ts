// The memory tools (STANDARD 1.2.0 §4.5): the session cases of the memory
// vectors, read in place, and the refusal of secrets (§6.7).
import { describe, expect, it } from 'vitest';
import vectors from '../../../tests/conformance/memory/store.json' with { type: 'json' };
import { MemoryRefusal, memoryTools, persistEntry, recallEntry } from '../src/acs/memory.js';
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
