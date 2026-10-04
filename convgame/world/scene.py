"""Authored scene, perception anchors, and boundaries for descriptive enrichment."""

from dataclasses import asdict, dataclass
import json


OPENING = "The water's ugly tonight, and I'm not losing another boat. Read the tide ledger if you mean to help."
LOOK = (
    "Maren, the tide ledger, the alarm bell, and the brass rescue key. "
    "Rain lashes the office window; through it you can see a stretch of harbor and its sky."
)
INTRO = """
THE LAST CROSSING

Narrator: A storm rattles the harbor office. Maren stands behind a desk with a tide
ledger and a brass alarm bell; the rescue skiff's key hangs from his belt.
A traveler is stranded beyond the harbor wall. You have twelve turns
to persuade Maren to lend you the key before the tide closes the crossing.
Through the rain-lashed window you can see a stretch of harbor and its sky.

Describe actions: I read the ledger. Ask about scenery: Are there clouds in the sky?
Speak explicitly: Maren, can I borrow the key? / I say to Maren, "I'll bring it back."
The Narrator describes outcomes; characters speak when addressed or reacting.
/look  /status  /help  /quit — commands don't use a turn.
"""


@dataclass(frozen=True)
class AccessAnchor:
    id: str
    subject: str
    mode: str
    scope: str
    categories: tuple[str, ...]
    statement: str
    requires_ledger_read: bool = False
    measurement_unit: str | None = None


@dataclass(frozen=True)
class CanonFact:
    id: str
    subject: str
    facet: str
    value_type: str
    value: str | bool | float
    statement: str
    scope: str
    lifetime: str = "encounter"


@dataclass(frozen=True)
class Scene:
    location: str
    constraints: tuple[tuple[str, str], ...]
    referents: tuple[str, ...]
    scopes: tuple[str, ...]
    anchors: tuple[AccessAnchor, ...]
    canon: tuple[CanonFact, ...]
    fallback: str
    look: str = LOOK
    weather: str = "storm"

    def snapshot(self) -> dict:
        return json.loads(json.dumps(asdict(self))) | {
            "constraints": dict(self.constraints),
            "policy": {
                "allowed_categories": ["appearance", "texture", "sound", "smell", "temperature", "presence"],
                "protected_subjects": {"key": ["appearance", "texture"], "ledger": ["appearance", "texture"],
                                       "bell": ["appearance", "texture"]},
                "reserved": ["inventory", "ownership", "permissions", "route safety", "objectives",
                             "new actors", "resources", "causal events", "future events"],
                "patch_budget": {"referents": 1, "facts": 2},
                "unknown_is_not_absent": True,
            },
        }


DEFAULT_SCENE = Scene(
    location="A stormbound harbor office, a low-fantasy coastal town, at night.",
    constraints=(
        ("scene.storm_active", "A storm is active; generated detail cannot clear or calm it."),
        ("scene.night", "It is tonight; do not invent daylight or unsupported visual precision."),
        ("scene.characters", "Only the player and Maren are present. Do not introduce other actors."),
        ("scene.rescue", "A traveler is stranded beyond the harbor wall; the tide closes the crossing after twelve turns."),
        ("scene.key", "The brass key is guarded by Maren and opens the rescue skiff locker; no spare keys or boats."),
        ("scene.ledger", "The ledger advises rope, sheltered east steps, and returning the key. No new advice or routes."),
        ("scene.mechanics", "Python controls actions, possessions, access, commitments, time, emotions, and endings."),
        ("scene.resources", "No generated usable resources, helpers, secret exits, safety shortcuts, or future events."),
    ),
    referents=("office", "harbor", "office.window", "office.desk", "key", "ledger", "bell"),
    scopes=("office", "harbor", "office.window_view"),
    anchors=(
        AccessAnchor("scene.office_view", "office", "sight", "office", ("appearance", "texture", "presence"),
                     "The desk, ledger, bell, guarded key, and rain-lashed window are visible in the office."),
        AccessAnchor("scene.window_harbor_view", "harbor", "sight", "office.window_view", ("appearance", "presence"),
                     "The existing window permits a partial view of the harbor water and sky, sufficient for broad shapes."),
        AccessAnchor("scene.rain_sound", "office", "hearing", "office", ("sound",),
                     "The ongoing storm and rain against the office window are audible."),
        AccessAnchor("scene.ledger_read", "ledger", "reading", "office", ("appearance",),
                     "The player has physically read the ledger's authored advice.", requires_ledger_read=True),
    ),
    canon=(
        CanonFact("canon.key_position", "key", "appearance.position", "descriptor", "maren_belt",
                  "The rescue key hangs from Maren's belt.", "office"),
        CanonFact("canon.ledger_open", "ledger", "appearance.open", "boolean", True,
                  "The tide ledger lies open on the desk.", "office"),
        CanonFact("canon.bell_position", "bell", "appearance.position", "descriptor", "desk",
                  "The alarm bell stands on the desk.", "office"),
        CanonFact("canon.key_material", "key", "appearance.material", "descriptor", "brass",
                  "The rescue key is brass.", "office"),
        CanonFact("canon.bell_material", "bell", "appearance.material", "descriptor", "brass",
                  "The alarm bell is brass.", "office"),
        CanonFact("canon.window_rain", "office.window", "appearance.rain", "descriptor", "rain_lashed",
                  "Rain lashes the office window.", "office", "current_weather_episode"),
        CanonFact("canon.storm", "harbor", "appearance.weather", "descriptor", "storm",
                  "The storm is already here.", "harbor", "current_weather_episode"),
    ),
    fallback="You can see the office and a stretch of harbor through the window, but cannot establish that detail from here.",
)

# Shared by Jev and Bonsai; descriptive facts and access come from World.scene.
SCENE = {
    "location": DEFAULT_SCENE.location,
    "characters": "Only the player and Maren, a cautious, gruff harbor-master, are present.",
    "objective": "Borrow the brass key to the rescue skiff locker to rescue a stranded traveler.",
    "objects": {
        "key": "Brass key held by Maren, opens rescue skiff locker.",
        "ledger": "Open tide ledger on desk: east steps are sheltered; take a rope and return key.",
        "bell": "Brass alarm bell on desk; signals danger on the water.",
    },
    "rules": (
        "Read the ledger, explicitly agree to take a rope, use the east steps and return the key, then ask Maren for it. "
        "Python controls all state changes. Physical actions and explicit speech are separate. "
        "Only actual reading marks the ledger read; a descriptive question about it does not. "
        "Only a spoken promise agrees the plan; only a spoken request can obtain the key. "
        "Taking the guarded key is blocked. Maren cannot hear private thoughts or bare observation questions. "
        "Direct sensory questions and scenery inspection use observation without requiring a registered object."
    ),
}


def scene_context(scene: Scene) -> dict:
    return SCENE | {"location": scene.location, "perception_and_policy": scene.snapshot()}
