"""Ordered narration and speech selected by the authoritative world rules."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from . import directive_constants as constants


class Speaker(StrEnum):
    NARRATOR = "Narrator"
    MAREN = "Maren"


@dataclass(frozen=True)
class NarrativeLine:
    speaker: Speaker
    text: str


@dataclass(frozen=True)
class Beat:
    speaker: Speaker
    instruction: str
    fallback: str


@dataclass(frozen=True)
class Directive:
    events: tuple[str, ...]
    beats: tuple[Beat, ...]

    @property
    def event(self) -> str:
        return self.events[-1]

    @property
    def player_spoke(self) -> bool:
        return any(event in constants.SPEECH_EVENTS for event in self.events)

    @property
    def scripted_guidance(self) -> bool:
        return self.event in constants.GUIDANCE_EVENTS

    @property
    def fallback(self) -> tuple[NarrativeLine, ...]:
        return tuple(NarrativeLine(beat.speaker, beat.fallback) for beat in self.beats)


def _narration(event: str, instruction: str, fallback: str) -> Directive:
    return Directive((event,), (Beat(Speaker.NARRATOR, instruction, fallback),))


def _speech(event: str, instruction: str, fallback: str) -> Directive:
    return Directive((event,), (Beat(Speaker.MAREN, instruction, fallback),))


DIRECTIVES: Final[dict[str, Directive]] = {
    constants.CLARIFY_EVENT: _narration(constants.CLARIFY_EVENT, constants.CLARIFY_INSTRUCTION, constants.CLARIFY_FALLBACK),
    constants.OFF_WORLD_EVENT: _narration(constants.OFF_WORLD_EVENT, constants.OFF_WORLD_INSTRUCTION, constants.OFF_WORLD_FALLBACK),
    constants.UNSPOKEN_EVENT: _narration(constants.UNSPOKEN_EVENT, constants.UNSPOKEN_INSTRUCTION, constants.UNSPOKEN_FALLBACK),
    constants.LEDGER_EVENT: _narration(constants.LEDGER_EVENT, constants.LEDGER_INSTRUCTION, constants.LEDGER_FALLBACK),
    constants.KEY_EVENT: _narration(constants.KEY_EVENT, constants.KEY_INSTRUCTION, constants.KEY_FALLBACK),
    constants.BELL_EVENT: _narration(constants.BELL_EVENT, constants.BELL_INSTRUCTION, constants.BELL_FALLBACK),
    "ask_ledger": _speech(
        "ask_ledger", "Explain the ledger's advice; answering a question does not mean the player has read it.",
        "The ledger marks the east steps as sheltered. Read it, then promise to take a rope and return my key.",
    ),
    "ask_key": _speech("ask_key", "Explain the key opens the skiff locker; keep it.",
                       "This key opens the rescue skiff locker. You'll need a safe plan before I lend it."),
    "ask_bell": _speech("ask_bell", "Explain the bell signals danger; it has not been rung by this question.",
                        "That bell signals danger on the water. Leave it silent unless there's trouble."),
    constants.PLAN_EVENT: _speech(constants.PLAN_EVENT, constants.PLAN_INSTRUCTION, constants.PLAN_FALLBACK),
    constants.REASSURE_EVENT: _speech(constants.REASSURE_EVENT, constants.REASSURE_INSTRUCTION, constants.REASSURE_FALLBACK),
    constants.REFUSE_EVENT: _speech(constants.REFUSE_EVENT, constants.REFUSE_INSTRUCTION, constants.REFUSE_FALLBACK),
    constants.THREATEN_EVENT: _speech(constants.THREATEN_EVENT, constants.THREATEN_INSTRUCTION, constants.THREATEN_FALLBACK),
    constants.CHAT_EVENT: _speech(constants.CHAT_EVENT, constants.CHAT_INSTRUCTION, constants.CHAT_FALLBACK),
    constants.WON_EVENT: Directive((constants.WON_EVENT,), (
        Beat(Speaker.NARRATOR, "Describe Maren handing the brass key to the player; it is now in their hand.",
             "Maren unhooks the brass key from his belt and places it in your hand."),
        Beat(Speaker.MAREN, constants.WON_INSTRUCTION, constants.WON_FALLBACK),
    )),
    constants.LOST_EVENT: Directive((constants.LOST_EVENT,), (
        Beat(Speaker.NARRATOR, "Describe Maren ending the encounter and retaining the key, without revealing his thoughts.",
             "Maren covers the key with his hand and gestures toward the door."),
        Beat(Speaker.MAREN, constants.LOST_INSTRUCTION, constants.LOST_FALLBACK),
    )),
    constants.TIMEOUT_EVENT: _narration(constants.TIMEOUT_EVENT, constants.TIMEOUT_INSTRUCTION, constants.TIMEOUT_FALLBACK),
    constants.TAKE_KEY_EVENT: Directive((constants.TAKE_KEY_EVENT,), (
        Beat(Speaker.NARRATOR, "Describe Maren stepping back and guarding the key, blocking the player's attempted grab.",
             "You reach for the key, but Maren steps back and covers it with his hand."),
        Beat(Speaker.MAREN, "Warn the player to ask before touching the key; do not hand it over.",
             "Ask before you touch. The key stays with me."),
    )),
    constants.RING_BELL_EVENT: _narration(
        constants.RING_BELL_EVENT, "Describe the alarm bell ringing and Maren looking toward it; nobody enters.",
        "You ring the brass alarm bell, its sharp note cutting through the rain. Maren turns toward the sound.",
    ),
}
