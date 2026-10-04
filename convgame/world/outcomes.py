"""Apply encounter endings and explain unmet requirements for lending the key."""

from dataclasses import asdict, replace

from ..trace import record
from . import directive_constants as constants
from .directives import DIRECTIVES, Directive, Speaker
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


def finish_turn(state: World, events: tuple[str, ...], observation: Directive | None = None) -> tuple[World, Directive]:
    """Resolve a win before a loss or timeout, then choose the final directive."""
    if constants.WON_EVENT in events:
        state.key_given = True
        state.ending = constants.WON_EVENT
        reason = "An authorized handover wins before checking loss or timeout."
    elif state.suspicion >= 0.9 or state.composure <= 0.1:
        state.ending = constants.LOST_EVENT
        reason = "End the encounter because suspicion reached 0.9 or composure fell to 0.1; loss takes precedence over timeout."
    elif state.turn >= state.max_turns:
        state.ending = constants.TIMEOUT_EVENT
        reason = "The turn limit was reached without an authorized handover."
    else:
        reason = "Continue: no handover, emotional ending, or turn limit was reached."
    record("world.ending", reason, ending=state.ending, turn=state.turn,
           max_turns=state.max_turns, suspicion=state.suspicion, composure=state.composure)

    directives = [observation if event == constants.OBSERVATION_EVENT and observation else DIRECTIVES[event]
                  for event in events]
    if state.ending in (constants.LOST_EVENT, constants.TIMEOUT_EVENT):
        # Retain physical outcomes, but the ending replaces pending conversation.
        outcome_beats = tuple(
            beat for directive in directives if directive.event in constants.ACTION_EVENTS
            for beat in directive.beats if beat.speaker == Speaker.NARRATOR
        )
        ending = DIRECTIVES[state.ending]
        directive = Directive(events + ending.events, outcome_beats + ending.beats)
        record("world.directive", "The ending replaces pending conversation while retaining physical narration.",
               directive=asdict(directive), after=state.snapshot())
        return state, directive
    if not directives:
        directives = [DIRECTIVES[constants.UNSPOKEN_EVENT]]
    beats = []
    for directive in directives:
        for beat in directive.beats:
            if directive.event == constants.REFUSE_EVENT:
                beat = replace(beat, fallback=refusal_dialogue(state))
            beats.append(beat)
    directive = Directive(tuple(event for directive in directives for event in directive.events), tuple(beats))
    record("world.directive", "Choose ordered response beats from resolved events, or fixed unspoken guidance when no action or speech occurred.",
           directive=asdict(directive), after=state.snapshot())
    return state, directive
