"""Event names, narrator instructions, and fallback dialogue for world directives."""

from typing import Final


CLARIFY_EVENT: Final[str] = "clarify"
CLARIFY_INSTRUCTION: Final[str] = (
    "Ask the player to clarify; assume no action occurred."
)
CLARIFY_FALLBACK: Final[str] = (
    "You'll have to be clearer with me. What exactly are you asking?"
)


OFF_WORLD_EVENT: Final[str] = "off_world"
OFF_WORLD_INSTRUCTION: Final[str] = "Redirect strange or meta talk back to the rescue."
OFF_WORLD_FALLBACK: Final[str] = (
    "I've no time for riddles about other worlds. There's a rescue to arrange."
)


LEDGER_EVENT: Final[str] = "ledger"
LEDGER_INSTRUCTION: Final[str] = (
    "Let the player read the ledger: east steps are sheltered; take a rope and "
    "return the key."
)
LEDGER_FALLBACK: Final[str] = (
    "The ledger marks the east steps as sheltered from the storm. Take a rope and "
    "promise to return my key."
)


KEY_EVENT: Final[str] = "key"
KEY_INSTRUCTION: Final[str] = (
    "Explain the key opens the rescue skiff locker; do not hand it over."
)
KEY_FALLBACK: Final[str] = (
    "This brass key opens the rescue skiff locker. Read the ledger before asking me "
    "to risk it."
)


BELL_EVENT: Final[str] = "bell"
BELL_INSTRUCTION: Final[str] = (
    "Explain the brass bell signals danger; nobody else enters the scene."
)
BELL_FALLBACK: Final[str] = (
    "That bell signals trouble on the water. I'd rather leave it silent tonight."
)


PLAN_EVENT: Final[str] = "plan"
PLAN_INSTRUCTION: Final[str] = (
    "Acknowledge the agreed plan: rope, sheltered east steps, return key; invite a "
    "request for the key."
)
PLAN_FALLBACK: Final[str] = (
    "Rope, east steps, and my key back afterward: that's a plan I can accept. Ask "
    "for the key when you're ready."
)


REASSURE_EVENT: Final[str] = "reassure"
REASSURE_INSTRUCTION: Final[str] = (
    "Respond to reassurance, keeping the rescue and safety requirements in mind."
)
REASSURE_FALLBACK: Final[str] = (
    "Steady words help on a night like this. Show me you've thought about getting "
    "back safely."
)


REFUSE_EVENT: Final[str] = "refuse"
REFUSE_INSTRUCTION: Final[str] = (
    "Refuse the key for now and explain the missing requirements from the current "
    "state."
)
REFUSE_FALLBACK: Final[str] = (
    "You'll need to read the ledger and promise to take a rope, use the east steps, "
    "and return my key. I also need to trust you before I lend it."
)


THREATEN_EVENT: Final[str] = "threaten"
THREATEN_INSTRUCTION: Final[str] = (
    "React warily to the threat; do not surrender the key."
)
THREATEN_FALLBACK: Final[str] = (
    "Threats won't get that locker open. Mind your words in my office."
)


CHAT_EVENT: Final[str] = "chat"
CHAT_INSTRUCTION: Final[str] = (
    "Answer briefly in character and point toward the ledger and the rescue."
)
CHAT_FALLBACK: Final[str] = (
    "The storm has stranded someone beyond the harbor wall. If you're going to "
    "help, start with the ledger on my desk."
)


WON_EVENT: Final[str] = "won"
WON_INSTRUCTION: Final[str] = (
    "Hand the brass key to the player; authorize the agreed rescue plan."
)
WON_FALLBACK: Final[str] = (
    "Here's the brass key; take the rope and launch from the east steps. Bring "
    "yourself and my key back safely."
)


LOST_EVENT: Final[str] = "lost"
LOST_INSTRUCTION: Final[str] = (
    "End the encounter: refuse the rescue key and ask the player to leave."
)
LOST_FALLBACK: Final[str] = (
    "We're done here, and the key stays with me. Leave my office now."
)


TIMEOUT_EVENT: Final[str] = "timeout"
TIMEOUT_INSTRUCTION: Final[str] = (
    "End the encounter: the tide has closed the rescue window; keep the key."
)
TIMEOUT_FALLBACK: Final[str] = (
    "The tide has turned and the crossing is closed. I can't send you out now."
)
