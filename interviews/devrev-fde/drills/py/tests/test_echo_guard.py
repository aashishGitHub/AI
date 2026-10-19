from dataclasses import dataclass, field

from fde.echo_guard import EchoGuard, fingerprint


def test_fingerprint_ignores_key_order_but_not_values_or_types() -> None:
    assert fingerprint({"a": 1, "b": {"c": [1, 2]}}) == fingerprint({"b": {"c": [1, 2]}, "a": 1})
    assert fingerprint({"a": 1}) != fingerprint({"a": "1"})
    assert fingerprint({"a": [1, 2]}) != fingerprint({"a": [2, 1]})
    assert fingerprint(None) != fingerprint("null")
    assert fingerprint({"a": 1}) != fingerprint({"a": True})


def test_drops_the_webhook_that_mirrors_our_own_push() -> None:
    guard = EchoGuard()
    guard.record_push("t-1", "v1")
    assert guard.decide("t-1", "v1", "v1") == "drop-as-echo"


def test_still_drops_our_echo_after_the_local_copy_has_moved_on() -> None:
    guard = EchoGuard()
    guard.record_push("t-1", "v1")
    assert guard.decide("t-1", "v1", "v2-local-unpushed") == "drop-as-echo"


def test_applies_a_genuine_remote_edit_when_local_has_not_diverged_from_what_we_pushed() -> None:
    guard = EchoGuard()
    guard.record_push("t-1", "v1")
    assert guard.decide("t-1", "v2", "v1") == "apply"


def test_applies_a_brand_new_remote_entity_we_have_never_seen() -> None:
    assert EchoGuard().decide("t-9", "v1", None) == "apply"


def test_flags_a_conflict_when_both_sides_changed_since_the_last_push() -> None:
    guard = EchoGuard()
    guard.record_push("t-1", "v1")
    assert guard.decide("t-1", "v2-remote", "v2-local") == "conflict"


def test_flags_a_conflict_when_the_entity_was_created_on_both_sides_independently() -> None:
    assert EchoGuard().decide("t-1", "remote", "local") == "conflict"


def test_treats_both_sides_converging_on_the_same_content_as_nothing_to_do() -> None:
    guard = EchoGuard()
    guard.record_push("t-1", "v1")
    assert guard.decide("t-1", "v2", "v2") == "drop-as-echo"


def test_tracks_entities_independently() -> None:
    guard = EchoGuard()
    guard.record_push("a", "v1")
    assert guard.decide("b", "v1", None) == "apply"


@dataclass(frozen=True)
class Webhook:
    id: str
    fp: str


@dataclass
class Simulation:
    guarded: bool
    max_steps: int = 1000
    remote: dict[str, str] = field(default_factory=dict)
    local: dict[str, str] = field(default_factory=dict)
    guard: EchoGuard = field(default_factory=EchoGuard)
    webhooks: list[Webhook] = field(default_factory=list)
    conflicts: list[Webhook] = field(default_factory=list)
    steps: int = 0
    pushes: int = 0

    def _write_remote(self, entity_id: str, fp: str) -> None:
        self.remote[entity_id] = fp
        self.webhooks.append(Webhook(entity_id, fp))

    def _push_if_changed(self, entity_id: str) -> None:
        fp = self.local[entity_id]
        if self.guarded and self.guard.last_pushed(entity_id) == fp:
            return
        self.pushes += 1
        self.guard.record_push(entity_id, fp)
        self._write_remote(entity_id, fp)

    def _drain(self) -> None:
        while self.webhooks and self.steps < self.max_steps:
            self.steps += 1
            event = self.webhooks.pop(0)
            decision = self.guard.decide(event.id, event.fp, self.local.get(event.id)) if self.guarded else "apply"
            if decision == "conflict":
                self.conflicts.append(event)
            if decision != "apply":
                continue
            self.local[event.id] = event.fp
            self.guard.record_push(event.id, event.fp)
            self._push_if_changed(event.id)

    def local_edit(self, entity_id: str, fp: str) -> None:
        self.local[entity_id] = fp
        self._push_if_changed(entity_id)
        self._drain()

    def local_edit_offline(self, entity_id: str, fp: str) -> None:
        self.local[entity_id] = fp

    def remote_edit(self, entity_id: str, fp: str) -> None:
        self._write_remote(entity_id, fp)
        self._drain()


def test_loop_terminates_our_push_comes_back_as_a_webhook_and_is_dropped() -> None:
    sim = Simulation(guarded=True)
    sim.local_edit("t-1", "v1")
    assert (sim.steps, sim.pushes) == (1, 1)
    assert sim.webhooks == []
    assert sim.remote["t-1"] == "v1"


def test_loop_terminates_a_remote_edit_is_applied_locally_and_never_pushed_back() -> None:
    sim = Simulation(guarded=True)
    sim.local_edit("t-1", "v1")
    sim.remote_edit("t-1", "v2")
    assert sim.local["t-1"] == "v2"
    assert (sim.steps, sim.pushes) == (2, 1)
    assert sim.webhooks == []


def test_loop_terminates_across_many_entities_and_alternating_edits() -> None:
    sim = Simulation(guarded=True)
    for i in range(50):
        sim.local_edit(f"t-{i}", f"local-{i}")
        sim.remote_edit(f"t-{i}", f"remote-{i}")
    assert sim.webhooks == []
    assert sim.pushes == 50
    assert sim.steps == 100


def test_without_the_guard_the_same_scenario_ping_pongs_until_the_step_cap() -> None:
    sim = Simulation(guarded=False, max_steps=200)
    sim.local_edit("t-1", "v1")
    assert sim.steps == 200
    assert len(sim.webhooks) > 0
    assert sim.pushes > 100


def test_surfaces_a_conflict_instead_of_overwriting_an_unpushed_local_edit() -> None:
    sim = Simulation(guarded=True)
    sim.local_edit("t-1", "v1")
    sim.local_edit_offline("t-1", "v2-local")
    sim.remote_edit("t-1", "v2-remote")
    assert sim.conflicts == [Webhook("t-1", "v2-remote")]
    assert sim.local["t-1"] == "v2-local"
    assert sim.webhooks == []


def test_known_limitation_a_late_echo_of_an_older_push_is_mistaken_for_a_remote_edit() -> None:
    guard = EchoGuard()
    guard.record_push("t-1", "v1")
    guard.record_push("t-1", "v2")
    assert guard.decide("t-1", "v1", "v2") == "apply"
