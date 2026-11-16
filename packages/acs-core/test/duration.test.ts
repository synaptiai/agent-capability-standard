// Durations (Standard 1.2.0 section 5.10.1) in whole milliseconds, rounded
// up: the `ttl` cases of the memory vectors and the validator's W614 cases.
import { describe, expect, it } from 'vitest';
import { parseDurationMs } from '../src/duration.js';

describe('parseDurationMs', () => {
  it.each([
    ['250ms', 250],
    ['1s', 1000],
    ['30s', 30_000],
    ['5m', 300_000],
    ['2h', 7_200_000],
    ['1d', 86_400_000],
    ['0s', 0],
    ['PT1H30M', 5_400_000],
    ['P1D', 86_400_000],
    ['P1DT2H', 93_600_000],
    ['PT0.5S', 500],
    ['PT1M0.25S', 60_250],
    ['PT0.0005S', 1],
    ['P365D', 31_536_000_000],
  ] as const)('%s is %d ms', (text, ms) => {
    expect(parseDurationMs(text)).toBe(ms);
  });
  it.each([
    'five fortnights',
    '',
    '1w',
    'P1Y',
    'P1M',
    'P1W',
    'PT',
    'P',
    'PT1.S',
    'PT0.0000000001S',
    'PT1.5M',
    '1.5s',
    '-1s',
    ' 1s',
    'PT30M1H',
  ])('%j is not a duration', (text) => {
    expect(parseDurationMs(text)).toBeNull();
  });
  it('refuses what has no exact number of milliseconds', () => {
    expect(parseDurationMs(`${Number.MAX_SAFE_INTEGER}ms`)).toBe(Number.MAX_SAFE_INTEGER);
    expect(parseDurationMs(`${Number.MAX_SAFE_INTEGER + 1}ms`)).toBeNull();
  });
});
