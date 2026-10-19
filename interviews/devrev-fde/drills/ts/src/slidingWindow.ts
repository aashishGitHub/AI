import type { Clock } from './types.ts';

export interface WindowOptions {
  readonly limit: number;
  readonly windowMs: number;
  readonly now: Clock;
}

export class FixedWindowCounter {
  readonly #o: WindowOptions;
  #window = Number.NaN;
  #count = 0;

  constructor(options: WindowOptions) {
    this.#o = options;
  }

  allow(): boolean {
    const window = Math.floor(this.#o.now() / this.#o.windowMs);
    if (window !== this.#window) {
      this.#window = window;
      this.#count = 0;
    }
    if (this.#count >= this.#o.limit) return false;
    this.#count++;
    return true;
  }
}

export class SlidingWindowLog {
  readonly #o: WindowOptions;
  readonly #log: number[] = [];

  constructor(options: WindowOptions) {
    this.#o = options;
  }

  allow(): boolean {
    const t = this.#o.now();
    while (this.#log.length > 0 && this.#log[0]! <= t - this.#o.windowMs) this.#log.shift();
    if (this.#log.length >= this.#o.limit) return false;
    this.#log.push(t);
    return true;
  }
}
