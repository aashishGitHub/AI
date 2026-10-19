import { describe, expect, it } from 'vitest';
import { applyPatch, diff, type Change } from '../src/jsonDiff.ts';
import type { Json } from '../src/types.ts';
import { mulberry32 } from './helpers.ts';

describe('diff', () => {
  it('returns nothing for equal documents', () => {
    expect(diff({ a: [1, { b: null }] }, { a: [1, { b: null }] })).toEqual([]);
  });

  it('reports add, remove and replace at nested paths', () => {
    const before = { user: { name: 'Ada', age: 36 }, tags: ['x'] };
    const after = { user: { name: 'Ada L', email: 'a@x.io' }, tags: ['x'] };
    expect(diff(before, after)).toEqual<Change[]>([
      { op: 'replace', path: ['user', 'name'], before: 'Ada', after: 'Ada L' },
      { op: 'remove', path: ['user', 'age'], before: 36 },
      { op: 'add', path: ['user', 'email'], after: 'a@x.io' },
    ]);
  });

  it('treats a type change as a replace of the whole subtree', () => {
    expect(diff({ a: [1] }, { a: { 0: 1 } })).toEqual([
      { op: 'replace', path: ['a'], before: [1], after: { 0: 1 } },
    ]);
    expect(diff({ a: null }, { a: {} })).toEqual([{ op: 'replace', path: ['a'], before: null, after: {} }]);
  });

  it('replaces at the root path when the documents are different scalars', () => {
    expect(diff(1, 2)).toEqual([{ op: 'replace', path: [], before: 1, after: 2 }]);
  });

  it('distinguishes null, false, 0 and empty string', () => {
    expect(diff({ v: null }, { v: false })).toHaveLength(1);
    expect(diff({ v: 0 }, { v: '' })).toHaveLength(1);
    expect(diff({ v: false }, { v: 0 })).toHaveLength(1);
  });

  it('diffs arrays by index: inserting at the front rewrites every element', () => {
    expect(diff(['b', 'c'], ['a', 'b', 'c'])).toEqual<Change[]>([
      { op: 'replace', path: [0], before: 'b', after: 'a' },
      { op: 'replace', path: [1], before: 'c', after: 'b' },
      { op: 'add', path: [2], after: 'c' },
    ]);
  });

  it('emits array removals from the tail so sequential application stays valid', () => {
    expect(diff([1, 2, 3, 4], [1])).toEqual<Change[]>([
      { op: 'remove', path: [3], before: 4 },
      { op: 'remove', path: [2], before: 3 },
      { op: 'remove', path: [1], before: 2 },
    ]);
  });

  it('does not mistake prototype properties for keys', () => {
    expect(diff({}, { toString: 1 })).toEqual([{ op: 'add', path: ['toString'], after: 1 }]);
    expect(diff({ toString: 1 }, {})).toEqual([{ op: 'remove', path: ['toString'], before: 1 }]);
  });
});

describe('applyPatch', () => {
  it('does not mutate its input', () => {
    const doc = { a: [1, 2], b: { c: 1 } };
    const snapshot = structuredClone(doc);
    applyPatch(doc, diff(doc, { a: [9], b: {} }));
    expect(doc).toStrictEqual(snapshot);
  });

  it('does not alias the target document', () => {
    const target = { list: [{ id: 1 }] };
    const patched = applyPatch({}, diff({}, target)) as { list: { id: number }[] };
    patched.list[0]!.id = 99;
    expect(target.list[0]!.id).toBe(1);
  });

  it('handles a root-level replace', () => {
    expect(applyPatch([1], diff([1], { a: 1 }))).toEqual({ a: 1 });
  });

  it('refuses to write through __proto__', () => {
    const evil: Change = { op: 'add', path: ['__proto__', 'polluted'], after: true };
    expect(() => applyPatch({}, [evil])).toThrow(/__proto__/);
    expect(({} as Record<string, unknown>)['polluted']).toBeUndefined();
  });

  it('throws on a path that does not exist', () => {
    expect(() => applyPatch({}, [{ op: 'add', path: ['a', 'b'], after: 1 }])).toThrow();
  });
});

function generate(rand: () => number, depth: number): Json {
  const pick = <T>(xs: readonly T[]): T => xs[Math.floor(rand() * xs.length)]!;
  const kind = depth <= 0 ? pick(['scalar'] as const) : pick(['scalar', 'scalar', 'array', 'object'] as const);
  if (kind === 'array') return Array.from({ length: Math.floor(rand() * 4) }, () => generate(rand, depth - 1));
  if (kind === 'object') {
    const out: Record<string, Json> = {};
    for (let i = Math.floor(rand() * 4); i > 0; i--) out[pick(['a', 'b', 'c', 'd'])] = generate(rand, depth - 1);
    return out;
  }
  return pick<Json>([null, true, false, 0, 1, 2, 'x', 'y', '']);
}

function mutate(rand: () => number, value: Json): Json {
  if (rand() < 0.3) return generate(rand, 2);
  if (Array.isArray(value)) {
    const copy = value.map((v) => mutate(rand, v));
    if (rand() < 0.4) copy.push(generate(rand, 1));
    if (rand() < 0.3) copy.splice(Math.floor(rand() * (copy.length + 1)), 1);
    return copy;
  }
  if (value !== null && typeof value === 'object') {
    const copy: Record<string, Json> = {};
    for (const [k, v] of Object.entries(value)) if (rand() > 0.2) copy[k] = mutate(rand, v);
    if (rand() < 0.4) copy['e'] = generate(rand, 1);
    return copy;
  }
  return value;
}

describe('property: applyPatch(diff(a, b), a) deep-equals b', () => {
  it('holds over 2000 seeded random pairs, and diff(a, a) is empty', () => {
    const rand = mulberry32(20260101);
    let nonTrivial = 0;
    for (let i = 0; i < 2000; i++) {
      const a = generate(rand, 3);
      const b = rand() < 0.7 ? mutate(rand, a) : generate(rand, 3);
      const snapshot = structuredClone(a);

      const changes = diff(a, b);
      expect(applyPatch(a, changes)).toStrictEqual(b);
      expect(a).toStrictEqual(snapshot);
      expect(diff(a, a)).toEqual([]);
      if (changes.length > 1) nonTrivial++;
    }
    expect(nonTrivial).toBeGreaterThan(200);
  });
});
