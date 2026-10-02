"""Validate Jev answers before they can change the world."""

import math
from collections.abc import Collection

from typesafe_sdk import ChoiceAnswer, SystemOneResponse

from ..world import Decisions, Intent, Object, Pick
from . import question_constants as constants


def _unit_interval(value: float) -> float:
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Jev returned an invalid probability or confidence.")
    return value


def _pick(answer: ChoiceAnswer, name: str, allowed: Collection[str]) -> Pick:
    if answer.choice not in allowed:
        raise ValueError(f"Jev returned an unknown {name}.")
    return Pick(answer.choice, _unit_interval(answer.confidence))


def decode(result: SystemOneResponse) -> Decisions:
    """Reject incomplete or malformed replies before returning decisions."""
    choices = result.choices
    tension = result.scores[constants.TENSION_QUESTION]
    return Decisions(
        intent=_pick(choices[constants.INTENT_QUESTION], constants.INTENT_QUESTION, set(Intent)),
        object=_pick(choices[constants.OBJECT_QUESTION], constants.OBJECT_QUESTION, set(Object)),
        off_world=_pick(
            choices[constants.OFF_WORLD_QUESTION],
            constants.OFF_WORLD_QUESTION,
            constants.YES_NO_CRITERIA,
        ),
        rescue_plan=_pick(
            choices[constants.RESCUE_PLAN_QUESTION],
            constants.RESCUE_PLAN_QUESTION,
            constants.YES_NO_CRITERIA,
        ),
        handover=_pick(
            choices[constants.HANDOVER_QUESTION],
            constants.HANDOVER_QUESTION,
            constants.YES_NO_CRITERIA,
        ),
        tension=_unit_interval(tension.score / constants.MAX_TENSION_SCORE),
        tension_confidence=_unit_interval(tension.confidence),
        hostility=_unit_interval(result.nouls[constants.HOSTILITY_QUESTION].noul),
        reassurance=_unit_interval(result.nouls[constants.REASSURANCE_QUESTION].noul),
    )
