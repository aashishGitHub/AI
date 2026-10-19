import { describe, expect, it } from 'vitest';
import { FixedWindowCounter, SlidingWindowLog } from '../src/slidingWindow.ts';
import { FakeClock } from './helpers.ts';

const LIMIT = 5;
const WINDOW_MS = 1000;

function pair(start = 0) {
  const clock = new FakeClock(start);
  const options = { limit: LIMIT, windowMs: WINDOW_MS, now: clock.now };
  return { clock, fixed: new FixedWindowCounter(options), log: new SlidingWindowLog(options) };
}

const burst = (limiter: { allow(): boolean }, n: number) =>
  Array.from({ length: n }, () => limiter.allow()).filter(Boolean).length;

describe('both limiters agree away from window edges', () => {
  it('allow up to the limit within a window and deny the rest', () => {
    const { fixed, log } = pair();
    expect(burst(fixed, 8)).toBe(LIMIT);
    expect(burst(log, 8)).toBe(LIMIT);
  });
});

describe('boundary burst: the fixed-window flaw', () => {
  it('fixed window lets 2x the limit through in 2ms across a window edge', () => {
    const { clock, fixed } = pair(999);
    expect(burst(fixed, LIMIT)).toBe(LIMIT);
    clock.advance(1);
    expect(burst(fixed, LIMIT)).toBe(LIMIT);
  });

  it('sliding log holds the line across the same edge', () => {
    const { clock, log } = pair(999);
    expect(burst(log, LIMIT)).toBe(LIMIT);
    clock.advance(1);
    expect(burst(log, LIMIT)).toBe(0);
  });

  it('sliding log admits again exactly when the oldest entries leave the window', () => {
    const { clock, log } = pair(0);
    expect(burst(log, LIMIT)).toBe(LIMIT);
    clock.advance(WINDOW_MS - 1);
    expect(log.allow()).toBe(false);
    clock.advance(1);
    expect(burst(log, LIMIT)).toBe(LIMIT);
  });

  it('sliding log frees slots gradually as individual entries expire', () => {
    const { clock, log } = pair(0);
    for (let i = 0; i < LIMIT; i++) {
      log.allow();
      clock.advance(100);
    }
    expect(log.allow()).toBe(false);
    clock.advance(500);
    expect(log.allow()).toBe(true);
    expect(log.allow()).toBe(false);
  });

  it('denied requests are not logged, so hammering does not extend the lockout', () => {
    const { clock, log } = pair(0);
    burst(log, LIMIT);
    for (let t = 100; t < WINDOW_MS; t += 100) {
      clock.advance(100);
      expect(log.allow()).toBe(false);
    }
    clock.advance(100);
    expect(burst(log, LIMIT)).toBe(LIMIT);
  });
});

describe('fixed window mechanics', () => {
  it('resets the count at the aligned window edge, not WINDOW_MS after the first request', () => {
    const { clock, fixed } = pair(700);
    expect(burst(fixed, LIMIT)).toBe(LIMIT);
    clock.advance(299);
    expect(fixed.allow()).toBe(false);
    clock.advance(1);
    expect(fixed.allow()).toBe(true);
  });
});
