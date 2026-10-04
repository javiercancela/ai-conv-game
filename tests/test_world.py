"""Regression coverage for turn ordering and snapshot isolation."""

from dataclasses import replace

import pytest

from convgame.world import Decisions, Pick, Speaker, World, advance


NEUTRAL_ANSWERS = Decisions(
    action=Pick("none", 1),
    action_object=Pick("none", 1),
    recipient=Pick("maren", 1),
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


def test_reading_ledger_does_not_communicate_a_promise() -> None:
    answers = replace(
        NEUTRAL_ANSWERS,
        action=Pick("inspect", 1),
        action_object=Pick("ledger", 1),
        recipient=Pick("none", 1),
        rescue_plan=Pick("yes", 1), reassurance=1,
    )

    state, directive = advance(World(), answers)

    assert state.ledger_read
    assert not state.plan_agreed
    assert state.trust == World().trust
    assert directive.event == "ledger"
    assert [beat.speaker for beat in directive.beats] == [Speaker.NARRATOR]
    assert not directive.player_spoke


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
    assert directive.fallback[0].text == (
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
    assert directive.fallback[0].text == (
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


def test_asking_about_ledger_does_not_read_it() -> None:
    answers = replace(NEUTRAL_ANSWERS, intent=Pick("ask_about", 1), object=Pick("ledger", 1))

    state, directive = advance(World(), answers)

    assert not state.ledger_read
    assert directive.event == "ask_ledger"
    assert [beat.speaker for beat in directive.beats] == [Speaker.MAREN]
    assert directive.player_spoke


def test_private_intentions_cannot_reassure_threaten_or_win() -> None:
    world = World(ledger_read=True, plan_agreed=True, trust=1)
    answers = replace(
        NEUTRAL_ANSWERS, recipient=Pick("none", 1), intent=Pick("request", 1),
        object=Pick("key", 1), rescue_plan=Pick("yes", 1), handover=Pick("yes", 1),
        reassurance=1, hostility=1, tension=1,
    )

    state, directive = advance(world, answers)

    assert state == replace(world, turn=1, revision=1)
    assert directive.event == "unspoken"
    assert [beat.speaker for beat in directive.beats] == [Speaker.NARRATOR]


def test_action_and_speech_can_share_a_turn_with_separate_objects() -> None:
    answers = replace(
        NEUTRAL_ANSWERS, action=Pick("inspect", 1), action_object=Pick("ledger", 1),
        intent=Pick("request", 1), object=Pick("key", 1), handover=Pick("yes", 1),
    )

    state, directive = advance(World(), answers)

    assert state.turn == 1
    assert state.ledger_read
    assert not state.key_given
    assert directive.events == ("ledger", "refuse")
    assert [beat.speaker for beat in directive.beats] == [Speaker.NARRATOR, Speaker.MAREN]


def test_reading_then_speaking_the_plan_can_share_a_turn() -> None:
    answers = replace(
        NEUTRAL_ANSWERS, action=Pick("inspect", 1), action_object=Pick("ledger", 1),
        intent=Pick("persuade", 1), rescue_plan=Pick("yes", 1), reassurance=1,
    )

    state, directive = advance(World(), answers)

    assert state.ledger_read and state.plan_agreed and state.ready
    assert not state.key_given
    assert directive.events == ("ledger", "plan")


def test_grabbing_key_is_blocked_even_when_ready_and_accompanied_by_a_request() -> None:
    world = World(ledger_read=True, plan_agreed=True, trust=1)
    answers = replace(
        NEUTRAL_ANSWERS, action=Pick("take_key", 1), intent=Pick("request", 1),
        object=Pick("key", 1), handover=Pick("yes", 1), reassurance=1,
    )

    state, directive = advance(world, answers)

    assert not state.key_given
    assert state.suspicion > world.suspicion
    assert state.trust < world.trust
    assert directive.events == ("take_key",)
    assert not directive.player_spoke
    assert [beat.speaker for beat in directive.beats] == [Speaker.NARRATOR, Speaker.MAREN]


def test_ringing_bell_is_observable_without_forced_speech() -> None:
    answers = replace(NEUTRAL_ANSWERS, action=Pick("ring_bell", 1), recipient=Pick("none", 1))

    state, directive = advance(World(), answers)

    assert state.bell_rung and not World().bell_rung
    assert state.snapshot()["bell_rung"]
    assert directive.event == "ring_bell"
    assert [beat.speaker for beat in directive.beats] == [Speaker.NARRATOR]


def test_final_turn_still_narrates_action_before_tide_closes() -> None:
    answers = replace(
        NEUTRAL_ANSWERS, action=Pick("inspect", 1), action_object=Pick("ledger", 1),
        recipient=Pick("none", 1),
    )

    state, directive = advance(World(turn=11), answers)

    assert state.ledger_read and state.ending == "timeout"
    assert directive.events == ("ledger", "timeout")
    assert all(beat.speaker == Speaker.NARRATOR for beat in directive.beats)


def test_timeout_replaces_clarification_instead_of_inviting_another_action() -> None:
    answers = replace(NEUTRAL_ANSWERS, intent=Pick("unclear", 1))

    state, directive = advance(World(turn=11), answers)

    assert state.ending == "timeout"
    assert directive.event == "timeout"
    assert len(directive.beats) == 1
    assert "tide" in directive.fallback[0].text.lower()


@pytest.mark.parametrize("object", ["ledger", "key", "bell"])
def test_quiet_inspection_ignores_uncertain_spoken_intent(object: str) -> None:
    answers = replace(
        NEUTRAL_ANSWERS, action=Pick("inspect", 1), action_object=Pick(object, 1),
        recipient=Pick("none", 1), intent=Pick("unclear", 0), object=Pick("unknown", 0),
        hostility=0.1, reassurance=0.1, tension=0.1,
    )

    state, directive = advance(World(), answers)

    assert directive.event == object
    assert state.turn == 1
    assert state.trust == World().trust
    assert state.suspicion == World().suspicion
    assert state.composure == World().composure
    assert all(beat.speaker == Speaker.NARRATOR for beat in directive.beats)
