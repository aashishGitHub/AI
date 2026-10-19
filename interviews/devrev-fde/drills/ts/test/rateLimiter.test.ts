import { describe, expect, it } from 'vitest';
import { TokenBucket } from '../src/rateLimiter.ts';
import { FakeClock } from './helpers.ts';

const allowed = { allowed: true };
const denied = (retryAfterMs: number) => ({ allowed: false, retryAfterMs });

function setup(capacity = 5, refillEveryMs = 1000) {
  const clock = new FakeClock(10_000);
  const bucket = new TokenBucket({ capacity, refillEveryMs, now: clock.now });
  return { clock, bucket };
}

describe('TokenBucket', () => {
  it('allows a full burst of capacity, then denies with the time to the next token', () => {
    const { bucket } = setup();
    for (let i = 0; i < 5; i++) expect(bucket.tryTake()).toEqual(allowed);
    expect(bucket.tryTake()).toEqual(denied(1000));
  });

  it('denies one millisecond before the refill and allows at the exact boundary', () => {
    const { bucket, clock } = setup();
    for (let i = 0; i < 5; i++) bucket.tryTake();

    clock.advance(999);
    expect(bucket.tryTake()).toEqual(denied(1));
    clock.advance(1);
    expect(bucket.tryTake()).toEqual(allowed);
    expect(bucket.tryTake()).toEqual(denied(1000));
  });

  it('keeps partial credit across a denial instead of resetting the refill timer', () => {
    const { bucket, clock } = setup();
    for (let i = 0; i < 5; i++) bucket.tryTake();

    clock.advance(600);
    expect(bucket.tryTake()).toEqual(denied(400));
    clock.advance(400);
    expect(bucket.tryTake()).toEqual(allowed);
  });

  it('never refills beyond capacity after a long idle period', () => {
    const { bucket, clock } = setup();
    clock.advance(1_000_000);
    for (let i = 0; i < 5; i++) expect(bucket.tryTake()).toEqual(allowed);
    expect(bucket.tryTake()).toEqual(denied(1000));
  });

  it('charges multi-token costs and reports the shortfall', () => {
    const { bucket, clock } = setup();
    expect(bucket.tryTake(3)).toEqual(allowed);
    expect(bucket.tryTake(3)).toEqual(denied(1000));
    clock.advance(1000);
    expect(bucket.tryTake(3)).toEqual(allowed);
  });

  it('rejects a cost that can never be satisfied', () => {
    const { bucket } = setup();
    expect(() => bucket.tryTake(6)).toThrow(RangeError);
  });

  it('ignores a clock that moves backwards', () => {
    const { bucket, clock } = setup();
    for (let i = 0; i < 5; i++) bucket.tryTake();
    clock.advance(-5000);
    expect(bucket.tryTake()).toEqual(denied(1000));
    clock.advance(5000 + 1000);
    expect(bucket.tryTake()).toEqual(allowed);
  });

  it('does not drift with non-divisible refill rates', () => {
    const { bucket, clock } = setup(1, 333);
    expect(bucket.tryTake()).toEqual(allowed);
    clock.advance(332);
    expect(bucket.tryTake()).toEqual(denied(1));
    clock.advance(1);
    expect(bucket.tryTake()).toEqual(allowed);
  });
});
