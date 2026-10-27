from __future__ import annotations

from mesh.envelope import Envelope, sign
from mesh.queue import MessageQueue, process_one
from tests.helpers import run


def message(message_id: str) -> Envelope:
    return sign(Envelope(message_id, "c1", "a", "b", 9_999.0, 0, {"prompt": "p"}), b"k")


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_enqueue_drops_a_duplicate_message_id() -> None:
    queue = MessageQueue()
    assert queue.enqueue(message("m1"))
    assert not queue.enqueue(message("m1"))


def test_messages_are_leased_in_arrival_order_and_acked_once() -> None:
    queue = MessageQueue()
    queue.enqueue(message("m1"))
    queue.enqueue(message("m2"))
    first = queue.lease()
    assert first is not None and first.envelope.message_id == "m1"
    queue.ack("m1")
    second = queue.lease()
    assert second is not None and second.envelope.message_id == "m2"
    assert queue.lease() is None


def test_a_leased_message_is_invisible_until_the_lease_expires_then_redelivered() -> None:
    clock = Clock()
    queue = MessageQueue(lease_s=30, clock=clock)
    queue.enqueue(message("m1"))
    assert queue.lease() is not None
    clock.now = 29.0
    assert queue.lease() is None
    clock.now = 30.0
    redelivered = queue.lease()
    assert redelivered is not None and redelivered.attempts == 2


def test_a_poison_message_is_dead_lettered_after_max_attempts() -> None:
    clock = Clock()
    queue = MessageQueue(lease_s=1, max_attempts=3, clock=clock)
    queue.enqueue(message("poison"))
    for _ in range(3):
        assert queue.lease() is not None
        clock.now += 1.0
    assert queue.lease() is None
    assert queue.dead_letters() == ["poison"]


def test_process_one_nacks_on_handler_failure_so_the_next_lease_retries() -> None:
    queue = MessageQueue(max_attempts=3)
    queue.enqueue(message("m1"))
    seen: list[str] = []

    async def flaky(env: Envelope) -> None:
        seen.append(env.message_id)
        if len(seen) == 1:
            raise RuntimeError("boom")

    assert run(process_one(queue, flaky)) is True
    assert run(process_one(queue, flaky)) is True
    assert run(process_one(queue, flaky)) is False
    assert seen == ["m1", "m1"]


def test_a_crash_after_the_side_effect_but_before_the_ack_runs_the_handler_twice() -> None:
    clock = Clock()
    queue = MessageQueue(lease_s=5, clock=clock)
    queue.enqueue(message("m1"))
    effects: list[str] = []
    leased = queue.lease()
    assert leased is not None
    effects.append(leased.envelope.message_id)
    clock.now = 5.0
    again = queue.lease()
    assert again is not None
    effects.append(again.envelope.message_id)
    assert effects == ["m1", "m1"]
