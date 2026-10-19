import type { Json } from './types.ts';

export type PathSegment = string | number;
type Path = readonly PathSegment[];

export type Change =
  | { readonly op: 'add'; readonly path: Path; readonly after: Json }
  | { readonly op: 'remove'; readonly path: Path; readonly before: Json }
  | { readonly op: 'replace'; readonly path: Path; readonly before: Json; readonly after: Json };

type JsonObject = { readonly [key: string]: Json };

const isArray = (v: Json): v is readonly Json[] => Array.isArray(v);
const isObject = (v: Json): v is JsonObject => typeof v === 'object' && v !== null && !Array.isArray(v);

export function diff(before: Json, after: Json): Change[] {
  const out: Change[] = [];
  walk(before, after, [], out);
  return out;
}

function walk(before: Json, after: Json, path: Path, out: Change[]): void {
  if (isArray(before) && isArray(after)) {
    const common = Math.min(before.length, after.length);
    for (let i = 0; i < common; i++) walk(before[i]!, after[i]!, [...path, i], out);
    for (let i = common; i < after.length; i++) out.push({ op: 'add', path: [...path, i], after: after[i]! });
    for (let i = before.length - 1; i >= common; i--) out.push({ op: 'remove', path: [...path, i], before: before[i]! });
  } else if (isObject(before) && isObject(after)) {
    for (const [key, value] of Object.entries(before)) {
      if (Object.hasOwn(after, key)) walk(value, after[key]!, [...path, key], out);
      else out.push({ op: 'remove', path: [...path, key], before: value });
    }
    for (const [key, value] of Object.entries(after)) {
      if (!Object.hasOwn(before, key)) out.push({ op: 'add', path: [...path, key], after: value });
    }
  } else if (before !== after) {
    out.push({ op: 'replace', path, before, after });
  }
}

type Container = Json[] | { [key: string]: Json };

export function applyPatch(doc: Json, changes: readonly Change[]): Json {
  // A one-slot holder lets a change at the root path take the same code path as any other.
  const holder: Container = [structuredClone(doc)];
  for (const change of changes) {
    const path: PathSegment[] = [0, ...change.path];
    if (path.includes('__proto__')) throw new Error('refusing to patch __proto__');
    const key = path.pop()!;
    const parent = path.reduce<Container>((node, segment) => descend(node, segment), holder);
    const value = change.op === 'remove' ? null : structuredClone(change.after);
    write(parent, key, change.op, value);
  }
  return holder[0]!;
}

function descend(node: Container, segment: PathSegment): Container {
  const next = (node as { [k: PathSegment]: Json })[segment];
  if (typeof next !== 'object' || next === null) throw new Error(`no container at ${segment}`);
  return next as Container;
}

function write(parent: Container, key: PathSegment, op: Change['op'], value: Json): void {
  if (Array.isArray(parent)) {
    const index = key as number;
    if (op === 'add') parent.splice(index, 0, value);
    else if (op === 'remove') parent.splice(index, 1);
    else parent[index] = value;
  } else if (op === 'remove') {
    delete parent[key as string];
  } else {
    parent[key as string] = value;
  }
}
