/**
 * Durations (Agent Capability Standard 1.2.0, section 5.10.1): a number
 * with a unit, `<digits>(ms|s|m|h|d)`, or an ISO 8601 day-time duration
 * `P[nD][T[nH][nM][n[.n]S]]` (no years, months or weeks, whose length
 * varies; a fraction on seconds only, at most nine digits). The grammar of
 * the core's `duration.rs`, for a `ttl` (section 4.5) in a host that does
 * not call the core.
 */

const NANOS_PER_MS = 1_000_000n;

/** A run of ASCII digits (at least one) as a bigint, or null. */
function whole(s: string): bigint | null {
  return /^[0-9]+$/.test(s) ? BigInt(s) : null;
}

/** Nanoseconds of `[nD][T[nH][nM][n[.n]S]]` (after the `P`), or null when
 * malformed. */
function isoNanos(s: string): bigint | null {
  const t = s.indexOf('T');
  const date = t >= 0 ? s.slice(0, t) : s;
  let time = t >= 0 ? s.slice(t + 1) : null;
  let total = 0n;
  let components = 0;
  if (date.length > 0) {
    if (!date.endsWith('D')) return null;
    const days = whole(date.slice(0, -1));
    if (days === null) return null;
    total += days * 86_400n * 1_000_000_000n;
    components += 1;
  }
  if (time !== null) {
    const before = components;
    for (const [unit, scale] of [
      ['H', 3_600n],
      ['M', 60n],
    ] as const) {
      const i = time.indexOf(unit);
      if (i >= 0) {
        const n = whole(time.slice(0, i));
        if (n === null) return null;
        total += n * scale * 1_000_000_000n;
        time = time.slice(i + 1);
        components += 1;
      }
    }
    if (time.endsWith('S')) {
      const secs = time.slice(0, -1);
      const dot = secs.indexOf('.');
      const int = whole(dot >= 0 ? secs.slice(0, dot) : secs);
      if (int === null) return null;
      total += int * 1_000_000_000n;
      if (dot >= 0) {
        const frac = secs.slice(dot + 1);
        if (frac.length === 0 || frac.length > 9 || !/^[0-9]+$/.test(frac)) return null;
        total += BigInt(frac.padEnd(9, '0'));
      }
      components += 1;
    } else if (time.length > 0) {
      return null;
    }
    if (components === before) return null;
  }
  return components === 0 ? null : total;
}

/**
 * A duration in whole milliseconds, rounded up (so `PT0.0005S` is 1 ms and
 * only a zero duration is 0), as the core's `duration_ms`; null when `text`
 * is not a duration, or is longer than `Number.MAX_SAFE_INTEGER`
 * milliseconds.
 */
export function parseDurationMs(text: string): number | null {
  let nanos: bigint | null;
  if (text.startsWith('P')) {
    nanos = isoNanos(text.slice(1));
  } else {
    const m = /^([0-9]+)(ms|s|m|h|d)$/.exec(text);
    if (m === null) return null;
    const per = { ms: 1n, s: 1_000n, m: 60_000n, h: 3_600_000n, d: 86_400_000n }[m[2] as 'ms' | 's' | 'm' | 'h' | 'd'];
    nanos = BigInt(m[1] as string) * per * NANOS_PER_MS;
  }
  if (nanos === null) return null;
  const ms = (nanos + NANOS_PER_MS - 1n) / NANOS_PER_MS;
  return ms > BigInt(Number.MAX_SAFE_INTEGER) ? null : Number(ms);
}
