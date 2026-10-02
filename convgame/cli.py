"""Terminal UI and orchestration."""

import argparse
from dataclasses import asdict
import json
import os
import sys
import time

from .bonsai import BonsaiNarrator
from .demo import DemoDecider, DemoNarrator
from .world import World, advance


INTRO = """
THE LAST CROSSING

A storm rattles the harbor office. Maren stands behind a desk with a tide
ledger and a brass alarm bell; the rescue skiff's key hangs from his belt.
A traveler is stranded beyond the harbor wall. You have twelve exchanges
to persuade Maren to lend you the key before the tide closes the crossing.

Speak naturally, or describe an action such as 'I read the ledger'.
/look  /status  /help  /quit — commands don't use a turn.
"""
OPENING = "The water's ugly tonight, and I'm not losing another boat. Read the tide ledger if you mean to help."


def status(world: World) -> str:
    return (f"Turn {world.turn}/{world.max_turns} | Trust {world.trust:.0%} | "
            f"Suspicion {world.suspicion:.0%} | Composure {world.composure:.0%}\n"
            f"Ledger read: {'yes' if world.ledger_read else 'no'} | "
            f"Safe plan agreed: {'yes' if world.plan_agreed else 'no'} | "
            f"Key: {'in your hand' if world.key_given else 'with Maren'}")


def play(decider, narrator, debug: bool = False, floor: float = 0.6) -> int:
    world = World(history=[{"role": "assistant", "content": OPENING}])
    print(INTRO)
    print(f"Maren: {OPENING}")
    while world.ending == "playing":
        try:
            line = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nYou leave the harbor office.")
            return 0
        if not line:
            continue
        command = line.lower()
        if command == "/quit":
            print("You leave the harbor office.")
            return 0
        if command == "/status":
            print(status(world))
            continue
        if command == "/look":
            print("Maren, the tide ledger, the alarm bell, and the brass rescue key. Rain lashes the office window.")
            continue
        if command == "/help":
            print("Read the ledger, discuss a safe rescue plan, earn Maren's trust, then ask for the key.\n"
                  "Use /status for progress, /look for objects, or /quit to leave.")
            continue
        if command.startswith("/"):
            print("Unknown command. Use /help.")
            continue
        if len(line) > 2000:
            print("Keep your line under 2,000 characters. No turn used.")
            continue
        started = time.perf_counter()
        print("Maren considers your words...", flush=True)
        try:
            answers = decider.decide(world, line)
        except Exception as error:
            # Avoid displaying provider error bodies, which may contain input/secrets.
            print(f"Jev could not evaluate that turn ({type(error).__name__}). "
                  "No turn used; check your API key/network and try again.", file=sys.stderr)
            continue
        decided = time.perf_counter()
        world, directive = advance(world, answers, floor)
        try:
            reply = narrator.narrate(world, line, directive)
        except Exception as error:
            print(f"Bonsai dialogue unavailable ({type(error).__name__}); using scene dialogue for this turn.",
                  file=sys.stderr)
            reply = directive.fallback
        world.history.extend([{"role": "user", "content": line}, {"role": "assistant", "content": reply}])
        world.history = world.history[-6:]
        print(f"\nMaren: {reply}")
        if debug:
            print(json.dumps({"answers": asdict(answers), "event": directive.event,
                              "jev_seconds": round(decided - started, 2),
                              "bonsai_seconds": round(time.perf_counter() - decided, 2)}, indent=2))
            print(status(world))
    print({"won": "\nYou received the brass key. The rescue can begin — you win!",
           "lost": "\nMaren ends the conversation. You leave without the key.",
           "timeout": "\nThe tide closes the crossing. You ran out of time."}[world.ending])
    return 0


def confidence(value: str) -> float:
    result = float(value)
    if not 0 <= result <= 1:
        raise argparse.ArgumentTypeError("confidence must be between 0 and 1")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="The Last Crossing: Jev decides, local Bonsai speaks.")
    parser.add_argument("--demo", action="store_true", help="Offline rules and scripted dialogue; no models or API calls")
    parser.add_argument("--debug", action="store_true", help="Show typed decisions, timings, and world state")
    parser.add_argument("--check", action="store_true", help="Check configuration and Bonsai connectivity, then exit")
    parser.add_argument("--bonsai-url", default=os.environ.get("BONSAI_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--bonsai-model", default=os.environ.get("BONSAI_CHAT_MODEL"))
    parser.add_argument("--jev-model", default=os.environ.get("TYPESAFE_DEFAULT_MODEL", "jev-latest"))
    parser.add_argument("--confidence", type=confidence, default=0.6, help="Action confidence floor (default: 0.6)")
    args = parser.parse_args()
    if args.demo:
        print("OFFLINE DEMO — keyword decisions and scripted dialogue; Jev and Bonsai are not used.")
        return 0 if args.check else play(DemoDecider(), DemoNarrator(), args.debug, args.confidence)

    configured = bool(os.environ.get("TYPESAFE_API_KEY", "").strip())
    narrator = BonsaiNarrator(args.bonsai_url, args.bonsai_model)
    if args.check:
        print(f"TypeSafe API key: {'configured (not authenticated)' if configured else 'missing'}")
        print(f"Jev model: {args.jev_model}")
    if not configured:
        print("Set TYPESAFE_API_KEY in your environment for live play, or use --demo.", file=sys.stderr)
        if not args.check:
            return 1
    try:
        narrator.check()
    except Exception as error:
        print(f"Bonsai is unavailable at {args.bonsai_url} ({type(error).__name__}).\n"
              "Start /home/xavi/Projects/Bonsai/scripts/start_llama_server.sh in another terminal.", file=sys.stderr)
        return 1
    if args.check:
        print(f"Bonsai: reachable at {args.bonsai_url}")
        return 0 if configured else 1
    try:
        from .jev import JevDecider
        decider = JevDecider(args.jev_model)
    except Exception as error:
        print(f"Cannot initialize Jev ({type(error).__name__}). Run uv sync and check your configuration.", file=sys.stderr)
        return 1
    try:
        return play(decider, narrator, args.debug, args.confidence)
    except KeyboardInterrupt:
        print("\nYou leave the harbor office.")
        return 0
    finally:
        decider.close()

