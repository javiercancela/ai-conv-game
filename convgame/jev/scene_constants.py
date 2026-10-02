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
    ),
}
