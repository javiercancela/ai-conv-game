"""World state and the snapshot shared with the decider and narrator."""

from dataclasses import dataclass, field
from typing import TypedDict

from .facts import FactStore
from .scene import DEFAULT_SCENE, Scene


class WorldSnapshot(TypedDict):
    turn: int
    max_turns: int
    trust: float
    suspicion: float
    composure: float
    ledger_read: bool
    plan_agreed: bool
    key_given: bool
    bell_rung: bool
    ending: str
    history: list[dict[str, str]]
    ready_to_lend_key: bool
    revision: int
    scene_revision: int
    weather_revision: int
    observations: dict


@dataclass
class World:
    turn: int = 0
    max_turns: int = 12
    trust: float = 0.35
    suspicion: float = 0.2
    composure: float = 0.8
    ledger_read: bool = False
    plan_agreed: bool = False
    key_given: bool = False
    bell_rung: bool = False
    ending: str = "playing"
    history: list[dict[str, str]] = field(default_factory=list)
    scene: Scene = DEFAULT_SCENE
    revision: int = 0
    scene_revision: int = 0
    weather_revision: int = 0
    facts: FactStore = field(default_factory=FactStore)

    @property
    def ready(self) -> bool:
        return (
            self.ledger_read
            and self.plan_agreed
            and self.trust >= 0.55
            and self.suspicion < 0.65
        )

    def snapshot(self) -> WorldSnapshot:
        return {
            "turn": self.turn,
            "max_turns": self.max_turns,
            "trust": self.trust,
            "suspicion": self.suspicion,
            "composure": self.composure,
            "ledger_read": self.ledger_read,
            "plan_agreed": self.plan_agreed,
            "key_given": self.key_given,
            "bell_rung": self.bell_rung,
            "ending": self.ending,
            "history": [entry.copy() for entry in self.history[-6:]],
            "ready_to_lend_key": self.ready,
            "revision": self.revision,
            "scene_revision": self.scene_revision,
            "weather_revision": self.weather_revision,
            "observations": self.facts.snapshot(),
        }
