"""Typed interpretations of the player's latest line."""

from dataclasses import dataclass
from enum import StrEnum


class Intent(StrEnum):
    """The purpose of explicit speech, independent of physical actions."""

    NONE = "none"
    ASK_ABOUT = "ask_about"
    REASSURE = "reassure"
    PERSUADE = "persuade"
    REQUEST = "request"
    THREATEN = "threaten"
    CHAT = "chat"
    UNCLEAR = "unclear"


class Action(StrEnum):
    NONE = "none"
    INSPECT = "inspect"
    OBSERVE = "observe"
    TAKE_KEY = "take_key"
    RING_BELL = "ring_bell"
    UNCLEAR = "unclear"


class Recipient(StrEnum):
    NONE = "none"
    MAREN = "maren"
    UNKNOWN = "unknown"


class Object(StrEnum):
    KEY = "key"
    LEDGER = "ledger"
    BELL = "bell"
    NONE = "none"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Pick:
    value: str
    confidence: float


@dataclass(frozen=True)
class Decisions:
    action: Pick
    action_object: Pick
    recipient: Pick
    intent: Pick
    object: Pick
    off_world: Pick
    rescue_plan: Pick
    handover: Pick
    tension: float  # normalized 0..1, from Jev's 0..2 Score
    tension_confidence: float
    hostility: float  # Noul probability, NOT confidence
    reassurance: float
