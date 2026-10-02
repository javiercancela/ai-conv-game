"""Apply probability-scaled changes to Maren's emotional state."""

from .decisions import Decisions
from .state import World


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def update_emotions(state: World, answers: Decisions, floor: float) -> None:
    """Mutate the new turn's state after its action passes confidence checks."""
    state.suspicion = clamp(
        state.suspicion + 0.30 * answers.hostility - 0.12 * answers.reassurance
    )
    state.trust = clamp(
        state.trust + 0.22 * answers.reassurance - 0.20 * answers.hostility
    )
    if answers.tension_confidence >= floor:
        state.composure = clamp(
            state.composure + 0.08 * answers.reassurance - 0.22 * answers.tension
        )
