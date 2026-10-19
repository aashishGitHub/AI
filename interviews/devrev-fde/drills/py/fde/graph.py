import math
from collections import deque
from collections.abc import Iterable, Mapping, Sequence

type Graph = Mapping[str, Sequence[str]]
type Edge = tuple[str, str]


def build_graph(edges: Iterable[Edge], directed: bool = True) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    for src, dst in edges:
        graph.setdefault(src, []).append(dst)
        if not directed:
            graph.setdefault(dst, []).append(src)
    return graph


def bfs_levels(graph: Graph, start: str, max_depth: float = math.inf) -> list[list[str]]:
    seen = {start}
    levels: list[list[str]] = []
    frontier = [start]
    while frontier:
        levels.append(frontier)
        if len(levels) > max_depth:
            break
        following: list[str] = []
        for node in frontier:
            for neighbour in graph.get(node, ()):
                if neighbour not in seen:
                    seen.add(neighbour)
                    following.append(neighbour)
        frontier = following
    return levels


def topo_sort(graph: Graph) -> list[str] | None:
    indegree: dict[str, int] = {}
    for node, targets in graph.items():
        indegree.setdefault(node, 0)
        for target in targets:
            indegree[target] = indegree.get(target, 0) + 1

    queue = deque(node for node, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for target in graph.get(node, ()):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    return order if len(order) == len(indegree) else None


def find_cycle(graph: Graph) -> list[str] | None:
    state: dict[str, str] = {}
    for root in graph:
        if root in state:
            continue
        state[root] = "visiting"
        stack = [(root, iter(graph.get(root, ())))]
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                state[node] = "done"
                stack.pop()
                continue
            if state.get(child) == "visiting":
                path = [name for name, _ in stack]
                return [*path[path.index(child):], child]
            if child not in state:
                state[child] = "visiting"
                stack.append((child, iter(graph.get(child, ()))))
    return None


def impacted_by(graph: Graph, start: str, max_depth: int) -> list[str]:
    return [node for level in bfs_levels(graph, start, max_depth)[1:] for node in level]
