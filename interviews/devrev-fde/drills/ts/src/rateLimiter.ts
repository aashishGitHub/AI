import type { Clock } from './types.ts';

export type Decision =
  | { readonly allowed: true }
  | { readonly allowed: false; readonly retryAfterMs: number };

export interface TokenBucketOptions {
  readonly capacity: number;
  readonly refillEveryMs: number;
  readonly now: Clock;
}

export class TokenBucket {
  readonly #opts: TokenBucketOptions;
  #credit: number;
  #last: number;

  constructor(opts: TokenBucketOptions) {
    this.#opts = opts;
    this.#credit = opts.capacity * opts.refillEveryMs;
    this.#last = opts.now();
  }

  tryTake(cost = 1): Decision {
    const { capacity, refillEveryMs, now } = this.#opts;
    if (cost > capacity) throw new RangeError('cost exceeds capacity');

    const t = now();
    const elapsed = Math.max(0, t - this.#last);
    this.#credit = Math.min(capacity * refillEveryMs, this.#credit + elapsed);
    this.#last = t;

    const price = cost * refillEveryMs;
    if (this.#credit >= price) {
      this.#credit -= price;
      return { allowed: true };
    }
    return { allowed: false, retryAfterMs: Math.ceil(price - this.#credit) };
  }
}
