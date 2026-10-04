"""Coordinate one authoritative world turn."""

from copy import deepcopy
from dataclasses import asdict, replace

from ..trace import log_context, record
from .actions import resolve_action, resolve_speech
from .decisions import Action, Decisions
from . import directive_constants as constants
from .directives import Beat, Directive, Speaker
from .emotions import update_emotions
from .outcomes import finish_turn
from .state import World
from .validation import blocked_event
from .facts import PreparedObservation, commit_observation


def advance(world: World, answers: Decisions, floor: float = 0.6,
            observation: PreparedObservation | None = None) -> tuple[World, Directive]:
    """Interpret one snapshot, then resolve physical actions before accompanying speech."""
    if observation and observation.proposal_id in world.facts.commits:
        receipt = world.facts.commits[observation.proposal_id]
        if receipt.directive is None:
            raise ValueError("Incomplete observation commit.")
        record("observation.replayed", "Return the original committed response without applying another turn.",
               proposal_id=receipt.proposal_id, revision=receipt.revision)
        return world, receipt.directive
    if world.ending != "playing":
        raise ValueError("This encounter has ended.")
    with log_context(turn=world.turn + 1):
        record("world.interpretation", "Resolve Jev's validated interpretation using Python rules; physical actions precede speech.",
               answers=asdict(answers), before=world.snapshot(), confidence_floor=floor)
        state = deepcopy(world)
        state.turn += 1

        event = blocked_event(answers, floor)
        if event is not None:
            state.revision += 1
            return finish_turn(state, (event,))

        if answers.action.value == Action.OBSERVE:
            if observation is None:
                raise ValueError("An observation must be prepared before advancing its turn.")
            receipt = commit_observation(state, observation)
            directive = Directive((constants.OBSERVATION_EVENT,), tuple(
                Beat(Speaker.NARRATOR, statement, statement, approved=True) for statement in receipt.statements
            ))
            state.revision += 1
            state, directive = finish_turn(state, (constants.OBSERVATION_EVENT,), observation=directive)
            state.facts.commits[receipt.proposal_id] = replace(receipt, directive=directive)
            record("observation.committed", "Publish the accepted descriptive patch, evidence, and evaluated turn together.",
                   proposal_id=receipt.proposal_id, query=asdict(observation.resolution.query),
                   access_evidence=observation.resolution.perception.access_evidence,
                   reused_fact_ids=observation.resolution.reuse_fact_ids,
                   patch=observation.resolution.payload(), fact_ids=receipt.fact_ids,
                   revision=state.revision, statements=receipt.statements)
            return state, directive
        if observation is not None:
            raise ValueError("Only an accepted observation action can commit a descriptive patch.")

        update_emotions(state, answers, floor)
        events = []
        action_event = resolve_action(state, answers)
        if action_event is not None:
            events.append(action_event)
        # A grab is blocked and provokes its own reaction, regardless of accompanying words.
        if answers.action.value != Action.TAKE_KEY:
            speech_event = resolve_speech(world, state, answers, floor)
            if speech_event is not None:
                events.append(speech_event)
        else:
            record("world.speech", "The blocked key grab supplies its own reaction, so accompanying speech is not resolved.")
        state.revision += 1
        return finish_turn(state, tuple(events))
