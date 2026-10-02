"""Confidence checks that run before any action or emotion changes."""

from . import directive_constants as constants
from .decisions import Decisions, Intent, Object


def blocked_event(answers: Decisions, floor: float) -> str | None:
    """Return a clarification or redirection event when a turn cannot act."""
    if answers.off_world.confidence < floor:
        return constants.CLARIFY_EVENT
    if answers.off_world.value == "yes":
        return constants.OFF_WORLD_EVENT
    if answers.intent.confidence < floor or answers.intent.value == Intent.UNCLEAR:
        return constants.CLARIFY_EVENT

    intent = Intent(answers.intent.value)
    if intent in (Intent.INSPECT, Intent.REQUEST) and (
        answers.object.confidence < floor
        or answers.object.value in (Object.NONE, Object.UNKNOWN)
    ):
        return constants.CLARIFY_EVENT
    return None
