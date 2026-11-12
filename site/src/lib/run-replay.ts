// A runtime conformance fixture read as a run (visual spec 3.0, RunReplay):
// the fixture's own workflow, parsed with the site's catalog parser (so a
// fixture whose workflow no longer parses fails the build), and what its
// `script` and `end` record for each step. The conformance suite runs these
// files against the executor, so the picture shows behaviour that is tested.
//
// Each script entry is one request the executor made to the host. An entry
// names its step when it carries `expect.step` (0-based); otherwise it is the
// next step at or after the run's position that uses the expected capability
// (or, for an AwaitEvent, that waits), and failing that the first such step
// from the top: a loop went back. Steps are numbered from 1 here.
import { loadOntology } from '../data/ontology';
import { parseCatalog, type Step, type Workflow } from '../data/workflows';
import { loadRuntimeFixture, type RuntimeFixture } from '../data/spec-sources';

/** The fixtures the site draws, by the figure that draws them (visual spec 3.9). */
export const REPLAY_FIXTURES: Readonly<Record<string, string>> = {
  'recovery-replay': 'recovery_loop_exhausted',
  'wait-replay': 'wait_liveness_lost',
  'deferral-replay': 'deferral_defers_effects',
};

export type ReplayStatus = 'ran' | 'deferred' | 'skipped' | 'not-reached';

export interface ReplayStep {
  /** 1-based. */
  n: number;
  step: Step;
  status: ReplayStatus;
  /** How many requests the script made for this step. */
  requests: number;
  /** What the host answered, in order (respond.kind of each request). */
  answers: string[];
  /** Why the step was deferred, from the fixture's `end.deferred`, or what deferred it. */
  reason: string | null;
  /** How many times a failure mode of this step fired: once per loop back from it, plus once when its loops ran out. */
  fired: number;
  /** The condition of the failure mode that fired, or null. */
  condition: string | null;
}

export interface ReplayLoop {
  /** 1-based step numbers: the step whose failure mode looped, and the step it went back to. */
  from: number;
  to: number;
  /** The loop's number among the loops from this step (1, 2, ...). */
  count: number;
  /** max_loops of the failure mode whose recovery names the target, or null when none does. */
  maxLoops: number | null;
}

/** A failure mode whose loops ran out (trace kind recovery_exhausted, or an R404 end). */
export interface ReplayExhausted {
  /** 1-based step whose loops ran out. */
  from: number;
  /** 1-based step of its on_exhausted handler, or null when it has none. */
  handler: number | null;
}

export interface Replay {
  fixture: RuntimeFixture;
  wf: Workflow;
  steps: ReplayStep[];
  loops: ReplayLoop[];
  exhausted: ReplayExhausted | null;
  /** The run's end: `Failed` with a code, or `Completed` with an outcome. */
  end: { kind: string; code: string | null; outcome: string | null };
}

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);

/** Which step (0-based) a script entry is for, given the run's position. Throws when none fits. */
function stepOf(entry: RuntimeFixture['script'][number], steps: Step[], cursor: number, last: number, where: string): number {
  const e = entry.expect;
  if (typeof e.step === 'number') {
    if (!steps[e.step]) throw new Error(`${where}: script names step ${e.step}, which the workflow does not have`);
    return e.step;
  }
  let fits: (s: Step) => boolean;
  let from = cursor;
  if (typeof e.capability === 'string') fits = (s) => s.capability === e.capability;
  else if (e.kind === 'AwaitEvent') {
    fits = (s) => isObj(s.extra.wait);
    from = Math.max(0, last);
  } else throw new Error(`${where}: a ${e.kind} request names no capability or step`);
  const ahead = steps.findIndex((s, i) => i >= from && fits(s));
  if (ahead !== -1) return ahead;
  const back = steps.findIndex(fits);
  if (back === -1) throw new Error(`${where}: no step fits the ${e.kind} request${e.capability ? ` for ${e.capability}` : ''}`);
  return back;
}

