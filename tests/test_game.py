from dataclasses import replace
import io
import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx2
import pytest
from typesafe_sdk import ChoiceAnswer, NoulAnswer, ScoreAnswer, TypeSafeClient

from convgame.bonsai import BonsaiNarrator, two_sentences
from convgame.cli import play
from convgame.demo import DemoDecider, DemoNarrator
from convgame.jev import JevDecider, decode, questions
from convgame.world import DIRECTIVES, Decisions, Pick, World, advance


def answers(**overrides):
    base = Decisions(Pick("chat", 0.95), Pick("none", 0.95), Pick("no", 0.95),
                     Pick("no", 0.95), Pick("no", 0.95), 0, 0.95, 0, 0)
    return replace(base, **overrides)


def test_complete_demo_win():
    world = World()
    decider = DemoDecider()
    events = []
    for line in ["I read the ledger.",
                 "I promise to take a rope, use the east steps, and return your key.",
                 "Please lend me the key."]:
        world, directive = advance(world, decider.decide(world, line))
        events.append(directive.event)
    assert world.ending == "won"
    assert world.key_given
    assert directive.event == "won"
    assert world.turn == 3
    assert events == ["ledger", "plan", "won"]


@pytest.mark.parametrize("line", [
    "I won't hurt you.",
    "I won’t hurt you.",
    "I will not hurt you.",
    "I don't want to hurt you.",
])
def test_demo_denial_of_violence_reassures_without_threat_penalties(line):
    world = World()
    for _ in range(3):
        decisions = DemoDecider().decide(world, line)
        assert decisions.intent.value == "reassure"
        assert decisions.hostility == 0
        assert decisions.tension == 0
        world, directive = advance(world, decisions)
        assert directive.event == "reassure"
    assert world.ending == "playing"
    assert world.suspicion <= World().suspicion
    assert world.trust >= World().trust


@pytest.mark.parametrize("line", [
    "I will hurt you.",
    "I won't hurt you, but I will kill you.",
    "I won't hurt you and I will kill you.",
])
def test_demo_explicit_threat_still_applies_penalties(line):
    decisions = DemoDecider().decide(World(), line)
    assert decisions.intent.value == "threaten"
    assert decisions.hostility == 1
    assert decisions.tension == 1
    updated, directive = advance(World(), decisions)
    assert directive.event == "threaten"
    assert updated.suspicion > World().suspicion
    assert updated.trust < World().trust


@pytest.mark.parametrize("change", [
    {"intent": Pick("request", 0.2)},
    {"intent": Pick("request", 0.95), "object": Pick("key", 0.2)},
    {"off_world": Pick("no", 0.2)},
])
def test_ambiguous_action_only_consumes_time(change):
    original = World()
    updated, directive = advance(original, answers(hostility=1, reassurance=1, **change))
    assert directive.event == "clarify"
    assert updated == replace(original, turn=1)
    assert original.turn == 0


def test_off_world_does_not_mutate_emotions_or_award_key():
    updated, directive = advance(World(), answers(off_world=Pick("yes", 1), hostility=1,
                                                handover=Pick("yes", 1)))
    assert directive.event == "off_world"
    assert updated == replace(World(), turn=1)


@pytest.mark.parametrize("world", [World(), World(ledger_read=True, trust=1),
    World(ledger_read=True, plan_agreed=True, trust=0.54),
    World(ledger_read=True, plan_agreed=True, trust=1, suspicion=0.7)])
def test_model_cannot_award_key_without_python_prerequisites(world):
    updated, directive = advance(world, answers(intent=Pick("request", 1), object=Pick("key", 1),
                                               handover=Pick("yes", 1)))
    assert not updated.key_given
    assert directive.event == "refuse"


def test_low_confidence_commitment_is_not_recorded():
    updated, _ = advance(World(ledger_read=True), answers(rescue_plan=Pick("yes", 0.3)))
    assert not updated.plan_agreed


def test_low_confidence_handover_is_clarified():
    updated, directive = advance(World(ledger_read=True, plan_agreed=True, trust=1),
        answers(intent=Pick("request", 1), object=Pick("key", 1), handover=Pick("yes", 0.2)))
    assert not updated.key_given
    assert directive.event == "clarify"


def test_noul_probability_scales_dial_but_score_confidence_gates_it():
    quiet, _ = advance(World(), answers(hostility=0.1, tension=1, tension_confidence=0.2))
    hostile, _ = advance(World(), answers(hostility=0.9, tension=1, tension_confidence=1))
    assert hostile.suspicion > quiet.suspicion
    assert quiet.composure == World().composure
    assert hostile.composure < quiet.composure


def test_threats_lose_and_terminal_state_cannot_advance():
    world = World()
    for _ in range(3):
        world, _ = advance(world, answers(intent=Pick("threaten", 1), hostility=1, tension=1))
    assert world.ending == "lost"
    assert 0 <= world.suspicion <= 1
    with pytest.raises(ValueError):
        advance(world, answers())


