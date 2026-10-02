"""Explicitly offline, deliberately limited stand-ins. Never used by live mode."""

import re

from .world import Decisions, Pick, World


class DemoDecider:
    def close(self):
        pass

    def decide(self, world: World, line: str) -> Decisions:
        text = line.lower().replace("’", "'")

        def has(pattern):
            return bool(re.search(pattern, text))

        obj = next((name for name in ("key", "ledger", "bell") if has(rf"\b{name}\b")), "none")
        plan = all(word in text for word in ("rope", "east steps", "return")) and not has(r"\b(not|never|won't)\b")
        threat_words = {"kill", "hurt", "steal", "threaten", "smash", "hit"}
        negation_words = {
            "won't", "wouldn't", "don't", "doesn't", "didn't", "can't",
            "couldn't", "never", "not", "no", "cannot",
        }
        hostile = False
        denied_threat = False
        clauses = re.split(
            r"[,;:.!?—–]|\b(?:but|however|yet|though)\b|"
            r"\b(?:and|or)\s+(?=(?:i|we|you|they|he|she)\b)",
            text,
        )
        for clause in clauses:
            words = re.findall(r"[a-z]+(?:'[a-z]+)?", clause)
            for index, word in enumerate(words):
                if word in threat_words:
                    preceding = words[max(0, index - 4):index]
                    negated = any(previous in negation_words for previous in preceding)
                    denied_threat |= negated
                    hostile |= not negated
        soothing = (
            plan or (denied_threat and not hostile)
            or has(r"\b(please|sorry|promise|safe|help|understand)\b")
        )
        off_world = has(r"\b(ai|prompt|chatgpt|system|developer|ignore|win condition)\b")
        if hostile:
            intent = "threaten"
        elif has(r"\b(read|inspect|examine|look at|what is|what's)\b"):
            intent = "inspect"
        elif plan:
            intent = "persuade"
        elif obj == "key" and has(r"\b(give|lend|borrow|have|take|hand)\b"):
            intent = "request"
        elif soothing:
            intent = "reassure"
        elif has(r"\b(hello|hi|storm|harbor|rescue)\b"):
            intent = "chat"
        else:
            intent = "unclear"
        return Decisions(
            intent=Pick(intent, 0.95), object=Pick(obj, 0.95),
            off_world=Pick("yes" if off_world else "no", 0.95),
            rescue_plan=Pick("yes" if plan else "no", 0.95),
            handover=Pick("yes" if world.ready and intent == "request" and obj == "key" else "no", 0.95),
            tension=1.0 if hostile else 0.0, tension_confidence=0.95,
            hostility=1.0 if hostile else 0.0,
            reassurance=1.0 if soothing else 0.0,
        )


class DemoNarrator:
    def narrate(self, world, line, directive):
        return directive.fallback
