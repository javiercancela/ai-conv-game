"""Event names, narrator instructions, and fallback dialogue for world directives."""

from typing import Final


CLARIFY_EVENT: Final[str] = "clarify"
CLARIFY_INSTRUCTION: Final[str] = (
    "Ask the player to clarify the unresolved intention or explicitly address Maren; do not invent an outcome."
)
CLARIFY_FALLBACK: Final[str] = (
    "Your intention is unclear. Describe an action, or address Maren with what you want to say."
)


OFF_WORLD_EVENT: Final[str] = "off_world"
OFF_WORLD_INSTRUCTION: Final[str] = "Redirect the player to the harbor scene without making Maren speak."
OFF_WORLD_FALLBACK: Final[str] = (
    "The storm continues outside the harbor office. Describe an action here, or speak to Maren about the rescue."
)


LEDGER_EVENT: Final[str] = "ledger"
LEDGER_INSTRUCTION: Final[str] = (
    "Describe only the ledger's written advice: the east steps are sheltered, and the notes "
    "recommend taking a rope and returning the key. Reading these notes does not make a promise. "
    "Do not put a rope in the office or invent player speech. Maren does not speak."
)
LEDGER_FALLBACK: Final[str] = (
    "You read the tide ledger: the east steps are sheltered from the storm. "
    "Its notes recommend taking a rope and returning the rescue key afterward."
)


KEY_EVENT: Final[str] = "key"
KEY_INSTRUCTION: Final[str] = (
    "Describe the brass rescue key on Maren's belt; it opens the skiff locker and stays with him."
)
KEY_FALLBACK: Final[str] = (
    "The brass rescue key hangs from Maren's belt. It opens the rescue skiff locker and remains in his possession."
)


BELL_EVENT: Final[str] = "bell"
BELL_INSTRUCTION: Final[str] = (
    "Describe the brass alarm bell on the desk; it signals danger but has not been rung by this inspection."
)
BELL_FALLBACK: Final[str] = (
    "The brass alarm bell stands on the desk, ready to signal danger on the water. You examine it without ringing it."
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
    "Authorize the agreed rescue plan after handing over the key."
)
WON_FALLBACK: Final[str] = (
    "Take the rope and launch from the east steps. Bring "
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
    "Describe the tide closing the rescue window; the key stays with Maren."
)
TIMEOUT_FALLBACK: Final[str] = (
    "The tide turns, closing the crossing before you can begin the rescue. The brass key remains with Maren."
)


UNSPOKEN_EVENT: Final[str] = "unspoken"
UNSPOKEN_INSTRUCTION: Final[str] = (
    "No physical action or explicit speech to Maren was established. Explain how to act or speak; "
    "do not repeat private thoughts or make Maren respond to them."
)
UNSPOKEN_FALLBACK: Final[str] = (
    'No action or spoken words reach Maren. Describe an action, address him with "Maren, ...", '
    'or write "I say to Maren ..." to speak.'
)
TAKE_KEY_EVENT: Final[str] = "take_key"
RING_BELL_EVENT: Final[str] = "ring_bell"
OBSERVATION_EVENT: Final[str] = "observation"
MIXED_OBSERVATION_EVENT: Final[str] = "mixed_observation"
ACTION_EVENTS: Final[frozenset[str]] = frozenset({
    LEDGER_EVENT, KEY_EVENT, BELL_EVENT, TAKE_KEY_EVENT, RING_BELL_EVENT, OBSERVATION_EVENT,
})
SPEECH_EVENTS: Final[frozenset[str]] = frozenset({
    "ask_ledger", "ask_key", "ask_bell", PLAN_EVENT, REASSURE_EVENT,
    REFUSE_EVENT, THREATEN_EVENT, CHAT_EVENT, WON_EVENT,
})
GUIDANCE_EVENTS: Final[frozenset[str]] = frozenset({
    CLARIFY_EVENT, OFF_WORLD_EVENT, UNSPOKEN_EVENT, MIXED_OBSERVATION_EVENT,
})
