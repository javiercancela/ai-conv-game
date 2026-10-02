"""Apply encounter endings and explain unmet requirements for lending the key."""

from dataclasses import replace

from . import directive_constants as constants
from .directives import DIRECTIVES, Directive
from .state import World


def refusal_dialogue(state: World) -> str:
    needs: list[str] = []
    if not state.ledger_read:
        needs.append("read the tide ledger")
    if not state.plan_agreed:
        needs.append("promise to take a rope, use the east steps, and return the key")
    if state.trust < 0.55 or state.suspicion >= 0.65:
        needs.append("give me reason to trust you")
    request = " and ".join(needs) if needs else "ask me clearly to lend you the key"
    return f"The key stays with me for now. First, {request}."


def finish_turn(state: World, event: str) -> tuple[World, Directive]:
    """Resolve a win before a loss or timeout, then choose the final directive."""
    if event == constants.WON_EVENT:
        state.key_given = True
        state.ending = constants.WON_EVENT
    elif state.suspicion >= 0.9 or state.composure <= 0.1:
        event = state.ending = constants.LOST_EVENT
    elif state.turn >= state.max_turns:
        event = state.ending = constants.TIMEOUT_EVENT

    directive = DIRECTIVES[event]
    if event == constants.REFUSE_EVENT:
        directive = replace(directive, fallback=refusal_dialogue(state))
    return state, directive
