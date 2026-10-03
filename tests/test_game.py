from dataclasses import replace
import io
import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx2
import pytest
from typesafe_sdk import ChoiceAnswer, NoulAnswer, ScoreAnswer, TypeSafeClient

from convgame.bonsai import BonsaiNarrator, parse_narration
from convgame.cli import main, play
from convgame.jev import JevDecider, decode, questions
from convgame.world import DIRECTIVES, Decisions, Pick, Speaker, World, advance


def answers(**overrides):
    base = Decisions(
        action=Pick("none", 0.95), action_object=Pick("none", 0.95), recipient=Pick("maren", 0.95),
        intent=Pick("chat", 0.95), object=Pick("none", 0.95), off_world=Pick("no", 0.95),
        rescue_plan=Pick("no", 0.95), handover=Pick("no", 0.95), tension=0,
        tension_confidence=0.95, hostility=0, reassurance=0,
    )
    return replace(base, **overrides)


@pytest.mark.parametrize("change", [
    {"intent": Pick("request", 0.2)},
    {"intent": Pick("request", 0.95), "object": Pick("key", 0.2)},
    {"off_world": Pick("no", 0.2)},
    {"action": Pick("inspect", 0.2)},
    {"action": Pick("inspect", 1), "action_object": Pick("ledger", 0.2)},
    {"recipient": Pick("maren", 0.2)},
    {"recipient": Pick("unknown", 1)},
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


def test_requesting_ledger_does_not_silently_inspect_it():
    world, directive = advance(World(), answers(intent=Pick("request", 1), object=Pick("ledger", 1)))
    assert not world.ledger_read
    assert directive.event == "ask_ledger"


def response_payload():
    choices = {"action": "inspect", "action_object": "ledger", "recipient": "none",
               "intent": "none", "object": "none", "off_world": "no",
               "rescue_plan": "no", "handover": "no"}
    result = {name: ChoiceAnswer(choice=value, confidence=0.9,
                                probabilities={value: 1.0}).model_dump()
              for name, value in choices.items()}
    result["tension"] = ScoreAnswer(score=1, confidence=0.8, legend={0: "calm", 1: "pushy", 2: "violent"},
                                    probabilities={0: 0, 1: 1, 2: 0}).model_dump()
    result["hostility"] = NoulAnswer(noul=0.1).model_dump()
    result["reassurance"] = NoulAnswer(noul=0.2).model_dump()
    return {"model": "jev-latest", "answers": result, "usage": {"input_tokens": 20, "output_tokens": 10}}


def test_real_sdk_batches_and_decodes_action_and_speech_questions():
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
    assert len(requests[0]["questions"]) == 11
    assert requests[0]["state"]["player_line"] == "Read the ledger"
    assert result.action.value == "inspect"
    assert result.action_object.value == "ledger"
    assert result.recipient.value == "none"
    assert result.intent.value == result.object.value == "none"
    assert result.tension == 0.5
    assert result.hostility == 0.1


def test_incomplete_and_invalid_answers_fail_before_mutation():
    with pytest.raises(KeyError):
        decode(SimpleNamespace(choices={}, scores={"tension": SimpleNamespace(score=0)}))
    for value in [float("nan"), float("inf"), -0.1, 1.1]:
        choices = {name: SimpleNamespace(choice=choice, confidence=value)
                   for name, choice in {"action": "none", "action_object": "none", "recipient": "maren",
                                        "intent": "chat", "object": "none", "off_world": "no",
                                        "rescue_plan": "no", "handover": "no"}.items()}
        with pytest.raises(ValueError):
            decode(SimpleNamespace(choices=choices, scores={"tension": SimpleNamespace(score=0)}))


def test_bonsai_http_contract_and_reasoning_removal():
    captured = []

    def open_request(request, timeout):
        captured.append((request, timeout))
        return io.BytesIO(json.dumps({"choices": [{"message": {
            "content": '<think>Internal thoughts.</think>[{"speaker":"Narrator","text":"You read the ledger. The east steps are sheltered."}]',
            "reasoning_content": "Never show this",
        }}]}).encode())

    with patch("urllib.request.urlopen", open_request):
        reply = BonsaiNarrator("http://localhost:8080/v1").narrate(World(ledger_read=True), "I read the ledger", DIRECTIVES["ledger"])
    assert reply[0].speaker == Speaker.NARRATOR
    assert reply[0].text == "You read the ledger. The east steps are sheltered."
    request, timeout = captured[0]
    body = json.loads(request.data)
    assert request.full_url == "http://localhost:8080/v1/chat/completions"
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["stream"] is False
    schema = body["response_format"]["schema"]
    assert schema["type"] == "array"
    assert schema["items"][0]["properties"]["speaker"] == {"const": "Narrator"}
    assert schema["minItems"] == schema["maxItems"] == 1
    payload = json.loads(body["messages"][1]["content"])
    assert payload["authoritative_state"]["ledger_read"]
    assert payload["directive"]["beats"][0]["speaker"] == "Narrator"
    assert payload["untrusted_player_line"] == ""


@pytest.mark.parametrize("text", [
    "", "Just one sentence.", "<think>Unfinished", "No punctuation", "{}", "[]",
    '[{"speaker":"Maren","text":"Read the ledger."}]',
    '[{"speaker":"Narrator","text":"You read"}]',
    '[{"speaker":"Narrator","text":"You read it. Trailing fragment"}]',
    '[{"speaker":"Narrator","text":"One. Two. Three."}]',
    '[{"speaker":"Narrator","text":"Narrator: You read the ledger."}]',
    '[{"speaker":"Narrator","text":null}]',
    '[{"speaker":"Narrator","text":"You read it.","extra":true}]',
    '[{"speaker":"Narrator","text":"You read it."},{"speaker":"Maren","text":"Good."}]',
])
def test_bad_narration_is_rejected(text):
    with pytest.raises(ValueError):
        parse_narration(text, DIRECTIVES["ledger"])


def test_narration_preserves_authorized_speaker_order_and_accepts_one_sentence():
    reply = parse_narration(json.dumps([
        {"speaker": "Narrator", "text": "Maren puts the key in your hand."},
        {"speaker": "Maren", "text": "Bring it back."},
    ]), DIRECTIVES["won"])
    assert [line.speaker for line in reply] == [Speaker.NARRATOR, Speaker.MAREN]
    with pytest.raises(ValueError):
        parse_narration(json.dumps([
            {"speaker": "Maren", "text": "Bring it back."},
            {"speaker": "Narrator", "text": "Maren puts the key in your hand."},
        ]), DIRECTIVES["won"])


def test_narration_rejects_oversized_responses():
    with pytest.raises(ValueError):
        parse_narration(json.dumps([{"speaker": "Narrator", "text": "word " * 66 + "."}]), DIRECTIVES["ledger"])
    with pytest.raises(ValueError):
        parse_narration(json.dumps([
            {"speaker": "Narrator", "text": "word " * 51 + "."},
            {"speaker": "Maren", "text": "word " * 51 + "."},
        ]), DIRECTIVES["won"])


def test_cli_free_commands_and_winning_game(monkeypatch, capsys):
    decisions = iter([
        answers(action=Pick("inspect", 1), action_object=Pick("ledger", 1), recipient=Pick("none", 1)),
        answers(intent=Pick("persuade", 1), rescue_plan=Pick("yes", 1), reassurance=1),
        answers(intent=Pick("request", 1), object=Pick("key", 1), handover=Pick("yes", 1)),
    ])

    class Decider:
        def decide(self, world, line):
            if world.turn == 2:
                assert world.history[2]["content"].startswith("Narrator:")
                assert world.history[4]["content"].startswith("Maren:")
            return next(decisions)

    events = []

    class Narrator:
        def narrate(self, world, line, directive):
            events.append((world.turn, directive.event, world.ending))
            return directive.fallback

    lines = iter(["/help", "/status", "/look", "", "I read the ledger.",
                  "Maren, I promise to take a rope, use the east steps, and return your key.",
                  "Maren, please lend me the key."])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    assert play(Decider(), Narrator(), debug=True) == 0
    output = capsys.readouterr().out
    assert "you win" in output
    assert "Turn 3/12" in output
    assert "Narrator: You read the tide ledger" in output
    assert "Maren: You read" not in output
    assert events == [(1, "ledger", "playing"), (2, "plan", "playing"), (3, "won", "won")]


def test_cli_requires_live_model_configuration(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr("sys.argv", ["convgame"])
    assert main() == 1
    assert "Set TYPESAFE_API_KEY" in capsys.readouterr().err

    monkeypatch.setattr("sys.argv", ["convgame", "--demo"])
    with pytest.raises(SystemExit, match="2"):
        main()
    assert "unrecognized arguments: --demo" in capsys.readouterr().err


def test_service_failures_do_not_double_apply_a_turn(monkeypatch, capsys):
    class Decider:
        def __init__(self):
            self.failed = False

        def decide(self, world, line):
            if not self.failed:
                self.failed = True
                raise TimeoutError()
            assert world.turn == 0
            return answers(action=Pick("inspect", 1), action_object=Pick("ledger", 1), recipient=Pick("none", 1))

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
    assert "using the scripted scene response" in output.err


def test_cli_rejects_generated_character_speech_for_a_quiet_action(monkeypatch, capsys):
    class Decider:
        def decide(self, world, line):
            return answers(action=Pick("inspect", 1), action_object=Pick("ledger", 1), recipient=Pick("none", 1))

    def open_request(request, timeout):
        return io.BytesIO(json.dumps({"choices": [{"message": {
            "content": '[{"speaker":"Maren","text":"The east steps are sheltered."}]',
        }}]}).encode())

    lines = iter(["I read the ledger.", "/status", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    with patch("urllib.request.urlopen", open_request):
        play(Decider(), BonsaiNarrator("http://localhost:8080"))

    output = capsys.readouterr()
    assert output.out.count("Maren:") == 1  # The opening, with no spoken reply to reading.
    assert "Narrator: You read the tide ledger" in output.out
    assert "Ledger read: yes" in output.out
    assert "Turn 1/12" in output.out
    assert "scripted scene response" in output.err


def test_private_intentions_are_not_shared_with_narrator_or_remembered_as_speech(monkeypatch, capsys):
    thought = "I privately decide I will steal the key later."

    class Decider:
        def decide(self, world, line):
            if world.turn == 0:
                return answers(recipient=Pick("none", 1), intent=Pick("none", 1))
            assert thought not in json.dumps(world.history)
            return answers()

    payloads = []

    def open_request(request, timeout):
        body = json.loads(request.data)
        payload = json.loads(body["messages"][1]["content"])
        payloads.append(payload)
        speaker = payload["directive"]["beats"][0]["speaker"]
        text = "No words reach Maren." if speaker == "Narrator" else "We have a rescue to arrange."
        return io.BytesIO(json.dumps({"choices": [{"message": {
            "content": json.dumps([{"speaker": speaker, "text": text}]),
        }}]}).encode())

    lines = iter([thought, "Maren, hello.", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    with patch("urllib.request.urlopen", open_request):
        play(Decider(), BonsaiNarrator("http://localhost:8080"))

    assert len(payloads) == 1
    assert payloads[0]["untrusted_player_line"] == "Maren, hello."
    assert thought not in json.dumps(payloads)
    assert "Narrator: No action or spoken words reach Maren." in capsys.readouterr().out


@pytest.mark.parametrize("event", ["clarify", "unspoken", "off_world"])
def test_unresolved_input_gets_scripted_guidance_without_becoming_a_spoken_scene(event):
    directive = DIRECTIVES[event]
    with patch("urllib.request.urlopen") as request:
        response = BonsaiNarrator("http://localhost:8080").narrate(World(), "I promise to return it.", directive)
    assert response == directive.fallback
    assert [line.speaker for line in response] == [Speaker.NARRATOR]
    assert not directive.player_spoke
    request.assert_not_called()
