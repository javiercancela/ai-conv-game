"""Send one batched System One request per player turn."""

from typesafe_sdk import Questions, RetryPolicy, TypeSafeClient

from ..world import Decisions, World
from .decoder import decode
from .questions import questions
from .scene_constants import SCENE


class JevDecider:
    def __init__(self, model: str | None = None) -> None:
        self.client: TypeSafeClient = TypeSafeClient(
            model=model,
            retry=RetryPolicy(max_retries=0),
            timeout=30,
        )
        self.questions: Questions = questions()

    def close(self) -> None:
        self.client.close()

    def decide(self, world: World, line: str) -> Decisions:
        result = self.client.system_one(
            state={"scene": SCENE, "world": world.snapshot(), "player_line": line},
            questions=self.questions,
        )
        return decode(result)
