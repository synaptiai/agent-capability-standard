// Every runtime fixture (tests/conformance/runtime/*.json) through the core,
// by the matching rules of section 10.5, started with the fixture's header
// and start members: straight, and saved and restored before every entry.
import { describe, expect, it } from 'vitest';
import type { Json } from '../src/canonical.js';
import { CoreError, type CoreContext, type CoreRun, type StartArgs } from '../src/wasm.js';
import { repositoryContext } from './core.js';

const FIXTURES = import.meta.glob<Record<string, Json>>('../../../tests/conformance/runtime/*.json', {
  eager: true,
  import: 'default',
});

/** Whether `action` holds the member `path` names (member names joined by `.`, as a script entry's `absent` lists them). */
function holds(action: Json, path: string): boolean {
  let node: Json = action;
  for (const name of path.split('.')) {
    if (node === null || typeof node !== 'object' || Array.isArray(node) || !(name in node)) return false;
    node = (node as Record<string, Json>)[name] as Json;
  }
  return true;
}

/** `expected` matches `actual` when every key it names matches. */
function matches(expected: Json, actual: Json): boolean {
  if (expected !== null && typeof expected === 'object' && !Array.isArray(expected)) {
    if (actual === null || typeof actual !== 'object' || Array.isArray(actual)) return false;
    return Object.entries(expected).every(([k, v]) => k in actual && matches(v, (actual as Record<string, Json>)[k] as Json));
  }
  if (Array.isArray(expected)) {
    return Array.isArray(actual) && expected.length === actual.length && expected.every((x, i) => matches(x, actual[i] as Json));
  }
  return JSON.stringify(expected) === JSON.stringify(actual);
}

function fill(response: Json, action: Record<string, Json>): Json {
  if (response === '{{digest}}') return action.digest ?? null;
  if (Array.isArray(response)) return response.map((r) => fill(r, action));
  if (response !== null && typeof response === 'object') {
    return Object.fromEntries(Object.entries(response).map(([k, v]) => [k, fill(v, action)]));
  }
  return response;
}

function start(ctx: CoreContext, f: Record<string, Json>): CoreRun {
  const args: StartArgs = {
    catalog: f.catalog as Json,
    workflow: f.workflow as string,
    inputs: f.inputs as Record<string, Json>,
    header: f.header as string | null,
    runId: 'run-1',
    nowMs: f.start as number,
    attendance: f.attendance as 'attended' | 'unattended',
  };
  if (f.actor_identity !== undefined) args.actorIdentity = f.actor_identity;
  if (f.records !== undefined) args.records = f.records as 'approvals' | 'actions';
  if (f.profiles !== undefined) args.profiles = f.profiles as Json[];
  if (f.grounding !== undefined) args.grounding = f.grounding as Json[];
  if (f.destinations !== undefined) args.destinations = f.destinations as string[][];
  return ctx.start(args);
}

function play(ctx: CoreContext, f: Record<string, Json>, restoreEach: boolean): CoreRun {
  let run = start(ctx, f);
  let now = f.start as number;
  (f.script as Record<string, Json>[]).forEach((entry, i) => {
    if (restoreEach) {
      const snap = run.snapshot('00ff');
      const restored = ctx.restore({ catalog: f.catalog as Json, snapshot: snap, keyHex: '00ff' });
      run.dispose();
      run = restored;
    }
    if ('tick' in entry) {
      now = entry.tick as number;
      run.tick(now);
      return;
    }
    const action = run.next() as unknown as Record<string, Json>;
    if ('expect' in entry) {
      expect(matches(entry.expect as Json, action as Json), `entry ${i}: ${JSON.stringify(action)}`).toBe(true);
      for (const path of (entry.absent as string[] | undefined) ?? []) {
        expect(holds(action as Json, path), `entry ${i}: ${path} must be absent: ${JSON.stringify(action)}`).toBe(false);
      }
    }
    if ('respond' in entry) {
      now = (entry.at as number | undefined) ?? now;
      run.submit(action.id as number, fill(entry.respond as Json, action) as { kind: string }, now);
    }
  });
  return run;
}

const SUPPORTED = (f: Record<string, Json>) => !('catalogs' in f) && !('agents' in f);

describe('runtime fixtures through the core', () => {
  for (const [path, f] of Object.entries(FIXTURES)) {
    const name = path.split('/').pop() as string;
    for (const restoreEach of [false, true]) {
      it(`${name}${restoreEach ? ' (restored before every entry)' : ''}`, async () => {
        expect(SUPPORTED(f)).toBe(true);
        const ctx = await repositoryContext();
        const run = play(ctx, f, restoreEach);
        const end = run.next() as unknown as Json;
        expect(matches(f.end as Json, end), JSON.stringify(end)).toBe(true);
        const kinds = new Set((run.trace() as Record<string, Json>[]).map((t) => t.kind));
        if (!restoreEach) for (const k of f.trace_kinds as string[]) expect(kinds.has(k), k).toBe(true);
        run.dispose();
      });
    }
  }

  it('refuses a start without the header member', async () => {
    const ctx = await repositoryContext();
    const f = Object.values(FIXTURES)[0] as Record<string, Json>;
    const args = { catalog: f.catalog, workflow: f.workflow, runId: 'r', nowMs: 0 } as unknown as StartArgs;
    expect(() => ctx.start(args)).toThrow(CoreError);
    try {
      ctx.start(args);
    } catch (e) {
      expect((e as CoreError).kind).toBe('bad_request');
    }
  });
});
