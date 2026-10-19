import { describe, expect, it } from 'vitest';
import { mergeLatest } from '../src/mergeRecords.ts';

interface Rec {
  readonly id: string;
  readonly version: number;
  readonly note: string;
}
const rec = (id: string, version: number, note = ''): Rec => ({ id, version, note });
const merge = (records: readonly Rec[]) =>
  mergeLatest(records, (r) => r.id, (r) => r.version);

describe('mergeLatest', () => {
  it('keeps the highest version per key regardless of arrival order', () => {
    const out = merge([rec('a', 2, 'new'), rec('a', 1, 'old'), rec('a', 3, 'newest')]);
    expect(out).toEqual([rec('a', 3, 'newest')]);
  });

  it('is stable: output follows first appearance of each key', () => {
    const out = merge([rec('b', 1), rec('a', 1), rec('b', 2), rec('c', 1), rec('a', 5)]);
    expect(out.map((r) => [r.id, r.version])).toEqual([['b', 2], ['a', 5], ['c', 1]]);
  });

  it('breaks version ties in favour of the later record', () => {
    const out = merge([rec('a', 1, 'first'), rec('a', 1, 'second')]);
    expect(out).toEqual([rec('a', 1, 'second')]);
  });

  it('does not let a stale record displace a newer one after a tie', () => {
    const out = merge([rec('a', 2, 'x'), rec('a', 2, 'y'), rec('a', 1, 'z')]);
    expect(out).toEqual([rec('a', 2, 'y')]);
  });

  it('handles empty input and returns the original object references', () => {
    expect(merge([])).toEqual([]);
    const only = rec('a', 1);
    expect(merge([only])[0]).toBe(only);
  });

  it('accepts any iterable and does not mutate the input', () => {
    const input = [rec('a', 1), rec('a', 2)];
    const copy = [...input];
    expect(mergeLatest(new Set(input), (r) => r.id, (r) => r.version)).toEqual([rec('a', 2)]);
    expect(input).toEqual(copy);
  });

  it('is linear: one key() call per record and at most two version() calls per record', () => {
    const n = 5000;
    const records = Array.from({ length: n }, (_, i) => rec(`k${i % 100}`, i));
    let keyCalls = 0;
    let versionCalls = 0;
    mergeLatest(records, (r) => (keyCalls++, r.id), (r) => (versionCalls++, r.version));
    expect(keyCalls).toBe(n);
    expect(versionCalls).toBeLessThanOrEqual(2 * n);
  });
});
