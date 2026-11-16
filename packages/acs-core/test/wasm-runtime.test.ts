// Every runtime fixture (tests/conformance/runtime/*.json) through the core,
// by the matching rules of section 10.5, started with the fixture's header
// and start members: straight, saved and restored before every entry, and
// with the trace and the settled records taken out before every entry
// (section 5.19.4). At every tick the run must change exactly when the time
// reaches its wake-up time (section 5.19.3).
import { describe, expect, it } from 'vitest';
import type { Json } from '../src/canonical.js';
import { CoreError, type CoreContext, type CoreRun, type ResumeArgs, type StartArgs } from '../src/wasm.js';
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

/** `response` with `"{{digest}}"` replaced by the action's digest, and `"{{digest_upper}}"` by it in uppercase. */
function fill(response: Json, action: Record<string, Json>): Json {
  if (response === '{{digest}}') return action.digest ?? null;
  if (response === '{{digest_upper}}') return String(action.digest).toUpperCase();
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

type Replay = 'plain' | 'restore' | 'drain';

/** What a replay saw: the run, and the records taken out of it (a drain replay). */
interface Played {
  run: CoreRun;
  taken: Json[];
}

/** A terminal action of a run whose host took records holds the records not taken: with the taken ones before them, it is the action of a run that took none. */
function withTaken(action: Record<string, Json>, taken: Json[]): Record<string, Json> {
  if (!Array.isArray(action.action_records)) return action;
  return { ...action, action_records: [...taken, ...action.action_records] };
}

function play(ctx: CoreContext, f: Record<string, Json>, mode: Replay): Played {
  let run = start(ctx, f);
  let now = f.start as number;
  const taken: Json[] = [];
  const restore = () => {
    const snap = run.snapshot('00ff');
    const restored = ctx.restore({ catalog: f.catalog as Json, snapshot: snap, keyHex: '00ff' });
    run.dispose();
    run = restored;
  };
  (f.script as Record<string, Json>[]).forEach((entry, i) => {
    if (mode === 'restore') restore();
    if (mode === 'drain') {
      run.takeTrace();
      taken.push(...run.takeRecords());
    }
    if ('tick' in entry) {
      now = entry.tick as number;
      const wake = run.wakeAt();
      const changed = run.tick(now);
      expect(changed, `entry ${i}: tick ${now} with wake-up time ${wake}`).toBe(wake !== null && now >= wake);
      if ('changed' in entry) expect(changed, `entry ${i}: changed`).toBe(entry.changed);
      return;
    }
    if ('wake_at' in entry) {
      expect(run.wakeAt(), `entry ${i}: wake_at`).toBe(entry.wake_at);
      return;
    }
    if ('cancel' in entry) {
      const c = entry.cancel as Record<string, Json>;
      now = (c.at as number | undefined) ?? now;
      run.cancel(c.reason as string, now);
      return;
    }
    if ('resume' in entry) {
      // The host keeps the run's state while it waits, restores it and resumes it (section 5.14.1).
      const r = entry.resume as Record<string, Json>;
      now = (r.at as number | undefined) ?? now;
      restore();
      const args: ResumeArgs = { nowMs: now, attendance: (r.attendance as 'attended' | 'unattended' | undefined) ?? 'attended' };
      if (r.actor_identity !== undefined) args.actorIdentity = r.actor_identity;
      run.resume(args);
      return;
    }
    let action = run.next() as unknown as Record<string, Json>;
    expect(action.run_id, `entry ${i}: run_id`).toBe('run-1');
    if (mode === 'drain') action = withTaken(action, taken);
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
  return { run, taken };
}

const SUPPORTED = (f: Record<string, Json>) => !('catalogs' in f) && !('agents' in f);

describe('runtime fixtures through the core', () => {
  for (const [path, f] of Object.entries(FIXTURES)) {
    const name = path.split('/').pop() as string;
    const labels: Record<Replay, string> = {
      plain: '',
      restore: ' (restored before every entry)',
      drain: ' (trace and records taken before every entry)',
    };
    for (const mode of ['plain', 'restore', 'drain'] as const) {
      it(`${name}${labels[mode]}`, async () => {
        expect(SUPPORTED(f)).toBe(true);
        const ctx = await repositoryContext();
        const { run, taken } = play(ctx, f, mode);
        expect(run.runId()).toBe('run-1');
        const end = withTaken(run.next() as unknown as Record<string, Json>, taken) as Json;
        expect(matches(f.end as Json, end), JSON.stringify(end)).toBe(true);
        if (f.run_record !== undefined) {
          const record = run.runRecord();
          expect(matches(f.run_record as Json, record), JSON.stringify(record)).toBe(true);
        }
        const kinds = new Set((run.trace() as Record<string, Json>[]).map((t) => t.kind));
        if (mode === 'plain') for (const k of f.trace_kinds as string[]) expect(kinds.has(k), k).toBe(true);
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
