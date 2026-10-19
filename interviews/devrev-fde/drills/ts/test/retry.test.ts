import { describe, expect, it } from 'vitest';
import { HttpError, NetworkError, parseRetryAfter, retry, type RetryOptions } from '../src/retry.ts';
import { mulberry32, scripted } from './helpers.ts';

const NOW = Date.parse('Wed, 21 Oct 2015 07:28:00 GMT');

function harness(overrides: Partial<RetryOptions> = {}) {
  const sleeps: number[] = [];
  const options: RetryOptions = {
    method: 'GET',
    maxAttempts: 4,
    baseMs: 100,
    capMs: 1000,
    sleep: async (ms) => {
      sleeps.push(ms);
    },
    rng: scripted([0.5, 0.5, 0.5, 0.5, 0.5]),
    nowMs: () => NOW,
    ...overrides,
  };
  return { sleeps, options };
}

function failingThenOk(errors: readonly Error[], value = 'ok') {
  const calls: number[] = [];
  const op = async (attempt: number) => {
    calls.push(attempt);
    const err = errors[attempt - 1];
    if (err !== undefined) throw err;
    return value;
  };
  return { op, calls };
}

const status = (code: number, headers: Record<string, string> = {}) => new HttpError(code, new Headers(headers));

describe('retry: backoff arithmetic', () => {
  it('returns immediately without sleeping when the first attempt succeeds', async () => {
    const { sleeps, options } = harness();
    const { op, calls } = failingThenOk([]);
    await expect(retry(op, options)).resolves.toBe('ok');
    expect(calls).toEqual([1]);
    expect(sleeps).toEqual([]);
  });

  it('sleeps rng * min(cap, base * 2^n): full jitter over a doubling ceiling', async () => {
    const { sleeps, options } = harness();
    const { op } = failingThenOk([status(503), status(503), status(503)]);
    await retry(op, options);
    expect(sleeps).toEqual([50, 100, 200]);
  });

  it('clamps the ceiling at capMs', async () => {
    const { sleeps, options } = harness({ maxAttempts: 6, capMs: 300 });
    const { op } = failingThenOk([status(500), status(500), status(500), status(500), status(500)]);
    await retry(op, options);
    expect(sleeps).toEqual([50, 100, 150, 150, 150]);
  });

  it('can sleep zero (rng 0) and stays strictly below the ceiling (rng just under 1)', async () => {
    const { sleeps, options } = harness({ rng: scripted([0, 0.999999]) });
    const { op } = failingThenOk([status(500), status(500)]);
    await retry(op, options);
    expect(sleeps).toEqual([0, 199]);
  });

  it('is fully determined by a seeded rng', async () => {
    const expectedDraws = mulberry32(42);
    const expected = [100, 200, 400].map((ceiling) => Math.floor(expectedDraws() * ceiling));

    const { sleeps, options } = harness({ rng: mulberry32(42), capMs: 10_000 });
    const { op } = failingThenOk([status(503), status(503), status(503)]);
    await retry(op, options);
    expect(sleeps).toEqual(expected);
  });
});

describe('retry: Retry-After', () => {
  it('treats seconds as a floor over the jittered delay', async () => {
    const { sleeps, options } = harness();
    const { op } = failingThenOk([status(429, { 'Retry-After': '2' }), status(429, { 'retry-after': '0' })]);
    await retry(op, options);
    expect(sleeps).toEqual([2000, 100]);
  });

  it('lets the jittered delay win when it is larger than the hint', async () => {
    const { sleeps, options } = harness({ rng: scripted([0.999]), baseMs: 10_000, capMs: 10_000 });
    const { op } = failingThenOk([status(503, { 'retry-after': '1' })]);
    await retry(op, options);
    expect(sleeps).toEqual([9990]);
  });

  it('honours an HTTP-date relative to the injected clock', async () => {
    const { sleeps, options } = harness();
    const { op } = failingThenOk([status(503, { 'retry-after': 'Wed, 21 Oct 2015 07:28:05 GMT' })]);
    await retry(op, options);
    expect(sleeps).toEqual([5000]);
  });

  it.each([
    ['an HTTP-date in the past', 'Wed, 21 Oct 2015 07:27:00 GMT', 0],
    ['garbage', 'soon', undefined],
    ['garbage Date.parse would accept', 'foo 3', undefined],
    ['a negative number', '-5', undefined],
    ['a fractional number', '1.5', undefined],
    ['an absurdly long number', '9'.repeat(400), undefined],
  ])('parseRetryAfter: %s', (_label, value, expected) => {
    expect(parseRetryAfter(value, NOW)).toBe(expected);
  });

  it('parseRetryAfter: absent header', () => {
    expect(parseRetryAfter(null, NOW)).toBeUndefined();
  });
});

describe('retry: what is retried', () => {
  it('gives up after maxAttempts and rethrows the last error', async () => {
    const { sleeps, options } = harness({ maxAttempts: 3 });
    const last = status(502);
    const { op, calls } = failingThenOk([status(503), status(503), last, status(503)]);
    await expect(retry(op, options)).rejects.toBe(last);
    expect(calls).toEqual([1, 2, 3]);
    expect(sleeps).toHaveLength(2);
  });

  it.each([400, 401, 404, 409, 422])('does not retry %i', async (code) => {
    const { sleeps, options } = harness();
    const { op, calls } = failingThenOk([status(code)]);
    await expect(retry(op, options)).rejects.toBeInstanceOf(HttpError);
    expect(calls).toEqual([1]);
    expect(sleeps).toEqual([]);
  });

  it.each([429, 500, 502, 503, 504, 599])('retries %i', async (code) => {
    const { options } = harness();
    const { op, calls } = failingThenOk([status(code)]);
    await retry(op, options);
    expect(calls).toEqual([1, 2]);
  });

  it('retries network errors but not programmer errors', async () => {
    const { options } = harness();
    const net = failingThenOk([new NetworkError('ECONNRESET')]);
    await retry(net.op, options);
    expect(net.calls).toEqual([1, 2]);

    const bug = failingThenOk([new TypeError('x is undefined')]);
    await expect(retry(bug.op, options)).rejects.toBeInstanceOf(TypeError);
    expect(bug.calls).toEqual([1]);
  });
});

describe('retry: idempotency gate', () => {
  it('never retries POST without an idempotency key, even on 503', async () => {
    const { sleeps, options } = harness({ method: 'POST' });
    const { op, calls } = failingThenOk([status(503)]);
    await expect(retry(op, options)).rejects.toBeInstanceOf(HttpError);
    expect(calls).toEqual([1]);
    expect(sleeps).toEqual([]);
  });

  it('never retries a POST network error without a key', async () => {
    const { options } = harness({ method: 'post' });
    const { op, calls } = failingThenOk([new NetworkError('reset')]);
    await expect(retry(op, options)).rejects.toBeInstanceOf(NetworkError);
    expect(calls).toEqual([1]);
  });

  it('retries POST once it carries an idempotency key', async () => {
    const { options } = harness({ method: 'POST', idempotencyKey: 'req-123' });
    const { op, calls } = failingThenOk([status(503)]);
    await retry(op, options);
    expect(calls).toEqual([1, 2]);
  });

  it.each(['PUT', 'DELETE', 'get'])('retries inherently idempotent %s', async (method) => {
    const { options } = harness({ method });
    const { op, calls } = failingThenOk([status(500)]);
    await retry(op, options);
    expect(calls).toEqual([1, 2]);
  });
});
