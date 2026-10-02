"""Build the eight independent questions sent in a single request."""

from collections.abc import Mapping

from typesafe_sdk import Choice, Noul, Questions, Score

from . import question_constants as constants


def _choice(prompt: str, criteria: Mapping[str, str | None]) -> Choice:
    return Choice(
        instructions=constants.INTERPRETATION_INSTRUCTIONS + prompt,
        criteria=dict(criteria),
    )


def _yes_no(prompt: str) -> Choice:
    return _choice(prompt, constants.YES_NO_CRITERIA)


def _probability(prompt: str) -> Noul:
    return Noul(instructions=constants.INTERPRETATION_INSTRUCTIONS + prompt)


def questions() -> Questions:
    return {
        constants.INTENT_QUESTION: _choice(constants.INTENT_PROMPT, constants.INTENT_CRITERIA),
        constants.OBJECT_QUESTION: _choice(constants.OBJECT_PROMPT, constants.OBJECT_CRITERIA),
        constants.OFF_WORLD_QUESTION: _yes_no(constants.OFF_WORLD_PROMPT),
        constants.RESCUE_PLAN_QUESTION: _yes_no(constants.RESCUE_PLAN_PROMPT),
        constants.HANDOVER_QUESTION: _yes_no(constants.HANDOVER_PROMPT),
        constants.TENSION_QUESTION: Score(
            instructions=constants.INTERPRETATION_INSTRUCTIONS + constants.TENSION_PROMPT,
            criteria=constants.TENSION_CRITERIA,
        ),
        constants.HOSTILITY_QUESTION: _probability(constants.HOSTILITY_PROMPT),
        constants.REASSURANCE_QUESTION: _probability(constants.REASSURANCE_PROMPT),
    }
