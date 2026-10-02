"""Coordinate one authoritative world turn."""

from dataclasses import replace

from .actions import resolve_action
from .decisions import Decisions
from .directives import Directive
from .emotions import update_emotions
from .outcomes import finish_turn
from .state import World
from .validation import blocked_event


def advance(world: World, answers: Decisions, floor: float = 0.6) -> tuple[World, Directive]:
    """Return a new state; all decisions refer to the same pre-turn snapshot."""
    if world.ending != "playing":
        raise ValueError("This encounter has ended.")
    state = replace(world, history=list(world.history), turn=world.turn + 1)

    event = blocked_event(answers, floor)
    if event is not None:
        return finish_turn(state, event)

    update_emotions(state, answers, floor)
    event = resolve_action(world, state, answers, floor)
    return finish_turn(state, event)
