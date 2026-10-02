"""Narration directives selected by the authoritative world rules."""

from dataclasses import dataclass
from typing import Final

from . import directive_constants as constants


@dataclass(frozen=True)
class Directive:
    event: str
    instruction: str
    fallback: str


DIRECTIVES: Final[dict[str, Directive]] = {
    constants.CLARIFY_EVENT: Directive(
        event=constants.CLARIFY_EVENT,
        instruction=constants.CLARIFY_INSTRUCTION,
        fallback=constants.CLARIFY_FALLBACK,
    ),
    constants.OFF_WORLD_EVENT: Directive(
        event=constants.OFF_WORLD_EVENT,
        instruction=constants.OFF_WORLD_INSTRUCTION,
        fallback=constants.OFF_WORLD_FALLBACK,
    ),
    constants.LEDGER_EVENT: Directive(
        event=constants.LEDGER_EVENT,
        instruction=constants.LEDGER_INSTRUCTION,
        fallback=constants.LEDGER_FALLBACK,
    ),
    constants.KEY_EVENT: Directive(
        event=constants.KEY_EVENT,
        instruction=constants.KEY_INSTRUCTION,
        fallback=constants.KEY_FALLBACK,
    ),
    constants.BELL_EVENT: Directive(
        event=constants.BELL_EVENT,
        instruction=constants.BELL_INSTRUCTION,
        fallback=constants.BELL_FALLBACK,
    ),
    constants.PLAN_EVENT: Directive(
        event=constants.PLAN_EVENT,
        instruction=constants.PLAN_INSTRUCTION,
        fallback=constants.PLAN_FALLBACK,
    ),
    constants.REASSURE_EVENT: Directive(
        event=constants.REASSURE_EVENT,
        instruction=constants.REASSURE_INSTRUCTION,
        fallback=constants.REASSURE_FALLBACK,
    ),
    constants.REFUSE_EVENT: Directive(
        event=constants.REFUSE_EVENT,
        instruction=constants.REFUSE_INSTRUCTION,
        fallback=constants.REFUSE_FALLBACK,
    ),
    constants.THREATEN_EVENT: Directive(
        event=constants.THREATEN_EVENT,
        instruction=constants.THREATEN_INSTRUCTION,
        fallback=constants.THREATEN_FALLBACK,
    ),
    constants.CHAT_EVENT: Directive(
        event=constants.CHAT_EVENT,
        instruction=constants.CHAT_INSTRUCTION,
        fallback=constants.CHAT_FALLBACK,
    ),
    constants.WON_EVENT: Directive(
        event=constants.WON_EVENT,
        instruction=constants.WON_INSTRUCTION,
        fallback=constants.WON_FALLBACK,
    ),
    constants.LOST_EVENT: Directive(
        event=constants.LOST_EVENT,
        instruction=constants.LOST_INSTRUCTION,
        fallback=constants.LOST_FALLBACK,
    ),
    constants.TIMEOUT_EVENT: Directive(
        event=constants.TIMEOUT_EVENT,
        instruction=constants.TIMEOUT_INSTRUCTION,
        fallback=constants.TIMEOUT_FALLBACK,
    ),
}
