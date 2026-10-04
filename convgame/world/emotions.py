"""Apply probability-scaled changes to Maren's emotional state."""

from ..trace import record
from .decisions import Action, Decisions, Recipient
from .state import World


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def update_emotions(state: World, answers: Decisions, floor: float) -> None:
    """Mutate the new turn's state after its action passes confidence checks."""
    speaking = answers.recipient.value == Recipient.MAREN
    if not speaking and answers.action.value in (Action.NONE, Action.INSPECT, Action.OBSERVE):
        record("world.emotions", "Quiet inspection and private intentions cannot change Maren's emotions.",
               changed=False)
        return
    before = {"trust": state.trust, "suspicion": state.suspicion, "composure": state.composure}
    reassurance = answers.reassurance if speaking else 0
    hostility = answers.hostility if speaking else 0
    if answers.action.value == Action.TAKE_KEY:
        hostility = 1
        reassurance = 0
    state.suspicion = clamp(
        state.suspicion + 0.30 * hostility - 0.12 * reassurance
    )
    state.trust = clamp(
        state.trust + 0.22 * reassurance - 0.20 * hostility
    )
    if answers.tension_confidence >= floor:
        state.composure = clamp(
            state.composure + 0.08 * reassurance - 0.22 * answers.tension
        )
    record("world.emotions", "A key grab forces maximum hostility and ignores reassurance."
           if answers.action.value == Action.TAKE_KEY else
           "Apply probability-scaled hostility and reassurance from explicit speech; only confident tension changes composure.",
           before=before, after={"trust": state.trust, "suspicion": state.suspicion, "composure": state.composure},
           applied_hostility=hostility, applied_reassurance=reassurance,
           tension=answers.tension, tension_confidence=answers.tension_confidence,
           composure_update=answers.tension_confidence >= floor, confidence_floor=floor,
           formulas={"suspicion": "clamp(before + 0.30 * hostility - 0.12 * reassurance)",
                     "trust": "clamp(before + 0.22 * reassurance - 0.20 * hostility)",
                     "composure": "clamp(before + 0.08 * reassurance - 0.22 * tension) when confidence >= floor"})
