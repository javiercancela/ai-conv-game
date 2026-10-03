"""Execution logs must explain real service calls, rule choices, and failures."""

from dataclasses import replace
import io
import json

import httpx2
import pytest
from typesafe_sdk import ChoiceAnswer, NoulAnswer, RetryPolicy, ScoreAnswer, TypeSafeClient

from convgame.bonsai import BonsaiNarrator
from convgame.cli import main, play
from convgame.jev import JevDecider, questions
from convgame.trace import file_log, record
from convgame.world import DIRECTIVES, Decisions, Pick, World, advance


NEUTRAL = Decisions(
    action=Pick("none", 1), action_object=Pick("none", 1), recipient=Pick("maren", 1),
    intent=Pick("chat", 1), object=Pick("none", 1), off_world=Pick("no", 1),
    rescue_plan=Pick("no", 1), handover=Pick("no", 1), tension=0,
    tension_confidence=1, hostility=0, reassurance=0,
)


def entries(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def jev_response(**overrides):
    choices = dict(action="none", action_object="none", recipient="maren", intent="chat",
                   object="none", off_world="no", rescue_plan="no", handover="no")
    reassurance = overrides.pop("reassurance", 0)
    choices.update(overrides)
    answers = {name: ChoiceAnswer(choice=value, confidence=1,
                                 probabilities={value: 1}).model_dump(mode="json")
               for name, value in choices.items()}
    answers["tension"] = ScoreAnswer(score=0, confidence=1, legend={0: "calm"},
                                   probabilities={0: 1}).model_dump(mode="json")
    answers["hostility"] = NoulAnswer(noul=0).model_dump(mode="json")
    answers["reassurance"] = NoulAnswer(noul=reassurance).model_dump(mode="json")
    return {"model": "test-model", "answers": answers,
            "usage": {"input_tokens": 20, "output_tokens": 10}}


def test_cli_log_captures_real_service_contracts_and_a_complete_win(tmp_path, monkeypatch, capsys):
    path = tmp_path / "nested" / "game.jsonl"
    responses = iter([
        jev_response(action="inspect", action_object="ledger", recipient="none", intent="none"),
        jev_response(intent="persuade", rescue_plan="yes", reassurance=1),
        jev_response(intent="request", object="key", handover="yes"),
    ])
    sent_jev = []

    def handle_jev(request):
        sent_jev.append(json.loads(request.content))
        return httpx2.Response(200, json=next(responses))

    decider = JevDecider.__new__(JevDecider)
    decider.model = "test-model"
    decider.questions = questions()
    decider.client = TypeSafeClient(api_key="test-secret", model=decider.model,
                                   retry=RetryPolicy(max_retries=0), transport=httpx2.MockTransport(handle_jev))
    sent_bonsai = []

    def handle_bonsai(request, timeout):
        if request.data is None:
            return io.BytesIO(b'{"data": []}')
        body = json.loads(request.data)
        sent_bonsai.append(body)
        payload = json.loads(body["messages"][1]["content"])
        directive = DIRECTIVES[payload["directive"]["events"][-1]]
        content = json.dumps([{"speaker": line.speaker, "text": line.text} for line in directive.fallback])
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())

    lines = iter(["I read the ledger.", "Maren, I'll take a rope, use the east steps, and return the key.",
                  "Maren, please lend me the key."])
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-secret")
    monkeypatch.setattr("convgame.jev.JevDecider", lambda model: decider)
    monkeypatch.setattr("urllib.request.urlopen", handle_bonsai)
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    monkeypatch.setattr("sys.argv", ["convgame", "--log-file", str(path), "--jev-model", "test-model"])

    assert main() == 0
    output = capsys.readouterr()
    assert str(path) in output.err
    assert "you win" in output.out
    trace = entries(path)
    jev_calls = [entry for entry in trace if entry["event"] == "jev.request"]
    assert len(jev_calls) == len(sent_jev) == 3
    for entry, body in zip(jev_calls, sent_jev):
        assert entry["state"] == body["state"]
        assert entry["questions"] == body["questions"]
        assert entry["model"] == body["model"]
    bonsai_calls = [entry for entry in trace if entry["event"] == "bonsai.request" and entry["method"] == "POST"]
    assert [entry["body"] for entry in bonsai_calls] == sent_bonsai
    assert len([entry for entry in trace if entry["event"] == "jev.response"]) == 3
    assert len([entry for entry in trace if entry["event"] == "bonsai.accepted"]) == 3
    handover = next(entry for entry in trace if entry["event"] == "world.key_request")
    assert handover["event_selected"] == "won"
    assert all(handover["checks"].values())
    assert "readiness" in handover["reason"]
    assert [entry["attempt"] for entry in trace if entry["event"] == "turn.finished"] == [1, 2, 3]
    assert next(entry for entry in trace if entry["event"] == "game.finished")["world"]["key_given"]
    assert all(entry["reason"] and entry["timestamp"] for entry in trace)
    assert len({entry["session"] for entry in trace}) == 1
    assert "test-secret" not in path.read_text()


