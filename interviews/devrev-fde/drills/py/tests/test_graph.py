import random

from fde.graph import Graph, bfs_levels, build_graph, find_cycle, impacted_by, topo_sort


def assert_valid_cycle(graph: Graph, cycle: list[str]) -> None:
    assert len(cycle) >= 2
    assert cycle[0] == cycle[-1]
    for src, dst in zip(cycle, cycle[1:]):
        assert dst in graph[src]


DIAMOND = {"a": ["b", "c"], "b": ["d"], "c": ["d", "e"], "d": ["f"], "e": [], "f": []}


def test_bfs_groups_nodes_by_shortest_distance_from_the_start() -> None:
    assert bfs_levels(DIAMOND, "a") == [["a"], ["b", "c"], ["d", "e"], ["f"]]


def test_bfs_visits_each_node_once_even_with_cycles() -> None:
    assert bfs_levels({"a": ["b", "c"], "b": ["a", "c"], "c": ["a", "b"]}, "a") == [["a"], ["b", "c"]]


def test_bfs_treats_a_start_with_no_entry_as_a_single_level() -> None:
    assert bfs_levels({}, "x") == [["x"]]


def test_bfs_stops_expanding_after_max_depth_levels() -> None:
    assert bfs_levels(DIAMOND, "a", 0) == [["a"]]
    assert bfs_levels(DIAMOND, "a", 1) == [["a"], ["b", "c"]]
    assert bfs_levels(DIAMOND, "a", 2) == [["a"], ["b", "c"], ["d", "e"]]
    assert len(bfs_levels(DIAMOND, "a", 99)) == 4


def test_topo_orders_a_dag_deterministically() -> None:
    assert topo_sort({"a": ["b", "c"], "b": ["d"], "c": ["d"], "d": []}) == ["a", "b", "c", "d"]


def test_topo_includes_nodes_that_only_appear_as_targets_and_isolated_nodes() -> None:
    assert topo_sort({"a": ["z"], "solo": []}) == ["a", "solo", "z"]


def test_topo_returns_none_when_there_is_a_cycle_including_a_self_loop() -> None:
    assert topo_sort({"a": ["b"], "b": ["c"], "c": ["a"]}) is None
    assert topo_sort({"a": ["a"]}) is None
    assert topo_sort({"a": ["b"], "b": ["c"], "c": ["b"]}) is None


def test_topo_returns_an_empty_order_for_an_empty_graph() -> None:
    assert topo_sort({}) == []


def test_topo_puts_every_edge_source_before_its_target_on_300_seeded_random_dags() -> None:
    rand = random.Random(7)
    for _ in range(300):
        n = 2 + rand.randrange(12)
        edges = [(f"n{i}", f"n{j}") for i in range(n) for j in range(i + 1, n) if rand.random() < 0.3]
        order = topo_sort(build_graph(edges))
        assert order is not None
        position = {node: index for index, node in enumerate(order)}
        for src, dst in edges:
            assert position[src] < position[dst]


def test_cycle_returns_none_for_a_dag() -> None:
    assert find_cycle({"a": ["b", "c"], "b": ["c"], "c": []}) is None


def test_cycle_returns_the_path_with_the_start_repeated_at_the_end() -> None:
    assert find_cycle({"a": ["b"], "b": ["c"], "c": ["a"]}) == ["a", "b", "c", "a"]


def test_cycle_reports_only_the_cycle_not_the_tail_leading_into_it() -> None:
    graph = {"entry": ["a"], "a": ["b"], "b": ["c"], "c": ["b"]}
    cycle = find_cycle(graph)
    assert cycle == ["b", "c", "b"]
    assert_valid_cycle(graph, cycle)


def test_cycle_finds_self_loops() -> None:
    assert find_cycle({"a": ["a"]}) == ["a", "a"]


def test_cycle_does_not_flag_a_diamond() -> None:
    assert find_cycle({"a": ["b", "c"], "b": ["d"], "c": ["d"], "d": []}) is None


def test_cycle_agrees_with_topo_sort_on_300_seeded_random_graphs() -> None:
    rand = random.Random(99)
    for _ in range(300):
        n = 2 + rand.randrange(8)
        edges = [(f"n{i}", f"n{j}") for i in range(n) for j in range(n) if rand.random() < 0.2]
        graph = build_graph(edges)
        cycle = find_cycle(graph)
        assert (cycle is None) == (topo_sort(graph) is not None)
        if cycle:
            assert_valid_cycle(graph, cycle)


def test_cycle_survives_a_200k_deep_chain_without_hitting_the_recursion_limit() -> None:
    n = 200_000
    chain = {f"n{i}": [f"n{i + 1}"] for i in range(n)}
    assert find_cycle(chain) is None
    chain[f"n{n}"] = ["n0"]
    cycle = find_cycle(chain)
    assert cycle is not None and len(cycle) == n + 2


LINKS = build_graph([("T-1", "T-2"), ("T-1", "T-3"), ("T-2", "T-4"), ("T-3", "T-4"), ("T-4", "T-5"), ("T-5", "T-1")])


def test_impacted_lists_everything_within_the_depth_cap_nearest_first_excluding_start() -> None:
    assert impacted_by(LINKS, "T-1", 1) == ["T-2", "T-3"]
    assert impacted_by(LINKS, "T-1", 2) == ["T-2", "T-3", "T-4"]
    assert impacted_by(LINKS, "T-1", 10) == ["T-2", "T-3", "T-4", "T-5"]


def test_impacted_terminates_on_cycles_and_never_returns_the_start_ticket() -> None:
    assert impacted_by(LINKS, "T-4", 10) == ["T-5", "T-1", "T-2", "T-3"]


def test_impacted_returns_nothing_for_depth_zero_or_an_unlinked_ticket() -> None:
    assert impacted_by(LINKS, "T-1", 0) == []
    assert impacted_by(LINKS, "T-99", 5) == []


def test_impacted_follows_links_in_both_directions_when_built_undirected() -> None:
    undirected = build_graph([("A", "B"), ("C", "B")], directed=False)
    assert impacted_by(undirected, "A", 2) == ["B", "C"]
