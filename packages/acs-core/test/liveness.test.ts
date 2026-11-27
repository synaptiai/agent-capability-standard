// The reference liveness watcher (Standard 1.2.0 sections 5.13 and 5.19.3):
// a source is reported lost only after `failure_threshold` consecutive
// misses, and a heartbeat or an answered probe sets the count back to zero.
// tests/test_liveness_watcher.py holds the same cases for the Python watcher.
import { describe, expect, it } from 'vitest';
import { LivenessWatcher, type Liveness } from '../src/liveness.js';

const MIN = 60_000;

function push(threshold: number | null = 3): LivenessWatcher {
  return new LivenessWatcher({ mode: 'push', interval: '1m', failure_threshold: threshold }, 0);
}

describe('LivenessWatcher in push mode', () => {
  it('never reports a source that misses one heartbeat and recovers', () => {
    const w = push();
    expect(w.misses(MIN)).toBe(0); // due at 1m: in time
    expect(w.misses(MIN + 1)).toBe(1);
    expect(w.response(MIN + 1)).toBeNull();
    w.heartbeat(MIN + 30_000);
    expect(w.misses(MIN + 30_000)).toBe(0);
    expect(w.misses(3 * MIN + 30_000 + 1)).toBe(2);
    expect(w.lost(3 * MIN + 30_000 + 1)).toBe(false);
    w.heartbeat(3 * MIN + 40_000);
    expect(w.response(5 * MIN)).toBeNull();
    expect(w.lostAt(5 * MIN)).toBeNull();
  });

  it('reports a source that keeps missing at its third miss', () => {
    const w = push();
    expect(w.misses(3 * MIN)).toBe(2);
    expect(w.response(3 * MIN)).toBeNull();
    expect(w.misses(3 * MIN + 1)).toBe(3);
    expect(w.response(3 * MIN + 1)).toEqual({ kind: 'LivenessLost' });
    expect(w.lostAt(5 * MIN)).toBe(3 * MIN + 1);
  });

  it('keeps a loss a later heartbeat would hide', () => {
    const w = push();
    w.heartbeat(10 * MIN);
    expect(w.lost(10 * MIN)).toBe(true);
    expect(w.lostAt(10 * MIN)).toBe(3 * MIN + 1);
    expect(w.misses(10 * MIN)).toBe(0);
  });

  it('defaults the threshold to three, and a threshold of one is lost at the first miss', () => {
    const w = push(null);
    expect(w.failureThreshold).toBe(3);
    expect(w.lost(3 * MIN)).toBe(false);
    expect(w.lost(3 * MIN + 1)).toBe(true);
    const one = push(1);
    expect(one.lost(MIN)).toBe(false);
    expect(one.lost(MIN + 1)).toBe(true);
  });

  it('says when the next miss is counted', () => {
    const w = push();
    expect(w.nextCheckMs(0)).toBe(MIN + 1);
    expect(w.nextCheckMs(MIN + 1)).toBe(2 * MIN + 1);
    w.heartbeat(MIN + 500);
    expect(w.nextCheckMs(MIN + 500)).toBe(2 * MIN + 501);
  });

  it('counts from when the wait began', () => {
    const w = new LivenessWatcher({ mode: 'push', interval: '10s' }, 1_000_000);
    expect(w.misses(1_010_000)).toBe(0);
    expect(w.misses(1_010_001)).toBe(1);
    expect(w.lostAt(1_030_001)).toBe(1_030_001);
  });

  it('takes no failed probe', () => {
    expect(() => push().probeFailed(MIN)).toThrow(/probe/);
  });
});

describe('LivenessWatcher in probe mode', () => {
  const probe = () => new LivenessWatcher({ mode: 'probe', interval: '10m', failure_threshold: 3 }, 0);

  it('never reports a source that fails one probe and recovers', () => {
    const w = probe();
    expect(w.nextCheckMs(0)).toBe(10 * MIN);
    w.probeFailed(10 * MIN);
    expect(w.misses(10 * MIN)).toBe(1);
    w.heartbeat(20 * MIN);
    expect(w.misses(20 * MIN)).toBe(0);
    w.probeFailed(30 * MIN);
    w.probeFailed(40 * MIN);
    expect(w.misses(40 * MIN)).toBe(2);
    expect(w.response(40 * MIN)).toBeNull();
    w.heartbeat(50 * MIN);
    // Time alone counts nothing in probe mode.
    expect(w.response(500 * MIN)).toBeNull();
  });

  it('reports a source that keeps failing at its third probe', () => {
    const w = probe();
    for (const k of [1, 2]) {
      w.probeFailed(k * 10 * MIN);
      expect(w.response(k * 10 * MIN)).toBeNull();
    }
    expect(w.nextCheckMs(20 * MIN)).toBe(30 * MIN);
    w.probeFailed(30 * MIN);
    expect(w.response(30 * MIN)).toEqual({ kind: 'LivenessLost' });
    expect(w.lostAt(30 * MIN)).toBe(30 * MIN);
    w.heartbeat(40 * MIN);
    expect(w.lost(40 * MIN)).toBe(true);
  });
});

describe('LivenessWatcher construction', () => {
  it("reads an AwaitEvent action's wait, and gives null without liveness", () => {
    const w = LivenessWatcher.forAction({ liveness: { mode: 'probe', interval: 'PT30S', failure_threshold: 2 } }, 5);
    expect(w && [w.mode, w.intervalMs, w.failureThreshold]).toEqual(['probe', 30_000, 2]);
    expect(LivenessWatcher.forAction({ liveness: null }, 0)).toBeNull();
    expect(LivenessWatcher.forAction({}, 0)).toBeNull();
  });

  it.each([
    { mode: 'poll', interval: '1m' },
    { interval: '1m' },
    { mode: 'push' },
    { mode: 'push', interval: 60 },
    { mode: 'push', interval: 'a minute' },
    { mode: 'push', interval: '0s' },
    { mode: 'push', interval: '1m', failure_threshold: 0 },
    { mode: 'push', interval: '1m', failure_threshold: 2.5 },
  ])('refuses %j', (liveness) => {
    expect(() => new LivenessWatcher(liveness as unknown as Liveness, 0)).toThrow(RangeError);
  });

  it('refuses a time that goes back', () => {
    const w = push();
    w.heartbeat(MIN);
    expect(() => w.misses(MIN - 1)).toThrow(/before/);
    expect(() => w.heartbeat(MIN - 1)).toThrow(/before/);
    expect(() => w.misses(1.5)).toThrow(/milliseconds/);
  });
});