def test_failed_jev_attempt_and_invalid_bonsai_have_distinct_logged_outcomes(tmp_path, monkeypatch):
    path = tmp_path / "failures.jsonl"

    class Decider:
        failed = False

        def decide(self, world, line):
            if not self.failed:
                self.failed = True
                raise TimeoutError("provider body with test-secret")
            return replace(NEUTRAL, action=Pick("inspect", 1), action_object=Pick("ledger", 1),
                           recipient=Pick("none", 1))

    def invalid_bonsai(request, timeout):
        content = json.dumps([{"speaker": "Maren", "text": "Hello."}])
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())

    lines = iter(["I read the ledger.", "I read the ledger.", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    monkeypatch.setattr("urllib.request.urlopen", invalid_bonsai)
    with file_log(path):
        play(Decider(), BonsaiNarrator("http://localhost:8080"))

    trace = entries(path)
    cancelled = next(entry for entry in trace if entry["event"] == "turn.cancelled")
    finished = next(entry for entry in trace if entry["event"] == "turn.finished")
    assert cancelled["attempt"] == 1 and cancelled["turn"] == 1
    assert cancelled["unchanged"]["turn"] == 0
    assert finished["attempt"] == 2 and finished["turn"] == 1
    assert finished["after"]["ledger_read"]
    rejected = next(entry for entry in trace if entry["event"] == "bonsai.rejected")
    assert "unauthorized speaker" in rejected["reason"]
    assert any(entry["event"] == "narration.fallback" for entry in trace)
    assert "provider body" not in path.read_text()


@pytest.mark.parametrize("answers,expected_reason", [
    (replace(NEUTRAL, action=Pick("inspect", 0.2)), "physical action"),
    (replace(NEUTRAL, off_world=Pick("yes", 1)), "off-world"),
    (replace(NEUTRAL, recipient=Pick("unknown", 1)), "speech recipient"),
])
def test_blocked_turn_logs_its_specific_cause_and_skips_bonsai(tmp_path, monkeypatch, answers, expected_reason):
    path = tmp_path / "blocked.jsonl"

    def unexpected_request(*args, **kwargs):
        pytest.fail("Scripted guidance must not call Bonsai")

    monkeypatch.setattr("urllib.request.urlopen", unexpected_request)
    with file_log(path):
        world, directive = advance(World(), answers)
        assert BonsaiNarrator("http://localhost:8080").narrate(world, "Unclear input", directive) == directive.fallback
    trace = entries(path)
    validation = next(entry for entry in trace if entry["event"] == "world.validation")
    assert not validation["accepted"]
    assert expected_reason in validation["reason"].lower()
    assert any(entry["event"] == "bonsai.skipped" for entry in trace)
    assert not any(entry["event"] == "world.emotions" for entry in trace)


def test_refusal_log_exposes_readiness_reached_too_late(tmp_path):
    path = tmp_path / "refusal.jsonl"
    with file_log(path):
        world, directive = advance(World(ledger_read=True, trust=1),
            replace(NEUTRAL, intent=Pick("request", 1), object=Pick("key", 1),
                    rescue_plan=Pick("yes", 1), handover=Pick("yes", 1)))
    assert world.ready and directive.event == "refuse"
    refusal = next(entry for entry in entries(path) if entry["event"] == "world.key_request")
    assert refusal["failed_checks"] == ["ready_before_turn"]
    assert not refusal["requirements"]["before"]["plan_agreed"]
    assert refusal["requirements"]["after"]["plan_agreed"]


def test_logs_append_sessions_flush_escape_input_and_release_handlers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr("sys.argv", ["convgame"])
    path = tmp_path / "logs" / "convgame.jsonl"
    assert main() == 1
    first_session = entries(path)[0]["session"]
    assert main() == 1
    starts = [entry for entry in entries(path) if entry["event"] == "session.started"]
    assert len(starts) == 2
    assert starts[-1]["session"] != first_session
    size = path.stat().st_size
    record("outside.session", "Closed file handlers must not receive later records.")
    assert path.stat().st_size == size

    escaped = tmp_path / "unicode.jsonl"
    with file_log(escaped):
        record("input", "Unicode and line breaks remain valid JSON Lines.", player_line="Maren, sí.\nAnother line.")
        assert len(entries(escaped)) == 1  # Each record is flushed immediately.
    assert entries(escaped)[0]["player_line"] == "Maren, sí.\nAnother line."


def test_check_logs_connectivity_without_a_jev_request(tmp_path, monkeypatch):
    path = tmp_path / "check.jsonl"
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-secret")
    monkeypatch.setattr("sys.argv", ["convgame", "--check", "--log-file", str(path)])
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: io.BytesIO(b'{"data": []}'))
    assert main() == 0
    trace = entries(path)
    assert any(entry["event"] == "configuration.checked" for entry in trace)
    assert not any(entry["event"] == "jev.request" for entry in trace)
    assert "test-secret" not in path.read_text()


def test_log_open_failure_stops_before_services(tmp_path, monkeypatch, capsys):
    parent_file = tmp_path / "not-a-directory"
    parent_file.write_text("occupied")
    monkeypatch.setattr("sys.argv", ["convgame", "--log-file", str(parent_file / "log.jsonl")])
    monkeypatch.setattr("convgame.cli.run", lambda args: pytest.fail("Do not run without the requested log"))
    assert main() == 1
    assert "Cannot write execution log" in capsys.readouterr().err
