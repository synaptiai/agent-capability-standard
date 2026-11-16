/**
 * `persist` and `recall` on the thread's durable key-value store (STANDARD
 * 1.2.0 §4.5).
 *
 * Thread values carry no expiry and no stored-at time, so `persist` writes
 * an envelope `{ v: 1, data, stored_at, expires_at? }` under a key prefix of
 * its own, and `recall` reads it back by exact key (the thread store cannot
 * be listed): an entry whose `expires_at` has passed reads as missing. The
 * one scope provided is `session`, the thread (the default); any other is
 * refused with `unsupported_scope`. Data or a key holding a secret is
 * refused with `secret_in_data`, and nothing is stored (§6.7). What §4.5
 * asks a host to state: entries survive a restart (the runtime keeps thread
 * values in durable storage across restarts and redeploys); they are kept
 * while the thread lasts, unless their `ttl` ends them, and the tools delete
 * none; a value is limited to `max_value_bytes` (the UTF-8 length of its
 * JSON text), and the tools set no limit on the number of entries (the
 * runtime's own caps, which it may set, apply).
 *
 * The tools pass the session cases of `tests/conformance/memory/store.json`
 * (`test/memory.test.ts`); the pure functions `persistEntry` and
 * `recallEntry` are what they run.
 */
import type { ThreadState } from '@standardagents/spec';
import { canonicalize, holdsCredential, iJsonProblem, parseDurationMs, redactJson, type Json } from '@synaptiai/acs-core';
import { z } from 'zod';
import { groundedTool } from './grounded.js';

/** The scope this store provides, and its default. */
export const MEMORY_SCOPE = 'session';

/** The default limit on a value, in bytes. */
export const MAX_VALUE_BYTES = 1_000_000;

/** A refused operation: a §5.19.7 reason and a message with no secret in it. */
export class MemoryRefusal extends Error {
  constructor(
    readonly reason: 'unsupported_scope' | 'unsupported_ttl' | 'over_capacity' | 'secret_in_data' | `x-${string}`,
    message: string,
  ) {
    super(`${reason}: ${message}`);
  }
}

/** What `persistEntry` and `recallEntry` need of a store. */
export interface MemoryBackend {
  getValue<T>(key: string): Promise<T | null>;
  setValue(key: string, value: unknown): Promise<void>;
}

interface Envelope {
  v: 1;
  data: Json;
  stored_at: number;
  expires_at?: number;
}

export interface MemoryOptions {
  /** The key prefix of the tools' entries (default `acs:memory:`). */
  prefix?: string;
  /** Milliseconds since the Unix epoch; defaults to `Date.now`. */
  now?: () => number;
  /** The largest value, as the UTF-8 length of its JSON text. */
  max_value_bytes?: number;
  /** The host's own secrets (§6.7), refused in data and keys beside the default patterns. */
  secrets?: readonly string[];
  /** The tools' names (default `persist_memory` and `recall_memory`). */
  names?: { persist?: string; recall?: string };
}

const iso = (ms: number): string => new Date(ms).toISOString();

function storeKey(prefix: string, key: string): string {
  return `${prefix}${encodeURIComponent(key)}`;
}

function scopeOf(input: Record<string, unknown>): string {
  const scope = input['scope'] ?? MEMORY_SCOPE;
  if (scope !== MEMORY_SCOPE) {
    throw new MemoryRefusal(
      'unsupported_scope',
      `this store provides the memory scope 'session' (the thread) only, not ${JSON.stringify(scope)} (STANDARD 1.2.0 §4.5)`,
    );
  }
  return scope;
}

