"""Confidence checks that run before any action or emotion changes."""

from ..trace import record
from . import directive_constants as constants
from .decisions import Action, Decisions, Intent, Object, Recipient


def blocked_event(answers: Decisions, floor: float) -> str | None:
    """Return a clarification or redirection event when a turn cannot act."""
    def block(event: str, reason: str) -> str:
        record("world.validation", reason, accepted=False, event_selected=event, confidence_floor=floor)
        return event

    if answers.off_world.confidence < floor:
        return block(constants.CLARIFY_EVENT, "Off-world classification is below the confidence floor.")
    if answers.off_world.value == "yes":
        return block(constants.OFF_WORLD_EVENT, "The line is classified as off-world; redirect without actions or emotion changes.")
    if answers.action.confidence < floor or answers.action.value == Action.UNCLEAR:
        return block(constants.CLARIFY_EVENT, "The physical action is unclear or below the confidence floor.")
    if answers.action.value == Action.INSPECT and (
        answers.action_object.confidence < floor
        or answers.action_object.value in (Object.NONE, Object.UNKNOWN)
    ):
        return block(constants.CLARIFY_EVENT, "The inspection target is missing, unknown, or below the confidence floor.")
    if answers.recipient.confidence < floor or answers.recipient.value == Recipient.UNKNOWN:
        return block(constants.CLARIFY_EVENT, "The speech recipient is unknown or below the confidence floor.")
    if answers.recipient.value == Recipient.NONE:
        record("world.validation", "The physical interpretation passed; without explicit speech, spoken-intent checks are unnecessary.",
               accepted=True, confidence_floor=floor)
        return None
    if answers.intent.confidence < floor or answers.intent.value in (Intent.NONE, Intent.UNCLEAR):
        return block(constants.CLARIFY_EVENT, "Explicit speech has no clear, sufficiently confident intent.")

    intent = Intent(answers.intent.value)
    if intent in (Intent.ASK_ABOUT, Intent.REQUEST) and (
        answers.object.confidence < floor
        or answers.object.value in (Object.NONE, Object.UNKNOWN)
    ):
        return block(constants.CLARIFY_EVENT, "The spoken request's object is missing, unknown, or below the confidence floor.")
    record("world.validation", "Physical action and explicit speech passed all required confidence checks.",
           accepted=True, confidence_floor=floor)
    return None
