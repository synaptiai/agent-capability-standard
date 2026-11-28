/**
 * Watching a wait's liveness (Agent Capability Standard 1.2.0, sections
 * 5.13 and 5.19.3): the host's side. The executor does not schedule
 * heartbeats or probes: a wait with `liveness` leaves them to the host,
 * which answers `{ kind: 'LivenessLost' }` to the `AwaitEvent` action once
 * the source has missed `failure_threshold` heartbeats or probes,
 * `interval` apart. The step then fails with R406.
 *
 * - `push` (the source sends heartbeats): a heartbeat is due `interval`
 *   after the last one (or after the wait began). One that has not arrived
 *   by then is missed; one that arrives at its due time is in time, as an
 *   event at a deadline is. Each further `interval` without one is another
 *   miss.
 * - `probe` (the host polls the source every `interval`): each probe that
 *   fails or goes unanswered is a miss (`probeFailed`).
 *
 * A heartbeat, or a probe the source answers, sets the count back to zero,
 * so a source that misses fewer than `failure_threshold` in a row is never
 * reported lost. Once the count reaches `failure_threshold` the loss is
 * kept, with the time it happened (`lostAt`): a later heartbeat does not
 * undo it, and a host that compares that time with the wait's deadline can
 * tell R406 from R401. A wait run again by a loop or a `retry` is a new
 * wait: give it a new watcher. Times are milliseconds on the run's clock.
 * The same rules as `grounded_agency.workflows.LivenessWatcher`.
 */
import { parseDurationMs } from './duration.js';

/** A wait's `liveness` member, as the `AwaitEvent` action carries it. */
export interface Liveness {
  mode: 'push' | 'probe';
  interval: string;
  failure_threshold?: number | null;
}

export const DEFAULT_FAILURE_THRESHOLD = 3;

function checkTime(value: number): void {
  if (!Number.isSafeInteger(value)) {
    throw new RangeError(`a time is whole milliseconds, not ${String(value)}`);
  }
}

export class LivenessWatcher {
  readonly mode: 'push' | 'probe';
  readonly intervalMs: number;
  readonly failureThreshold: number;
  // The last time the source answered (or the wait began), the probes that
  // failed since (probe mode), and when the source was lost.
  #lastMs: number;
  #failedProbes = 0;
  #lostAt: number | null = null;

  /**
   * `liveness` is the wait's `liveness` member; `startedMs` is when the
   * wait began: the first heartbeat or probe is due `interval` after it.
   * Throws a `RangeError` for a `liveness` no valid workflow holds.
   */
  constructor(liveness: Liveness, startedMs: number) {
    const { mode, interval } = liveness;
    if (mode !== 'push' && mode !== 'probe') {
      throw new RangeError(`liveness mode must be push or probe, not ${String(mode)}`);
    }
    const intervalMs = typeof interval === 'string' ? parseDurationMs(interval) : null;
    if (intervalMs === null) {
      throw new RangeError(`liveness interval must be a duration, not ${String(interval)}`);
    }
    if (intervalMs <= 0) {
      throw new RangeError(`liveness interval must be longer than zero, not ${interval}`);
    }
    const threshold = liveness.failure_threshold ?? DEFAULT_FAILURE_THRESHOLD;
    if (!Number.isSafeInteger(threshold) || threshold < 1) {
      throw new RangeError(
        `liveness failure_threshold must be an integer of at least 1, not ${String(threshold)}`,
      );
    }
    checkTime(startedMs);
    this.mode = mode;
    this.intervalMs = intervalMs;
    this.failureThreshold = threshold;
    this.#lastMs = startedMs;
  }

  /** A watcher for an `AwaitEvent` action's wait, or null when it has no `liveness`. */
  static forAction(action: { liveness?: Liveness | null }, startedMs: number): LivenessWatcher | null {
    return action.liveness == null ? null : new LivenessWatcher(action.liveness, startedMs);
  }

  /**
   * The source answered at `atMs`: a heartbeat arrived (`push`) or a probe
   * succeeded (`probe`). The count goes back to zero, and the next heartbeat
   * or probe is due `interval` later. A loss already reached is kept.
   */
  heartbeat(atMs: number): void {
    this.#advance(atMs);
    this.#lastMs = atMs;
    this.#failedProbes = 0;
  }

  /** A probe at `atMs` failed or went unanswered (`probe` mode only): one more miss. */
  probeFailed(atMs: number): void {
    if (this.mode !== 'probe') throw new RangeError('probeFailed is for liveness mode probe');
    this.#advance(atMs);
    this.#lastMs = atMs;
    this.#failedProbes += 1;
    if (this.#failedProbes >= this.failureThreshold && this.#lostAt === null) this.#lostAt = atMs;
  }

  /**
   * The consecutive misses at `nowMs`: in `push` mode the heartbeats due
   * before `nowMs` since the source last answered (one due at `nowMs` is
   * not missed yet); in `probe` mode the probes that failed since.
   */
  misses(nowMs: number): number {
    checkTime(nowMs);
    if (nowMs < this.#lastMs) {
      throw new RangeError(`time ${nowMs} is before the last one recorded (${this.#lastMs})`);
    }
    if (this.mode === 'probe') return this.#failedProbes;
    if (nowMs === this.#lastMs) return 0;
    return Math.floor((nowMs - this.#lastMs - 1) / this.intervalMs);
  }

  /** When the source was lost, if it was by `nowMs`; else null. */
  lostAt(nowMs: number): number | null {
    this.#advance(nowMs);
    return this.#lostAt;
  }

  /** Whether the source was lost by `nowMs`. */
  lost(nowMs: number): boolean {
    return this.lostAt(nowMs) !== null;
  }

  /**
   * When to look again, never before `nowMs`: in `probe` mode when the next
   * probe is due, or `nowMs` when that time has passed (probe now); in `push`
   * mode when the next miss is counted, 1 ms after the next heartbeat is due,
   * which is always after `nowMs`.
   */
  nextCheckMs(nowMs: number): number {
    const misses = this.misses(nowMs);
    if (this.mode === 'probe') return Math.max(this.#lastMs + this.intervalMs, nowMs);
    return this.#lastMs + (misses + 1) * this.intervalMs + 1;
  }

  /** The answer to the `AwaitEvent` action at `nowMs`: `LivenessLost` once the source is lost, else null. */
  response(nowMs: number): { kind: 'LivenessLost' } | null {
    return this.lost(nowMs) ? { kind: 'LivenessLost' } : null;
  }

  #advance(nowMs: number): void {
    const misses = this.misses(nowMs);
    if (this.#lostAt === null && this.mode === 'push' && misses >= this.failureThreshold) {
      this.#lostAt = this.#lastMs + this.failureThreshold * this.intervalMs + 1;
    }
  }
}
