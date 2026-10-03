"""Coordinate one authoritative world turn."""

from dataclasses import asdict, replace

from ..trace import log_context, record
from .actions import resolve_action, resolve_speech
from .decisions import Action, Decisions
from .directives import Directive
from .emotions import update_emotions
from .outcomes import finish_turn
from .state import World
from .validation import blocked_event


def advance(world: World, answers: Decisions, floor: float = 0.6) -> tuple[World, Directive]:
    """Interpret one snapshot, then resolve physical actions before accompanying speech."""
    if world.ending != "playing":
        raise ValueError("This encounter has ended.")
    with log_context(turn=world.turn + 1):
        record("world.interpretation", "Resolve Jev's validated interpretation using Python rules; physical actions precede speech.",
               answers=asdict(answers), before=world.snapshot(), confidence_floor=floor)
        state = replace(world, history=list(world.history), turn=world.turn + 1)

        event = blocked_event(answers, floor)
        if event is not None:
            return finish_turn(state, (event,))

        update_emotions(state, answers, floor)
        events = []
        action_event = resolve_action(state, answers)
        if action_event is not None:
            events.append(action_event)
        # A grab is blocked and provokes its own reaction, regardless of accompanying words.
        if answers.action.value != Action.TAKE_KEY:
            speech_event = resolve_speech(world, state, answers, floor)
            if speech_event is not None:
                events.append(speech_event)
        else:
            record("world.speech", "The blocked key grab supplies its own reaction, so accompanying speech is not resolved.")
        return finish_turn(state, tuple(events))
