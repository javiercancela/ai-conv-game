"""Opt-in live observation evaluation: python -m convgame.evaluate_observations.

The report separates deterministic checks from semantic judgments requiring a
human reviewer. A model's review pass is never counted as semantic correctness.
"""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

from .bonsai import BonsaiNarrator
from .observations import prepare_observation
from .trace import file_log, log_context
from .world import Action, Recipient, World, advance
from .world.validation import blocked_event
from .world.facts import active_facts


# Different wording from the prompts and deterministic fixtures, including a
# continuity sequence long enough to evict the initial answer from history.
SCENARIOS = (
    ("clouds", "Is the harbor sky covered, or can I make out any stars?", Action.OBSERVE, Recipient.NONE),
    ("sound", "What sort of noise does the rain make against the glass?", Action.OBSERVE, Recipient.NONE),
    ("ledger", "What shade is the ledger's cover?", Action.OBSERVE, Recipient.NONE),
    ("thought_1", "I silently wonder how the rescue will go.", Action.NONE, Recipient.NONE),
    ("thought_2", "I privately consider whether Maren will trust me.", Action.NONE, Recipient.NONE),
    ("thought_3", "I imagine asking about the clouds but keep quiet.", Action.NONE, Recipient.NONE),
    ("thought_4", "I think about the tide without speaking.", Action.NONE, Recipient.NONE),
    ("clouds_again", "Has that cover over the harbor sky broken up yet?", Action.OBSERVE, Recipient.NONE),
    ("temperature", "Can you tell me how warm the harbor water is in degrees?", Action.OBSERVE, Recipient.NONE),
    ("boats", "Are other vessels visible in this part of the harbor?", Action.OBSERVE, Recipient.NONE),
    ("presupposition", "What is inside the spare rescue boat?", Action.OBSERVE, Recipient.NONE),
)
CHANNEL_SCENARIOS = (
    ("addressed", "Maren, can you make out clouds overhead?", Action.NONE, Recipient.MAREN),
    ("private_question", "I silently wonder whether there are clouds overhead.", Action.NONE, Recipient.NONE),
    ("bare_key", "Could I borrow the key?", Action.NONE, Recipient.NONE),
    ("typo", "Are there clounds on the sky?", Action.OBSERVE, Recipient.NONE),
)
SEMANTIC_FIELDS = ("sensible_answer", "contradiction", "unsupported_knowledge", "unintended_story_opportunity")


def _summary(rows: list[dict]) -> dict:
    reviewed = [row for row in rows if all(row.get(key) is not None for key in SEMANTIC_FIELDS)]
    return {
        "evaluated_lines": len(rows),
        "classification_correct": sum(row.get("classification_correct", False) for row in rows),
        "service_errors": sum("service_error" in row for row in rows),
        "fallbacks": sum(row.get("fallback", False) for row in rows),
        "mean_seconds": round(sum(row["seconds"] for row in rows) / len(rows), 4) if rows else None,
        "human_reviewed_lines": len(reviewed),
        "sensible_answer_rate": sum(row["sensible_answer"] for row in reviewed) / len(reviewed) if reviewed else None,
        "contradictions": sum(row["contradiction"] for row in reviewed) if reviewed else None,
        "unsupported_knowledge": sum(row["unsupported_knowledge"] for row in reviewed) if reviewed else None,
        "unintended_story_opportunities": sum(row["unintended_story_opportunity"] for row in reviewed) if reviewed else None,
    }