/** The failure mode of `from` whose recovery goes back to `to`'s store, or null. */
function loopingMode(from: Step, to: Step): Obj | null {
  for (const fm of from.failure_modes ?? []) {
    if (isObj(fm) && isObj(fm.recovery) && fm.recovery.goto_step === to.store_as) return fm;
  }
  return null;
}

/** max_loops of a failure mode of `from` whose recovery goes back to `to`'s store (1, the §5.12 default, when it sets none). */
function maxLoopsOf(from: Step, to: Step): number | null {
  const fm = loopingMode(from, to);
  if (!fm) return null;
  const r = fm.recovery as Obj;
  return typeof r.max_loops === 'number' ? r.max_loops : 1;
}

/** Why a step with no reason in `end.deferred` was deferred: its own approval plan in an unattended run. */
function ownDeferral(step: Step, attendance: string): string | null {
  const a = step.extra.approval;
  if (isObj(a) && isObj(a.approver) && a.approver.kind === 'human' && a.when_unattended === 'defer_to_queue' && attendance === 'unattended') {
    return 'a human approver is not asked in an unattended run, and its plan is defer_to_queue';
  }
  return null;
}

export function replay(name: string): Replay {
  const fixture = loadRuntimeFixture(name);
  const where = fixture.file;
  const one = { [fixture.workflow]: fixture.catalog[fixture.workflow] };
  let wf: Workflow;
  try {
    wf = parseCatalog(where, JSON.stringify(one), 'core', loadOntology())[0]!;
  } catch (e) {
    throw new Error(`${where}: its workflow no longer parses: ${(e as Error).message}`);
  }
  const steps = wf.steps;
  const requests = steps.map(() => 0);
  const answers: string[][] = steps.map(() => []);
  const loops: ReplayLoop[] = [];
  let cursor = fixture.start;
  let last = -1;
  for (const entry of fixture.script) {
    const i = stepOf(entry, steps, cursor, last, where);
    if (last !== -1 && i < last) {
      const count = loops.filter((l) => l.from === last + 1 && l.to === i + 1).length + 1;
      loops.push({ from: last + 1, to: i + 1, count, maxLoops: maxLoopsOf(steps[last]!, steps[i]!) });
    }
    requests[i]!++;
    answers[i]!.push(entry.respond.kind);
    last = i;
    cursor = i + 1;
  }
  // A failure mode's loops ran out: the fixture traces it, or the run ends R404 (§5.12).
  const lastLoop = loops.at(-1);
  let exhausted: ReplayExhausted | null = null;
  if (lastLoop && (fixture.traceKinds.includes('recovery_exhausted') || fixture.end.code === 'R404')) {
    const fm = loopingMode(steps[lastLoop.from - 1]!, steps[lastLoop.to - 1]!);
    const target = fm && isObj(fm.recovery) && isObj(fm.recovery.on_exhausted) ? fm.recovery.on_exhausted.goto_step : null;
    const h = typeof target === 'string' ? steps.findIndex((x) => x.store_as === target) : -1;
    if (typeof target === 'string' && h === -1) throw new Error(`${where}: on_exhausted names ${target}, which no step stores`);
    exhausted = { from: lastLoop.from, handler: h === -1 ? null : h + 1 };
  }
  const deferred = new Map((fixture.end.deferred ?? []).map((d) => [d.step, d.reason ?? null]));
  for (const k of deferred.keys()) if (!steps[k]) throw new Error(`${where}: end.deferred names step ${k}, which the workflow does not have`);
  const failed = fixture.end.kind === 'Failed';
  const lastRan = requests.reduce((acc, r, i) => (r > 0 ? i : acc), -1);
  const out: ReplayStep[] = steps.map((step, i) => {
    let status: ReplayStatus;
    let reason: string | null = null;
    if (deferred.has(i)) {
      status = 'deferred';
      reason = deferred.get(i) ?? ownDeferral(step, fixture.attendance);
      if (!reason) throw new Error(`${where}: step ${i} is deferred with no reason the fixture gives`);
    } else if (requests[i]! > 0) status = 'ran';
    else if (failed && i > lastRan) status = 'not-reached';
    else status = 'skipped';
    const fired = loops.filter((l) => l.from === i + 1).length + (exhausted?.from === i + 1 ? 1 : 0);
    const mode = fired > 0 ? loopingMode(step, steps[loops.find((l) => l.from === i + 1)!.to - 1]!) : null;
    const condition = mode && typeof mode.condition === 'string' ? mode.condition : null;
    return { n: i + 1, step, status, requests: requests[i]!, answers: answers[i]!, reason, fired, condition };
  });
  const end = {
    kind: fixture.end.kind,
    code: typeof fixture.end.code === 'string' ? fixture.end.code : null,
    outcome: typeof fixture.end.outcome === 'string' ? fixture.end.outcome : null,
  };
  if (!end.code && !end.outcome) throw new Error(`${where}: end has neither a code nor an outcome`);
  return { fixture, wf, steps: out, loops, exhausted, end };
}

