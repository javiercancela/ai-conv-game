"""The fixed scene supplied to Jev on every turn."""

from typing import Final


SCENE: Final[dict[str, str | dict[str, str]]] = {
    "location": "A stormbound harbor office, a low-fantasy coastal town.",
    "characters": "Only the player and Maren, a cautious, gruff harbor-master, are present.",
    "objective": "Borrow the brass key to the rescue skiff locker to rescue a stranded traveler.",
    "objects": {
        "key": "Brass key held by Maren, opens rescue skiff locker.",
        "ledger": "Open tide ledger on desk: east steps are sheltered; take a rope and return key.",
        "bell": "Brass alarm bell on desk; signals danger on the water.",
    },
    "rules": (
        "The player must read the ledger, agree to take a rope, use the east steps "
        "and return the key, then ask for the key. Python controls all state changes."
        " Physical actions and explicit speech are separate: only actual inspection marks the ledger read, "
        "only a promise spoken to Maren agrees the plan, and only a spoken request can obtain the key. "
        "Taking the key without a handover is blocked. Maren cannot hear private thoughts. "
        "The Narrator describes actions and observable outcomes; Maren speaks only when addressed "
        "or when the rules select a reaction to a significant action."
    ),
}