def evaluate(decider, narrator, floor: float) -> list[dict]:
    rows = []
    world = World()
    initial_cloud_ids = ()
    for index, (name, line, action, recipient) in enumerate(SCENARIOS + CHANNEL_SCENARIOS):
        if index >= len(SCENARIOS):
            world = World()
        started = time.perf_counter()
        row = {"scenario": name, "player_line": line, **{field: None for field in SEMANTIC_FIELDS},
               "review_notes": "Review the answer in context; a semantic model pass is not evidence of correctness."}
        try:
            with log_context(evaluation=name, turn=world.turn + 1):
                answers = decider.decide(world, line)
                decided = time.perf_counter()
                row["decisions"] = asdict(answers)
                row["classification_correct"] = answers.action.value == action and answers.recipient.value == recipient
                prepared = None
                if answers.action.value == Action.OBSERVE and blocked_event(answers, floor) is None:
                    prepared = prepare_observation(world, line, narrator)
                    row["resolution"] = prepared.resolution.payload()
                    row["fallback"] = prepared.fallback
                world, directive = advance(world, answers, floor, observation=prepared)
                committed = time.perf_counter()
                try:
                    reply = narrator.narrate(world, line, directive)
                except Exception as error:
                    reply = directive.fallback
                    row["rendering_error"] = type(error).__name__
                    row["fallback"] = True
                row["response"] = "\n".join(f"{block.speaker}: {block.text}" for block in reply)
                remembered = line if directive.player_spoke else "[No spoken words; see narrated outcomes.]"
                world.history.extend([{"role": "user", "content": remembered},
                                      {"role": "assistant", "content": row["response"]}])
                world.history = world.history[-6:]
                row["after"] = world.snapshot()
                row["mechanics_unchanged"] = not (world.ledger_read or world.plan_agreed or world.key_given)
                row["jev_seconds"] = round(decided - started, 4)
                row["resolution_seconds"] = round(committed - decided, 4)
                if name == "clouds" and prepared:
                    facts = active_facts(world)
                    initial_cloud_ids = tuple(fact_id for fact_id in world.facts.commits[prepared.proposal_id].fact_ids
                                              if facts[fact_id].detail.facet == "appearance.cloud_cover")
                if name == "clouds_again" and prepared:
                    row["continuity_same_fact_ids"] = bool(initial_cloud_ids) and (
                        set(initial_cloud_ids) <= set(world.facts.commits[prepared.proposal_id].fact_ids))
        except Exception as error:
            row["service_error"] = type(error).__name__
        row["seconds"] = round(time.perf_counter() - started, 4)
        rows.append(row)
        print(f"{name}: {row.get('response', row.get('service_error'))} ({row['seconds']:.2f}s)", flush=True)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bonsai-url", default=os.environ.get("BONSAI_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--bonsai-model", default=os.environ.get("BONSAI_CHAT_MODEL"))
    parser.add_argument("--jev-model", default=os.environ.get("TYPESAFE_DEFAULT_MODEL", "jev-latest"))
    parser.add_argument("--confidence", type=float, default=0.6)
    parser.add_argument("--output", type=Path, default=Path("reports/observations-live.json"))
    parser.add_argument("--log-file", default="logs/observations-live.log")
    args = parser.parse_args()
    if not 0 <= args.confidence <= 1:
        parser.error("confidence must be between zero and one")
    report = {"evaluated_at": datetime.now(timezone.utc).isoformat(), "scenarios": [],
              "semantic_review": "Human review fields are null until the transcript is assessed."}
    narrator = BonsaiNarrator(args.bonsai_url, args.bonsai_model)
    with file_log(args.log_file):
        try:
            if not os.environ.get("TYPESAFE_API_KEY", "").strip():
                raise ValueError("Missing API key")
            # Do not incur Jev requests if local observation resolution is unavailable.
            narrator.check()
            from .jev import JevDecider
            decider = JevDecider(args.jev_model)
        except Exception as error:
            report["blocked_by"] = type(error).__name__
            print(f"Live evaluation unavailable ({type(error).__name__}); no Jev requests sent.")
        else:
            try:
                report["scenarios"] = evaluate(decider, narrator, args.confidence)
            finally:
                decider.close()
    report["summary"] = _summary(report["scenarios"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Evaluation report: {args.output}")
    return int("blocked_by" in report or any("service_error" in row for row in report["scenarios"]))


if __name__ == "__main__":
    raise SystemExit(main())
