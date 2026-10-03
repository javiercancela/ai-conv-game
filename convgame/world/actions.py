"""Resolve scene actions using both the original and the new turn's state."""

from ..trace import record
from . import directive_constants as constants
from .decisions import Action, Decisions, Intent, Object, Recipient
from .state import World


def key_request_event(
    world: World, state: World, answers: Decisions, floor: float
) -> str:
    """Require readiness before and after the turn; the model cannot grant items."""
    checks = {
        "ready_before_turn": world.ready,
        "ready_after_emotion_and_action_changes": state.ready,
        "peaceful_handover_identified": answers.handover.value == "yes",
        "handover_confident": answers.handover.confidence >= floor,
    }
    requirements = {
        label: {"ledger_read": value.ledger_read, "plan_agreed": value.plan_agreed,
                "trust_at_least_0.55": value.trust >= 0.55,
                "suspicion_below_0.65": value.suspicion < 0.65}
        for label, value in (("before", world), ("after", state))
    }
    if (
        world.ready
        and state.ready
        and answers.handover.value == "yes"
        and answers.handover.confidence >= floor
    ):
        record("world.key_request", "Lend the key: readiness holds before and after this turn, and Jev confidently identified a peaceful handover.",
               event_selected=constants.WON_EVENT, checks=checks, requirements=requirements)
        return constants.WON_EVENT
    if world.ready and answers.handover.confidence < floor:
        record("world.key_request", "Ask for clarification: the player was ready, but the handover confidence is below the floor.",
               event_selected=constants.CLARIFY_EVENT, checks=checks, requirements=requirements,
               handover_confidence=answers.handover.confidence, confidence_floor=floor)
        return constants.CLARIFY_EVENT
    record("world.key_request", "Refuse the key because at least one required readiness or peaceful-handover check failed; becoming ready during the request is insufficient.",
           event_selected=constants.REFUSE_EVENT, checks=checks, requirements=requirements,
           failed_checks=[name for name, passed in checks.items() if not passed],
           handover_confidence=answers.handover.confidence, confidence_floor=floor)
    return constants.REFUSE_EVENT


def resolve_action(state: World, answers: Decisions) -> str | None:
    """Resolve a physical attempt independently of anything the player says."""
    action = Action(answers.action.value)
    if action == Action.INSPECT:
        if answers.action_object.value == Object.LEDGER:
            state.ledger_read = True
        record("world.action", "Resolve the inspection; only physically reading the ledger records it as read.",
               action=action, object=answers.action_object.value, ledger_read=state.ledger_read)
        return answers.action_object.value
    if action == Action.TAKE_KEY:
        record("world.action", "Maren guards the key; physical grabs never grant it, even when the player is ready.",
               action=action, event_selected=constants.TAKE_KEY_EVENT)
        return constants.TAKE_KEY_EVENT
    if action == Action.RING_BELL:
        state.bell_rung = True
        record("world.action", "The accepted physical action rings the bell.", action=action, bell_rung=True)
        return constants.RING_BELL_EVENT
    record("world.action", "No physical action was established.", action=action)
    return None


def resolve_speech(
    world: World, state: World, answers: Decisions, floor: float
) -> str | None:
    """Only explicit speech to Maren can make a promise or request a handover."""
    if answers.recipient.value != Recipient.MAREN:
        record("world.speech", "No explicit speech to Maren was established; ignore spoken promises and requests.",
               recipient=answers.recipient.value)
        return None
    intent = Intent(answers.intent.value)
    if intent == Intent.THREATEN:
        record("world.speech", "React to the explicit threat; threats do not record a safety plan.",
               event_selected=constants.THREATEN_EVENT)
        return constants.THREATEN_EVENT

    if (
        answers.rescue_plan.value == "yes"
        and answers.rescue_plan.confidence >= floor
        and state.ledger_read
    ):
        state.plan_agreed = True
        record("world.plan", "Record the complete safety commitment: it was explicitly spoken to Maren with sufficient confidence after the ledger was read.",
               agreed=True, confidence=answers.rescue_plan.confidence, confidence_floor=floor)
    else:
        record("world.plan", "Keep the existing plan status: recording a plan requires a complete, confident spoken commitment and a read ledger.",
               agreed=state.plan_agreed, ledger_read=state.ledger_read,
               rescue_plan=answers.rescue_plan.value, confidence=answers.rescue_plan.confidence,
               confidence_floor=floor)

    if intent == Intent.REQUEST and answers.object.value == Object.KEY:
        return key_request_event(world, state, answers, floor)
    if intent in (Intent.ASK_ABOUT, Intent.REQUEST):
        record("world.speech", "Answer the spoken question about the object; discussing an object does not perform a physical action.",
               event_selected=f"ask_{answers.object.value}")
        return f"ask_{answers.object.value}"
    if state.plan_agreed and not world.plan_agreed:
        record("world.speech", "Acknowledge the newly agreed rescue plan.", event_selected=constants.PLAN_EVENT)
        return constants.PLAN_EVENT
    if intent in (Intent.REASSURE, Intent.PERSUADE):
        record("world.speech", "Respond to explicit reassurance or persuasion.", event_selected=constants.REASSURE_EVENT)
        return constants.REASSURE_EVENT
    record("world.speech", "Respond to ordinary explicit conversation.", event_selected=constants.CHAT_EVENT)
    return constants.CHAT_EVENT
