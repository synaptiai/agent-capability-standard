import { describe, expect, it } from 'vitest';
import { AcsCore, CoreError } from '../src/wasm.js';
import { loadCore } from './core.js';

interface Raw {
  memory: WebAssembly.Memory;
  acs_alloc(len: number): number;
  acs_free(ptr: number, len: number): void;
  acs_call(ptr: number, len: number): number;
}

/** The exports themselves, driven as the wrapper drives them. */
async function raw(): Promise<Raw> {
  const core = await loadCore();
  return (core as unknown as { exports: Raw }).exports;
}

function round(r: Raw, request: Uint8Array): { n: number; text: string } {
  const ptr = r.acs_alloc(request.length);
  new Uint8Array(r.memory.buffer, ptr, request.length).set(request);
  const out = r.acs_call(ptr, request.length);
  const n = new DataView(r.memory.buffer).getUint32(out, true);
  const text = new TextDecoder().decode(new Uint8Array(r.memory.buffer, out + 4, n));
  r.acs_free(ptr, request.length);
  r.acs_free(out, 4 + n);
  return { n, text };
}

describe('the WebAssembly memory protocol', () => {
  it('round-trips requests of 0, 1 and 1 MiB bytes; the prefix is the body length', async () => {
    const r = await raw();
    for (const request of [new Uint8Array(0), new TextEncoder().encode('{')]) {
      const { n, text } = round(r, request);
      expect(new TextEncoder().encode(text).length).toBe(n);
      expect(JSON.parse(text).error.kind).toBe('bad_request');
    }
    const big = new TextEncoder().encode(
      JSON.stringify({ op: 'yaml.parse', max_bytes: 4 << 20, text: `x: ${'a'.repeat(1 << 20)}` }),
    );
    const { n, text } = round(r, big);
    expect(new TextEncoder().encode(text).length).toBe(n);
    expect(JSON.parse(text).ok.x).toHaveLength(1 << 20);
  });

  it('frees both buffers: 10 000 calls do not grow the memory beyond a bound', async () => {
    const r = await raw();
    const request = new TextEncoder().encode(JSON.stringify({ op: 'version' }));
    round(r, request);
    const before = r.memory.buffer.byteLength;
    for (let i = 0; i < 10_000; i++) round(r, request);
    expect(r.memory.buffer.byteLength).toBeLessThanOrEqual(before + (1 << 20));
  });

  it('answers through the wrapper and throws CoreError on a refusal', async () => {
    const core = await loadCore();
    expect(core.version().spec_versions).toEqual(['1.0', '1.1', '1.2']);
    expect(() => core.call('no.such.op')).toThrow(CoreError);
    try {
      core.call('run.next', { run: 424242 });
    } catch (e) {
      expect((e as CoreError).kind).toBe('unknown_handle');
    }
    expect(AcsCore).toBeDefined();
  });
});