/** A random key, for a `persist` that names none. */
function generatedKey(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Store `input.data` under `input.key` (generated when absent) in the
 * session scope at `now`: the `persist` capability's output. Throws a
 * `MemoryRefusal`, having stored nothing, on a refusal.
 */
export async function persistEntry(
  store: MemoryBackend,
  input: Record<string, unknown>,
  now: number,
  options: Pick<MemoryOptions, 'prefix' | 'max_value_bytes' | 'secrets'> = {},
): Promise<Record<string, Json>> {
  const secrets = options.secrets ?? [];
  const data = (input['data'] ?? null) as Json;
  const given = input['key'];
  if (given !== undefined && typeof given !== 'string') throw new MemoryRefusal('x-invalid-key', 'key must be a string');
  // Secrets first (§4.5, §6.7): the message names where, never what.
  const keyHit = typeof given === 'string' && holdsCredential(given, secrets);
  if (holdsCredential(data, secrets) || keyHit) {
    const pointers = redactJson(data, secrets).pointers.map((p) => (p === '' ? '/' : p));
    const where = [...pointers, ...(keyHit ? ['the key'] : [])].join(', ') || 'the data';
    throw new MemoryRefusal(
      'secret_in_data',
      `the data holds what looks like a secret at ${where}; store a reference to where the secret is kept, not the secret (STANDARD 1.2.0 §4.5, §6.7)`,
    );
  }
  const scope = scopeOf(input);
  let ttl: number | null = null;
  if (input['ttl'] !== undefined && input['ttl'] !== null) {
    ttl = typeof input['ttl'] === 'string' ? parseDurationMs(input['ttl']) : null;
    if (ttl === null || ttl === 0) {
      throw new MemoryRefusal(
        'unsupported_ttl',
        `ttl ${JSON.stringify(input['ttl'])} is not a duration longer than zero (STANDARD 1.2.0 §4.5, §5.10.1)`,
      );
    }
  }
  const problem = iJsonProblem(data);
  if (problem !== null) throw new MemoryRefusal('x-not-i-json', `the data is not I-JSON: ${problem}`);
  const limit = options.max_value_bytes ?? MAX_VALUE_BYTES;
  const size = new TextEncoder().encode(canonicalize(data)).length;
  if (size > limit) {
    throw new MemoryRefusal(
      'over_capacity',
      `the value is ${size} bytes; this store keeps at most ${limit} bytes per value (STANDARD 1.2.0 §4.5)`,
    );
  }
  const key = typeof given === 'string' ? given : generatedKey();
  const envelope: Envelope = { v: 1, data, stored_at: now, ...(ttl !== null ? { expires_at: now + ttl } : {}) };
  await store.setValue(storeKey(options.prefix ?? 'acs:memory:', key), envelope);
  return {
    stored: true,
    key,
    scope,
    stored_at: iso(now),
    timestamp: iso(now),
    ...(envelope.expires_at !== undefined ? { expires_at: iso(envelope.expires_at) } : {}),
    evidence_anchors: [{ ref: `memory:${scope}:${key}`, kind: 'record' }],
  };
}

/**
 * Read `input.key` in the session scope at `now`: the `recall`
 * capability's output, `found` true with the entry's data, or false with
 * `input.default` (or null). An entry whose `expires_at` has passed reads
 * as missing.
 */
export async function recallEntry(
  store: MemoryBackend,
  input: Record<string, unknown>,
  now: number,
  options: Pick<MemoryOptions, 'prefix'> = {},
): Promise<Record<string, Json>> {
  const key = input['key'];
  if (typeof key !== 'string') throw new MemoryRefusal('x-invalid-key', 'key must be a string');
  const scope = scopeOf(input);
  const entry = await store.getValue<Envelope>(storeKey(options.prefix ?? 'acs:memory:', key));
  if (entry === null || entry.v !== 1 || (entry.expires_at !== undefined && entry.expires_at <= now)) {
    return { data: (input['default'] ?? null) as Json, found: false, scope, evidence_anchors: [] };
  }
  return {
    data: entry.data,
    found: true,
    scope,
    stored_at: iso(entry.stored_at),
    ...(entry.expires_at !== undefined ? { expires_at: iso(entry.expires_at) } : {}),
    evidence_anchors: [{ ref: `memory:${scope}:${key}`, kind: 'record' }],
  };
}

/**
 * The `persist` and `recall` tools on the thread's key-value store (§4.5),
 * each a `groundedTool` (so a `persist` call whose data holds a credential
 * is refused by the layer too, F504, §5.18.10).
 */
export function memoryTools(options: MemoryOptions = {}) {
  const now = options.now ?? (() => Date.now());
  const scope = z.string().optional().describe("The memory scope: 'session' (the thread), the only one provided");
  const persist = groundedTool({
    name: options.names?.persist ?? 'persist_memory',
    capability: 'persist',
    description: 'Store data under a key in this conversation (scope session), optionally until a ttl ends it.',
    args: z.object({
      data: z.unknown().describe('The data to store (JSON)'),
      key: z.string().optional().describe('The key; one is generated when absent'),
      ttl: z.string().optional().describe("How long the entry lasts, e.g. '1h' or 'PT30M'"),
      scope,
    }),
    ...(options.secrets !== undefined ? { secrets: options.secrets } : {}),
    execute: async (state: ThreadState, args) =>
      (await persistEntry(state, args as Record<string, unknown>, now(), options)) as never,
  });
  const recall = groundedTool({
    name: options.names?.recall ?? 'recall_memory',
    capability: 'recall',
    description: 'Read the data stored under a key in this conversation (scope session).',
    args: z.object({
      key: z.string().describe('The key'),
      default: z.unknown().optional().describe('What to return when no live entry has the key'),
      scope,
    }),
    execute: async (state: ThreadState, args) =>
      (await recallEntry(state, args as Record<string, unknown>, now(), options)) as never,
  });
  return { persist, recall };
}
