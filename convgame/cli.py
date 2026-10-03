"""Terminal UI and orchestration."""

import argparse
from contextlib import ExitStack
from dataclasses import asdict
import json
import os
import sys
import time

from .bonsai import BonsaiNarrator
from .trace import file_log, log_context, record
from .world import World, advance


INTRO = """
THE LAST CROSSING

Narrator: A storm rattles the harbor office. Maren stands behind a desk with a tide
ledger and a brass alarm bell; the rescue skiff's key hangs from his belt.
A traveler is stranded beyond the harbor wall. You have twelve turns
to persuade Maren to lend you the key before the tide closes the crossing.

Describe actions: I read the ledger.
Speak explicitly: Maren, can I borrow the key? / I say to Maren, "I'll bring it back."
The Narrator describes outcomes; characters speak when addressed or reacting.
/look  /status  /help  /quit — commands don't use a turn.
"""
OPENING = "The water's ugly tonight, and I'm not losing another boat. Read the tide ledger if you mean to help."


def status(world: World) -> str:
    return (f"Turn {world.turn}/{world.max_turns} | Trust {world.trust:.0%} | "
            f"Suspicion {world.suspicion:.0%} | Composure {world.composure:.0%}\n"
            f"Ledger read: {'yes' if world.ledger_read else 'no'} | "
            f"Safe plan agreed: {'yes' if world.plan_agreed else 'no'} | "
            f"Key: {'in your hand' if world.key_given else 'with Maren'} | "
            f"Bell rung: {'yes' if world.bell_rung else 'no'}")


def play(decider, narrator, debug: bool = False, floor: float = 0.6) -> int:
    world = World(history=[{"role": "assistant", "content": f"Maren: {OPENING}"}])
    attempt = 0
    record("game.started", "Begin a new encounter with the opening dialogue.", world=world.snapshot())
    print(INTRO)
    print(f"Maren: {OPENING}")
    while world.ending == "playing":
        try:
            line = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            record("game.finished", "The player left through EOF or Ctrl+C.", world=world.snapshot())
            print("\nNarrator: You leave the harbor office.")
            return 0
        if not line:
            continue
        command = line.lower()
        if command == "/quit":
            record("game.finished", "The player chose /quit.", world=world.snapshot())
            print("Narrator: You leave the harbor office.")
            return 0
        if command == "/status":
            record("input.command", "Show authoritative state without using a turn.", command=command)
            print(status(world))
            continue
        if command == "/look":
            record("input.command", "Describe the scene without using a turn.", command=command)
            print("Narrator: Maren, the tide ledger, the alarm bell, and the brass rescue key. Rain lashes the office window.")
            continue
        if command == "/help":
            record("input.command", "Show instructions without using a turn.", command=command)
            print("Describe actions such as 'I read the ledger'. To speak, address Maren, describe speaking\n"
                  "to him, or quote your spoken words. Private thoughts are not promises he can hear.\n"
                  "Read the ledger, tell Maren your safe rescue plan, earn his trust, then ask him for the key.\n"
                  "Use /status for progress, /look for objects, or /quit to leave.")
            continue
        if command.startswith("/"):
            record("input.rejected", "Unknown commands do not use a turn.", player_line=line)
            print("Unknown command. Use /help.")
            continue
        if len(line) > 2000:
            record("input.rejected", "Input over 2,000 characters does not use a turn.", characters=len(line))
            print("Keep your line under 2,000 characters. No turn used.")
            continue
        attempt += 1
        with log_context(attempt=attempt, turn=world.turn + 1):
            record("turn.started", "Evaluate the player line; a Jev failure will leave this turn unused.",
                   player_line=line, before=world.snapshot())
            started = time.perf_counter()
            print("Resolving your turn...", flush=True)
            try:
                answers = decider.decide(world, line)
            except Exception as error:
                record("turn.cancelled", "Jev could not provide a valid interpretation; preserve the world and turn counter.",
                       error_type=type(error).__name__, unchanged=world.snapshot())
                # Avoid displaying provider error bodies, which may contain input/secrets.
                print(f"Jev could not evaluate that turn ({type(error).__name__}). "
                      "No turn used; check your API key/network and try again.", file=sys.stderr)
                continue
            decided = time.perf_counter()
            world, directive = advance(world, answers, floor)
            try:
                reply = narrator.narrate(world, line, directive)
            except Exception as error:
                record("narration.fallback", "Bonsai failed or its response was rejected; use the scripted beats and retain the already resolved state.",
                       error_type=type(error).__name__, events=directive.events)
                print(f"Bonsai narration unavailable ({type(error).__name__}); using the scripted scene response for this turn.",
                      file=sys.stderr)
                reply = directive.fallback
            rendered = "\n".join(f"{block.speaker}: {block.text}" for block in reply)
            remembered_line = line if directive.player_spoke else "[No spoken words; see narrated outcomes.]"
            world.history.extend([{"role": "user", "content": remembered_line},
                                  {"role": "assistant", "content": rendered}])
            world.history = world.history[-6:]
            record("turn.finished", "Remember accepted player speech and narrated outcomes, keeping six recent messages; unspoken input uses a placeholder.",
                   player_speech_remembered=directive.player_spoke, response=rendered, after=world.snapshot(),
                   jev_seconds=round(decided - started, 4),
                   resolution_and_narration_seconds=round(time.perf_counter() - decided, 4))
            print(f"\n{rendered}")
            if debug:
                print(json.dumps({"answers": asdict(answers), "events": directive.events,
                                  "jev_seconds": round(decided - started, 2),
                                  "bonsai_seconds": round(time.perf_counter() - decided, 2)}, indent=2))
                print(status(world))
    record("game.finished", "The authoritative world reached an encounter ending.", world=world.snapshot())
    print({"won": "\nNarrator: You received the brass key. The rescue can begin — you win!",
           "lost": "\nNarrator: Maren ends the encounter. You leave without the key.",
           "timeout": "\nNarrator: The tide closes the crossing. You ran out of time."}[world.ending])
    return 0


