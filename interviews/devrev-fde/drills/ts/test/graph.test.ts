import { describe, expect, it } from 'vitest';
import { bfsLevels, buildGraph, findCycle, impactedBy, topoSort, type Edge, type Graph } from '../src/graph.ts';
import { mulberry32 } from './helpers.ts';

const g = (adjacency: Record<string, string[]>): Graph => new Map(Object.entries(adjacency));

function assertValidCycle(graph: Graph, cycle: readonly string[]): void {
  expect(cycle.length).toBeGreaterThanOrEqual(2);
  expect(cycle[0]).toBe(cycle[cycle.length - 1]);
  for (let i = 0; i + 1 < cycle.length; i++) expect(graph.get(cycle[i]!)).toContain(cycle[i + 1]!);
}

describe('bfsLevels', () => {
  const graph = g({ a: ['b', 'c'], b: ['d'], c: ['d', 'e'], d: ['f'], e: [], f: [] });

  it('groups nodes by shortest distance from the start', () => {
    expect(bfsLevels(graph, 'a')).toEqual([['a'], ['b', 'c'], ['d', 'e'], ['f']]);
  });

  it('visits each node once even with diamonds and cycles', () => {
    expect(bfsLevels(g({ a: ['b', 'c'], b: ['a', 'c'], c: ['a', 'b'] }), 'a')).toEqual([['a'], ['b', 'c']]);
  });

  it('treats a start with no entry as a single level', () => {
    expect(bfsLevels(g({}), 'x')).toEqual([['x']]);
  });

  it('stops expanding after maxDepth levels', () => {
    expect(bfsLevels(graph, 'a', 0)).toEqual([['a']]);
    expect(bfsLevels(graph, 'a', 1)).toEqual([['a'], ['b', 'c']]);
    expect(bfsLevels(graph, 'a', 2)).toEqual([['a'], ['b', 'c'], ['d', 'e']]);
    expect(bfsLevels(graph, 'a', 99)).toHaveLength(4);
  });
});

describe('topoSort (Kahn)', () => {
  it('orders a DAG deterministically', () => {
    expect(topoSort(g({ a: ['b', 'c'], b: ['d'], c: ['d'], d: [] }))).toEqual(['a', 'b', 'c', 'd']);
  });

  it('includes nodes that only appear as edge targets and isolated nodes', () => {
    expect(topoSort(g({ a: ['z'], solo: [] }))).toEqual(['a', 'solo', 'z']);
  });

  it('returns null when there is a cycle, including a self-loop', () => {
    expect(topoSort(g({ a: ['b'], b: ['c'], c: ['a'] }))).toBeNull();
    expect(topoSort(g({ a: ['a'] }))).toBeNull();
  });

  it('sorts the acyclic part but still reports the cycle as null', () => {
    expect(topoSort(g({ a: ['b'], b: ['c'], c: ['b'] }))).toBeNull();
  });

  it('returns an empty order for an empty graph', () => {
    expect(topoSort(g({}))).toEqual([]);
  });

  it('puts every edge source before its target on 300 seeded random DAGs', () => {
    const rand = mulberry32(7);
    for (let round = 0; round < 300; round++) {
      const n = 2 + Math.floor(rand() * 12);
      const edges: Edge[] = [];
      for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) if (rand() < 0.3) edges.push([`n${i}`, `n${j}`]);
      const order = topoSort(buildGraph(edges));
      expect(order).not.toBeNull();
      const position = new Map(order!.map((node, index) => [node, index]));
      for (const [from, to] of edges) expect(position.get(from)!).toBeLessThan(position.get(to)!);
    }
  });
});

describe('findCycle', () => {
  it('returns null for a DAG', () => {
    expect(findCycle(g({ a: ['b', 'c'], b: ['c'], c: [] }))).toBeNull();
  });

  it('returns the cycle path with the start repeated at the end', () => {
    expect(findCycle(g({ a: ['b'], b: ['c'], c: ['a'] }))).toEqual(['a', 'b', 'c', 'a']);
  });

  it('reports only the cycle, not the tail leading into it', () => {
    const graph = g({ entry: ['a'], a: ['b'], b: ['c'], c: ['b'] });
    const cycle = findCycle(graph)!;
    expect(cycle).toEqual(['b', 'c', 'b']);
    assertValidCycle(graph, cycle);
  });

  it('finds self-loops', () => {
    expect(findCycle(g({ a: ['a'] }))).toEqual(['a', 'a']);
  });

  it('does not flag a diamond as a cycle', () => {
    expect(findCycle(g({ a: ['b', 'c'], b: ['d'], c: ['d'], d: [] }))).toBeNull();
  });

  it('agrees with topoSort on 300 seeded random graphs', () => {
    const rand = mulberry32(99);
    for (let round = 0; round < 300; round++) {
      const n = 2 + Math.floor(rand() * 8);
      const edges: Edge[] = [];
      for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) if (rand() < 0.2) edges.push([`n${i}`, `n${j}`]);
      const graph = buildGraph(edges);
      const cycle = findCycle(graph);
      expect(cycle === null).toBe(topoSort(graph) !== null);
      if (cycle) assertValidCycle(graph, cycle);
    }
  });

  it('survives a 200k-deep chain without overflowing the call stack', () => {
    const n = 200_000;
    const chain = new Map<string, string[]>();
    for (let i = 0; i < n; i++) chain.set(`n${i}`, [`n${i + 1}`]);
    expect(findCycle(chain)).toBeNull();
    chain.set(`n${n}`, ['n0']);
    expect(findCycle(chain)).toHaveLength(n + 2);
  });
});

describe('impactedBy', () => {
  const links = buildGraph([
    ['T-1', 'T-2'],
    ['T-1', 'T-3'],
    ['T-2', 'T-4'],
    ['T-3', 'T-4'],
    ['T-4', 'T-5'],
    ['T-5', 'T-1'],
  ]);

  it('lists everything reachable within the depth cap, nearest first, excluding the start', () => {
    expect(impactedBy(links, 'T-1', 1)).toEqual(['T-2', 'T-3']);
    expect(impactedBy(links, 'T-1', 2)).toEqual(['T-2', 'T-3', 'T-4']);
    expect(impactedBy(links, 'T-1', 10)).toEqual(['T-2', 'T-3', 'T-4', 'T-5']);
  });

  it('terminates on cycles and never returns the start ticket', () => {
    expect(impactedBy(links, 'T-4', 10)).toEqual(['T-5', 'T-1', 'T-2', 'T-3']);
  });

  it('returns nothing for depth 0 or an unlinked ticket', () => {
    expect(impactedBy(links, 'T-1', 0)).toEqual([]);
    expect(impactedBy(links, 'T-99', 5)).toEqual([]);
  });

  it('follows links in both directions when the graph is built undirected', () => {
    const undirected = buildGraph([['A', 'B'], ['C', 'B']], false);
    expect(impactedBy(undirected, 'A', 2)).toEqual(['B', 'C']);
  });
});