def test_timeout_and_last_turn_win():
    world, directive = advance(World(turn=11), answers())
    assert world.ending == directive.event == "timeout"
    world, _ = advance(World(turn=11, ledger_read=True, plan_agreed=True, trust=1),
        answers(intent=Pick("request", 1), object=Pick("key", 1), handover=Pick("yes", 1)))
    assert world.ending == "won"


def test_requesting_ledger_matches_narrated_action():
    world, directive = advance(World(), answers(intent=Pick("request", 1), object=Pick("ledger", 1)))
    assert world.ledger_read
    assert directive.event == "ledger"


def response_payload():
    choices = {"intent": "inspect", "object": "ledger", "off_world": "no",
               "rescue_plan": "no", "handover": "no"}
    result = {name: ChoiceAnswer(choice=value, confidence=0.9,
                                probabilities={value: 1.0}).model_dump()
              for name, value in choices.items()}
    result["tension"] = ScoreAnswer(score=1, confidence=0.8, legend={0: "calm", 1: "pushy", 2: "violent"},
                                    probabilities={0: 0, 1: 1, 2: 0}).model_dump()
    result["hostility"] = NoulAnswer(noul=0.1).model_dump()
    result["reassurance"] = NoulAnswer(noul=0.2).model_dump()
    return {"model": "jev-latest", "answers": result, "usage": {"input_tokens": 20, "output_tokens": 10}}


def test_real_sdk_batches_and_decodes_all_eight_questions():
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx2.Response(200, json=response_payload())

    decider = JevDecider.__new__(JevDecider)
    decider.client = TypeSafeClient(api_key="test-only", transport=httpx2.MockTransport(handle))
    decider.questions = questions()
    try:
        result = decider.decide(World(), "Read the ledger")
    finally:
        decider.close()
    assert len(requests) == 1
    assert len(requests[0]["questions"]) == 8
    assert requests[0]["state"]["player_line"] == "Read the ledger"
    assert result.object.value == "ledger"
    assert result.tension == 0.5
    assert result.hostility == 0.1


def test_incomplete_and_invalid_answers_fail_before_mutation():
    with pytest.raises(KeyError):
        decode(SimpleNamespace(choices={}, scores={"tension": SimpleNamespace(score=0)}))
    for value in [float("nan"), float("inf"), -0.1, 1.1]:
        choices = {name: SimpleNamespace(choice=choice, confidence=value)
                   for name, choice in {"intent": "chat", "object": "none", "off_world": "no",
                                        "rescue_plan": "no", "handover": "no"}.items()}
        with pytest.raises(ValueError):
            decode(SimpleNamespace(choices=choices, scores={"tension": SimpleNamespace(score=0)}))


def test_bonsai_http_contract_and_reasoning_removal():
    captured = []

    def open_request(request, timeout):
        captured.append((request, timeout))
        return io.BytesIO(json.dumps({"choices": [{"message": {
            "content": "<think>Internal thoughts.</think>Maren: Read the ledger. Then we can talk. Extra sentence.",
            "reasoning_content": "Never show this",
        }}]}).encode())

    with patch("urllib.request.urlopen", open_request):
        reply = BonsaiNarrator("http://localhost:8080/v1").narrate(World(), "Hello", DIRECTIVES["chat"])
    assert reply == "Read the ledger. Then we can talk."
    request, timeout = captured[0]
    body = json.loads(request.data)
    assert request.full_url == "http://localhost:8080/v1/chat/completions"
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["stream"] is False
    assert "authoritative_state" in json.loads(body["messages"][1]["content"])


@pytest.mark.parametrize("text", ["", "Just one sentence.", "<think>Unfinished", "No punctuation"])
def test_bad_narration_is_rejected(text):
    with pytest.raises(ValueError):
        two_sentences(text)


def test_cli_free_commands_and_winning_game(monkeypatch, capsys):
    lines = iter(["/help", "/status", "/look", "", "I read the ledger.",
                  "I promise to take a rope, use the east steps, and return your key.",
                  "Please lend me the key."])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    assert play(DemoDecider(), DemoNarrator(), debug=True) == 0
    output = capsys.readouterr().out
    assert "you win" in output
    assert "Turn 3/12" in output


def test_service_failures_do_not_double_apply_a_turn(monkeypatch, capsys):
    class Decider(DemoDecider):
        def __init__(self):
            self.failed = False

        def decide(self, world, line):
            if not self.failed:
                self.failed = True
                raise TimeoutError()
            assert world.turn == 0
            return super().decide(world, line)

    class Narrator:
        def narrate(self, *args):
            raise TimeoutError()

    lines = iter(["Read the ledger", "Read the ledger", "/status", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    play(Decider(), Narrator())
    output = capsys.readouterr()
    assert "Turn 1/12" in output.out
    assert "Ledger read: yes" in output.out
    assert "No turn used" in output.err
    assert "using scene dialogue" in output.err
