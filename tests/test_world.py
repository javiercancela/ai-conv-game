"""Regression coverage for turn ordering and snapshot isolation."""

from dataclasses import replace

import pytest

from convgame.world import Decisions, Pick, World, advance


NEUTRAL_ANSWERS = Decisions(
    intent=Pick("chat", 1),
    object=Pick("none", 1),
    off_world=Pick("no", 1),
    rescue_plan=Pick("no", 1),
    handover=Pick("no", 1),
    tension=0,
    tension_confidence=1,
    hostility=0,
    reassurance=0,
)


def test_snapshot_limits_history_and_copies_entries() -> None:
    world = World(history=[{"role": "user", "content": str(i)} for i in range(8)])

    snapshot = world.snapshot()

    assert snapshot["history"] == world.history[-6:]
    assert snapshot["ready_to_lend_key"] == world.ready
    snapshot["history"][0]["content"] = "changed"
    snapshot["history"].clear()
    assert len(world.history) == 8
    assert world.history[2]["content"] == "2"


def test_reading_ledger_and_offering_plan_requires_another_turn() -> None:
    answers = replace(
        NEUTRAL_ANSWERS,
        intent=Pick("inspect", 1),
        object=Pick("ledger", 1),
        rescue_plan=Pick("yes", 1),
    )

    state, directive = advance(World(), answers)

    assert state.ledger_read
    assert not state.plan_agreed
    assert directive.event == "ledger"


def test_reaching_readiness_during_request_does_not_grant_key() -> None:
    world = World(ledger_read=True, trust=1)
    answers = replace(
        NEUTRAL_ANSWERS,
        intent=Pick("request", 1),
        object=Pick("key", 1),
        rescue_plan=Pick("yes", 1),
        handover=Pick("yes", 1),
    )

    state, directive = advance(world, answers)

    assert state.ready
    assert not state.key_given
    assert not world.plan_agreed
    assert directive.event == "refuse"
    assert directive.fallback == (
        "The key stays with me for now. First, ask me clearly to lend you the key."
    )


def test_losing_trust_during_request_prevents_handover() -> None:
    world = World(ledger_read=True, plan_agreed=True, trust=0.6)
    answers = replace(
        NEUTRAL_ANSWERS,
        intent=Pick("request", 1),
        object=Pick("key", 1),
        handover=Pick("yes", 1),
        hostility=1,
    )

    state, directive = advance(world, answers)

    assert world.ready
    assert not state.ready
    assert not state.key_given
    assert directive.event == "refuse"
    assert directive.fallback == (
        "The key stays with me for now. First, give me reason to trust you."
    )


def test_threat_does_not_record_a_rescue_plan() -> None:
    answers = replace(
        NEUTRAL_ANSWERS, intent=Pick("threaten", 1), rescue_plan=Pick("yes", 1)
    )

    state, directive = advance(World(ledger_read=True), answers)

    assert not state.plan_agreed
    assert directive.event == "threaten"


@pytest.mark.parametrize("off_world", [Pick("no", 0.2), Pick("yes", 1)])
def test_blocked_action_still_checks_loss_before_timeout(off_world: Pick) -> None:
    world = World(turn=11, suspicion=0.9)

    state, directive = advance(world, replace(NEUTRAL_ANSWERS, off_world=off_world))

    assert state.turn == 12
    assert state.ending == directive.event == "lost"
