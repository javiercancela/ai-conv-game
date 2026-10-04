"""Send one batched System One request per player turn."""

import time

from typesafe_sdk import Questions, RetryPolicy, TypeSafeClient

from ..trace import record
from ..world import Decisions, World
from .decoder import decode
from .questions import questions
from ..world.scene import scene_context


class JevDecider:
    def __init__(self, model: str | None = None) -> None:
        self.model = model
        self.client: TypeSafeClient = TypeSafeClient(
            model=model,
            retry=RetryPolicy(max_retries=0),
            timeout=30,
        )
        self.questions: Questions = questions()

    def close(self) -> None:
        self.client.close()

    def decide(self, world: World, line: str) -> Decisions:
        state = {"scene": scene_context(world.scene),
                 "world": world.snapshot(), "player_line": line}
        record("jev.request", "Interpret this player line in one batched System One call.",
               operation="system_one", model=getattr(self, "model", None),
               state=state, questions={name: question.model_dump(mode="json")
                                      for name, question in self.questions.items()})
        started = time.perf_counter()
        try:
            result = self.client.system_one(state=state, questions=self.questions)
        except Exception as error:
            record("jev.error", "The Jev call failed; no interpretation can be applied.",
                   error_type=type(error).__name__, seconds=round(time.perf_counter() - started, 4))
            raise
        record("jev.response", "Jev returned typed answers; validate them before changing the world.",
               response=result.model_dump(mode="json"), seconds=round(time.perf_counter() - started, 4))
        try:
            return decode(result)
        except Exception as error:
            record("jev.rejected", "Jev's answers are incomplete or invalid; leave the world unchanged.",
                   error_type=type(error).__name__)
            raise
