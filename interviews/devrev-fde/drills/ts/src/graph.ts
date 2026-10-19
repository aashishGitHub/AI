export type Graph = ReadonlyMap<string, readonly string[]>;
export type Edge = readonly [from: string, to: string];

export function buildGraph(edges: readonly Edge[], directed = true): Map<string, string[]> {
  const graph = new Map<string, string[]>();
  const link = (from: string, to: string) => {
    const out = graph.get(from);
    if (out) out.push(to);
    else graph.set(from, [to]);
  };
  for (const [from, to] of edges) {
    link(from, to);
    if (!directed) link(to, from);
  }
  return graph;
}

export function bfsLevels(graph: Graph, start: string, maxDepth = Infinity): string[][] {
  const seen = new Set([start]);
  const levels: string[][] = [];
  let frontier = [start];
  while (frontier.length > 0) {
    levels.push(frontier);
    if (levels.length > maxDepth) break;
    const next: string[] = [];
    for (const node of frontier) {
      for (const neighbour of graph.get(node) ?? []) {
        if (seen.has(neighbour)) continue;
        seen.add(neighbour);
        next.push(neighbour);
      }
    }
    frontier = next;
  }
  return levels;
}

export function topoSort(graph: Graph): string[] | null {
  const indegree = new Map<string, number>();
  for (const [node, targets] of graph) {
    if (!indegree.has(node)) indegree.set(node, 0);
    for (const target of targets) indegree.set(target, (indegree.get(target) ?? 0) + 1);
  }

  const order = [...indegree].filter(([, degree]) => degree === 0).map(([node]) => node);
  for (let head = 0; head < order.length; head++) {
    for (const target of graph.get(order[head]!) ?? []) {
      const remaining = indegree.get(target)! - 1;
      indegree.set(target, remaining);
      if (remaining === 0) order.push(target);
    }
  }
  return order.length === indegree.size ? order : null;
}

export function findCycle(graph: Graph): string[] | null {
  const state = new Map<string, 'visiting' | 'done'>();
  for (const root of graph.keys()) {
    if (state.has(root)) continue;
    state.set(root, 'visiting');
    const stack: Array<[node: string, children: Iterator<string>]> = [
      [root, (graph.get(root) ?? [])[Symbol.iterator]()],
    ];
    while (stack.length > 0) {
      const [node, children] = stack[stack.length - 1]!;
      const step = children.next();
      if (step.done) {
        state.set(node, 'done');
        stack.pop();
        continue;
      }
      const child = step.value;
      const childState = state.get(child);
      if (childState === 'visiting') {
        const path = stack.map(([name]) => name);
        return [...path.slice(path.indexOf(child)), child];
      }
      if (childState === undefined) {
        state.set(child, 'visiting');
        stack.push([child, (graph.get(child) ?? [])[Symbol.iterator]()]);
      }
    }
  }
  return null;
}

export function impactedBy(graph: Graph, start: string, maxDepth: number): string[] {
  return bfsLevels(graph, start, maxDepth).slice(1).flat();
}