def confidence(value: str) -> float:
    result = float(value)
    if not 0 <= result <= 1:
        raise argparse.ArgumentTypeError("confidence must be between 0 and 1")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="The Last Crossing: Jev interprets, the world resolves, local Bonsai narrates.")
    parser.add_argument("--debug", action="store_true", help="Show typed decisions, timings, and world state")
    parser.add_argument("--check", action="store_true", help="Check configuration and Bonsai connectivity, then exit")
    parser.add_argument("--bonsai-url", default=os.environ.get("BONSAI_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--bonsai-model", default=os.environ.get("BONSAI_CHAT_MODEL"))
    parser.add_argument("--jev-model", default=os.environ.get("TYPESAFE_DEFAULT_MODEL", "jev-latest"))
    parser.add_argument("--confidence", type=confidence, default=0.6, help="Action confidence floor (default: 0.6)")
    parser.add_argument("--log-file", default="logs/convgame.jsonl",
                        help="Append service calls and decision reasons to this JSON Lines file (default: logs/convgame.jsonl)")
    args = parser.parse_args()
    # Open the log before checking services so startup failures are recorded too.
    with ExitStack() as stack:
        try:
            path = stack.enter_context(file_log(args.log_file))
        except OSError as error:
            print(f"Cannot write execution log at {args.log_file} ({type(error).__name__}).", file=sys.stderr)
            return 1
        print(f"Execution log: {path.resolve()}", file=sys.stderr)
        record("session.started", "Check configuration before running the game or connectivity check.",
               mode="check" if args.check else "play", jev_model=args.jev_model,
               bonsai_model=args.bonsai_model, confidence_floor=args.confidence)
        try:
            result = run(args)
        except BaseException as error:
            record("session.failed", "An unhandled error interrupted the command.", error_type=type(error).__name__)
            raise
        record("session.finished", "The command completed.", exit_code=result)
        return result


def run(args: argparse.Namespace) -> int:
    configured = bool(os.environ.get("TYPESAFE_API_KEY", "").strip())
    narrator = BonsaiNarrator(args.bonsai_url, args.bonsai_model)
    if args.check:
        print(f"TypeSafe API key: {'configured (not authenticated)' if configured else 'missing'}")
        print(f"Jev model: {args.jev_model}")
    if not configured:
        record("configuration.rejected", "TYPESAFE_API_KEY is missing; live play requires it.")
        print("Set TYPESAFE_API_KEY in your environment to play.", file=sys.stderr)
        if not args.check:
            return 1
    try:
        narrator.check()
    except Exception as error:
        record("configuration.rejected", "The Bonsai connectivity check failed; stop before starting an encounter.",
               error_type=type(error).__name__)
        print(f"Bonsai is unavailable at {args.bonsai_url} ({type(error).__name__}).\n"
              "Start /home/xavi/Projects/Bonsai/scripts/start_llama_server.sh in another terminal.", file=sys.stderr)
        return 1
    if args.check:
        record("configuration.checked", "The Bonsai endpoint is reachable; Jev key presence was checked without a paid request.",
               jev_key_present=configured)
        print(f"Bonsai: reachable at {args.bonsai_url}")
        return 0 if configured else 1
    try:
        from .jev import JevDecider
        decider = JevDecider(args.jev_model)
    except Exception as error:
        record("configuration.rejected", "Jev client initialization failed; stop before starting an encounter.",
               error_type=type(error).__name__)
        print(f"Cannot initialize Jev ({type(error).__name__}). Run uv sync and check your configuration.", file=sys.stderr)
        return 1
    try:
        return play(decider, narrator, args.debug, args.confidence)
    except KeyboardInterrupt:
        record("game.finished", "Ctrl+C interrupted turn processing; leave the encounter.")
        print("\nNarrator: You leave the harbor office.")
        return 0
    finally:
        decider.close()
