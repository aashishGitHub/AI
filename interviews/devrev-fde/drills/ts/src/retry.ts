import type { Clock } from './types.ts';

export class HttpError extends Error {
  readonly status: number;
  readonly headers: Headers;

  constructor(status: number, headers: Headers = new Headers()) {
    super(`HTTP ${status}`);
    this.status = status;
    this.headers = headers;
  }
}

export class NetworkError extends Error {}

export interface RetryOptions {
  readonly method: string;
  readonly idempotencyKey?: string;
  readonly maxAttempts: number;
  readonly baseMs: number;
  readonly capMs: number;
  readonly sleep: (ms: number) => Promise<void>;
  readonly rng: () => number;
  readonly nowMs: Clock;
}

const IDEMPOTENT_METHODS = new Set(['GET', 'HEAD', 'OPTIONS', 'TRACE', 'PUT', 'DELETE']);
const IMF_FIXDATE = /^[A-Za-z]{3}, \d{2} [A-Za-z]{3} \d{4} \d{2}:\d{2}:\d{2} GMT$/;

export function parseRetryAfter(value: string | null, nowMs: number): number | undefined {
  if (value === null) return undefined;
  if (/^\d{1,9}$/.test(value)) return Number(value) * 1000;
  // Date.parse accepts garbage like "foo 3", so gate it on the strict HTTP-date shape.
  if (!IMF_FIXDATE.test(value)) return undefined;
  const at = Date.parse(value);
  return Number.isNaN(at) ? undefined : Math.max(0, at - nowMs);
}

function isRetryable(err: unknown): boolean {
  if (err instanceof NetworkError) return true;
  return err instanceof HttpError && (err.status === 429 || (err.status >= 500 && err.status <= 599));
}

export async function retry<T>(op: (attempt: number) => Promise<T>, o: RetryOptions): Promise<T> {
  const safeToRepeat = IDEMPOTENT_METHODS.has(o.method.toUpperCase()) || o.idempotencyKey !== undefined;

  for (let attempt = 1; ; attempt++) {
    try {
      return await op(attempt);
    } catch (err) {
      if (!safeToRepeat || !isRetryable(err) || attempt >= o.maxAttempts) throw err;

      const ceiling = Math.min(o.capMs, o.baseMs * 2 ** (attempt - 1));
      const jittered = Math.floor(o.rng() * ceiling);
      const hinted =
        err instanceof HttpError ? (parseRetryAfter(err.headers.get('retry-after'), o.nowMs()) ?? 0) : 0;
      await o.sleep(Math.max(jittered, hinted));
    }
  }
}
