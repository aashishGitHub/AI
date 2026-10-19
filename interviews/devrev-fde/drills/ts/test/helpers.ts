export class FakeClock {
  #now: number;

  constructor(start = 0) {
    this.#now = start;
  }

  now = (): number => this.#now;

  advance(ms: number): void {
    this.#now += ms;
  }
}

export function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function scripted(values: readonly number[]): () => number {
  let i = 0;
  return () => {
    const v = values[i++];
    if (v === undefined) throw new Error('scripted rng exhausted');
    return v;
  };
}