/** What the host answered, in words. */
export const ANSWER_WORDS: Readonly<Record<string, string>> = {
  Output: 'returned an output',
  LivenessLost: 'the source stopped answering',
};

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** One sentence for the figure's caption and its Markdown copy. */
export function replayCaption(r: Replay): string {
  const count = (s: ReplayStatus) => r.steps.filter((x) => x.status === s).length;
  const parts = [
    `${plural(count('ran'), 'step ran', 'steps ran')}`,
    ...(count('deferred') > 0 ? [`${count('deferred')} deferred`] : []),
    ...(count('skipped') > 0 ? [`${count('skipped')} skipped`] : []),
    ...(count('not-reached') > 0 ? [`${count('not-reached')} not reached`] : []),
  ];
  const loops = r.loops.length > 0 ? `, after ${plural(r.loops.length, 'loop', 'loops')} back` : '';
  const end = r.end.code ? `fails with ${r.end.code}` : `ends ${r.end.outcome}`;
  return `In the conformance fixture ${r.fixture.name}, ${parts.join(', ')}${loops}, and the run ${end}.`;
}

/** Why a step's row reads as it does: its deferral reason, or what the host answered and how often its failure mode fired. */
export function stepWhy(s: ReplayStep): string {
  if (s.reason) return s.reason;
  const said = [...new Set(s.answers.map((a) => ANSWER_WORDS[a] ?? a))].join('; ');
  const fired = s.fired > 0 ? `its failure mode${s.condition ? ` "${s.condition}"` : ''} fired ${s.fired === 1 ? 'once' : `${s.fired} times`}` : '';
  return [said, fired].filter(Boolean).join('; ');
}

/** The exit when a failure mode's loops ran out, in words. */
export function exhaustedWords(r: Replay): string | null {
  const x = r.exhausted;
  if (!x) return null;
  const loop = r.loops.filter((l) => l.from === x.from).at(-1)!;
  const handler = x.handler === null ? 'it has no on_exhausted handler' : `on_exhausted runs step ${x.handler}${r.steps[x.handler - 1]!.step.store_as ? ` (${r.steps[x.handler - 1]!.step.store_as})` : ''}`;
  return `Loops run out at step ${x.from} (max_loops ${loop.maxLoops ?? 1}): ${handler}, cause R404`;
}

/** The replay as rows for the Markdown copy. */
export function replayRows(r: Replay): string[][] {
  return r.steps.map((s) => [
    String(s.n),
    s.step.capability,
    s.step.store_as ?? '',
    s.status === 'ran' ? (s.requests > 1 ? `ran ${s.requests} times` : 'ran') : s.status === 'not-reached' ? 'not reached' : s.status,
    stepWhy(s),
  ]);
}
