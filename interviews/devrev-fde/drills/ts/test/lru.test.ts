import { describe, expect, it } from 'vitest';
import { LinkedLruCache, LruCache } from '../src/lru.ts';

describe.each([
  ['Map-based', (n: number) => new LruCache<string, number>(n)],
  ['linked-list', (n: number) => new LinkedLruCache<string, number>(n)],
])('%s LRU cache', (_name, make) => {
  it('returns undefined for a miss and the value for a hit', () => {
    const cache = make(2);
    expect(cache.get('a')).toBeUndefined();
    cache.put('a', 1);
    expect(cache.get('a')).toBe(1);
  });

  it('evicts the least recently used entry when over capacity', () => {
    const cache = make(2);
    cache.put('a', 1);
    cache.put('b', 2);
    cache.put('c', 3);
    expect(cache.get('a')).toBeUndefined();
    expect(cache.keys()).toEqual(['b', 'c']);
    expect(cache.size).toBe(2);
  });

  it('counts a get as a use', () => {
    const cache = make(2);
    cache.put('a', 1);
    cache.put('b', 2);
    cache.get('a');
    cache.put('c', 3);
    expect(cache.get('b')).toBeUndefined();
    expect(cache.get('a')).toBe(1);
  });

  it('counts an overwrite as a use and updates the value without growing', () => {
    const cache = make(2);
    cache.put('a', 1);
    cache.put('b', 2);
    cache.put('a', 10);
    expect(cache.size).toBe(2);
    cache.put('c', 3);
    expect(cache.get('b')).toBeUndefined();
    expect(cache.get('a')).toBe(10);
  });

  it('works with capacity 1', () => {
    const cache = make(1);
    cache.put('a', 1);
    cache.put('b', 2);
    expect(cache.get('a')).toBeUndefined();
    expect(cache.get('b')).toBe(2);
    cache.put('b', 3);
    expect(cache.keys()).toEqual(['b']);
  });

  it('a miss does not disturb the order', () => {
    const cache = make(2);
    cache.put('a', 1);
    cache.put('b', 2);
    cache.get('zzz');
    expect(cache.keys()).toEqual(['a', 'b']);
  });

  it('rejects a capacity below one', () => {
    expect(() => make(0)).toThrow(RangeError);
    expect(() => make(1.5)).toThrow(RangeError);
  });

  it('stays correct over a long mixed workload, matching a naive model', () => {
    const cache = make(5);
    const model: [string, number][] = [];
    let seed = 12345;
    const rand = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
    for (let i = 0; i < 5000; i++) {
      const key = String(Math.floor(rand() * 9));
      if (rand() < 0.5) {
        cache.put(key, i);
        const at = model.findIndex(([k]) => k === key);
        if (at >= 0) model.splice(at, 1);
        model.push([key, i]);
        if (model.length > 5) model.shift();
      } else {
        const at = model.findIndex(([k]) => k === key);
        const expected = at >= 0 ? model[at]![1] : undefined;
        if (at >= 0) model.push(model.splice(at, 1)[0]!);
        expect(cache.get(key)).toBe(expected);
      }
      expect(cache.keys()).toEqual(model.map(([k]) => k));
    }
  });
});
