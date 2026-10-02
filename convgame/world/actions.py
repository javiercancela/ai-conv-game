"""Resolve scene actions using both the original and the new turn's state."""

from . import directive_constants as constants
from .decisions import Decisions, Intent, Object
from .state import World


def key_request_event(
    world: World, state: World, answers: Decisions, floor: float
) -> str:
    """Require readiness before and after the turn; the model cannot grant items."""
    if (
        world.ready
        and state.ready
        and answers.handover.value == "yes"
        and answers.handover.confidence >= floor
    ):
        return constants.WON_EVENT
    if world.ready and answers.handover.confidence < floor:
        return constants.CLARIFY_EVENT
    return constants.REFUSE_EVENT


def resolve_action(
    world: World, state: World, answers: Decisions, floor: float
) -> str:
    """Apply accepted actions to the new state and select their narration event."""
    intent = Intent(answers.intent.value)
    if intent == Intent.THREATEN:
        return constants.THREATEN_EVENT

    if (
        answers.rescue_plan.value == "yes"
        and answers.rescue_plan.confidence >= floor
        and world.ledger_read
    ):
        state.plan_agreed = True

    if intent == Intent.REQUEST and answers.object.value == Object.KEY:
        return key_request_event(world, state, answers, floor)
    if intent in (Intent.INSPECT, Intent.REQUEST):
        if answers.object.value == Object.LEDGER:
            state.ledger_read = True
        return answers.object.value
    if state.plan_agreed and not world.plan_agreed:
        return constants.PLAN_EVENT
    if intent in (Intent.REASSURE, Intent.PERSUADE):
        return constants.REASSURE_EVENT
    return constants.CHAT_EVENT
