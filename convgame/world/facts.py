"""Typed descriptive facts, strict contracts, and network-free patch validation.

The overlay is encounter state, independent of the short dialogue transcript.
Only the turn resolver commits a complete, validated observation to a draft World.
"""

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
import json
import math
import re
from typing import TYPE_CHECKING

from .scene import CanonFact

if TYPE_CHECKING:
    from .directives import Directive
    from .state import World


def _object(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _string(maximum: int = 160) -> dict:
    return {"type": "string", "minLength": 1, "maxLength": maximum}


def _array(items: dict, maximum: int) -> dict:
    return {"type": "array", "items": items, "maxItems": maximum, "uniqueItems": True}


def _nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


VALUE_SCHEMA = {"anyOf": [
    _object({"type": {"enum": ["descriptor"]}, "text": _string(120)}),
    _object({"type": {"enum": ["boolean"]}, "value": {"type": "boolean"}}),
    _object({"type": {"enum": ["number"]}, "amount": {"type": "number"}, "unit": _string(40)}),
]}
RESOLUTION_SCHEMA = _object({
    "status": {"enum": ["resolved", "estimated", "unobservable", "ambiguous", "protected"]},
    "query": _object({"subject": _string(), "facet": _string()}),
    "perception": _object({
        "mode": {"enum": ["sight", "hearing", "touch", "smell", "reading", "testimony", "none"]},
        "access_evidence": _array(_string(), 6), "scope": _string(),
    }),
    "reuse_fact_ids": _array(_string(), 8),
    "proposed_referents": _array(_object({
        "id": _string(), "kind": {"enum": ["scenery"]}, "parent": _string(),
    }), 1),
    "proposed_facts": _array(_object({
        "subject": _string(), "facet": _string(), "value": VALUE_SCHEMA,
        "statement": _string(300), "scope": _string(),
        "lifetime": {"enum": ["encounter", "current_weather_episode", "current_view"]},
        "constraint_ids": _array(_string(), 12),
    }), 2),
    "answer_fact_refs": _array(_string(), 8),
    "estimate": _nullable(_object({
        "statement": _string(300), "evidence_ids": _array(_string(), 8),
        "uncertainty": {"enum": ["possible", "likely"]},
    })),
    "reuse_estimate_id": _nullable(_string()),
    "limitation": _nullable({"enum": ["no_access", "requires_touch", "requires_measurement"]}),
    "clarification": _nullable(_object({"candidates": _array(_string(), 3)})),
})
REVIEW_SCHEMA = _object({"verdict": {"enum": ["pass", "reject"]}, "reason": _string(600)})


def check_schema(value, schema: dict, path: str = "response") -> None:
    """Enforce the same small schema at decode time, not just in the model prompt."""
    if "anyOf" in schema:
        for choice in schema["anyOf"]:
            try:
                check_schema(value, choice, path)
                return
            except ValueError:
                pass
        raise ValueError(f"Invalid {path}.")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"Invalid {path} enum.")
    kind = schema.get("type")
    if kind == "null" and value is not None:
        raise ValueError(f"Invalid {path}: expected null.")
    if kind == "object":
        if not isinstance(value, dict) or set(value) != set(schema["properties"]):
            raise ValueError(f"Invalid {path} fields.")
        for key, subschema in schema["properties"].items():
            check_schema(value[key], subschema, f"{path}.{key}")
    elif kind == "array":
        if not isinstance(value, list) or len(value) > schema["maxItems"]:
            raise ValueError(f"Invalid {path} collection.")
        if any(item in value[:index] for index, item in enumerate(value)):
            raise ValueError(f"Duplicate {path} entries.")
        for item in value:
            check_schema(item, schema["items"], path)
    elif kind == "string":
        if not isinstance(value, str) or not value.strip() or not schema["minLength"] <= len(value) <= schema["maxLength"]:
            raise ValueError(f"Invalid {path} string.")
        if any(ord(char) < 32 for char in value):
            raise ValueError(f"Invalid {path} control characters.")
    elif kind == "boolean" and type(value) is not bool:
        raise ValueError(f"Invalid {path} boolean.")
    elif kind == "number" and (type(value) not in (int, float) or not math.isfinite(value)):
        raise ValueError(f"Invalid {path} number.")


@dataclass(frozen=True)
class FactValue:
    type: str
    value: str | bool | float
    unit: str | None = None

    def payload(self) -> dict:
        if self.type == "descriptor":
            return {"type": self.type, "text": self.value}
        if self.type == "boolean":
            return {"type": self.type, "value": self.value}
        return {"type": self.type, "amount": self.value, "unit": self.unit}


@dataclass(frozen=True)
class Referent:
    id: str
    kind: str
    parent: str


@dataclass(frozen=True)
class Query:
    subject: str
    facet: str


@dataclass(frozen=True)
class Perception:
    mode: str
    access_evidence: tuple[str, ...]
    scope: str


@dataclass(frozen=True)
class CandidateFact:
    subject: str
    facet: str
    value: FactValue
    statement: str
    scope: str
    lifetime: str
    constraint_ids: tuple[str, ...]


@dataclass(frozen=True)
class Fact:
    id: str
    detail: CandidateFact
    origin: str
    established_turn: int
    scene_revision: int
    weather_revision: int
    established_at: str | None = None
    superseded_reason: str | None = None


@dataclass(frozen=True)
class EstimateDetail:
    statement: str
    evidence_ids: tuple[str, ...]
    uncertainty: str


@dataclass(frozen=True)
class Estimate:
    id: str
    query: Query
    detail: EstimateDetail
    established_turn: int
    scene_revision: int
    weather_revision: int
    established_at: str | None = None
    superseded_reason: str | None = None


@dataclass(frozen=True)
class Observation:
    id: str
    fact_ids: tuple[str, ...]
    estimate_id: str | None
    perception: Perception
    turn: int
    revision: int


@dataclass(frozen=True)
class Resolution:
    status: str
    query: Query
    perception: Perception
    reuse_fact_ids: tuple[str, ...] = ()
    proposed_referents: tuple[Referent, ...] = ()
    proposed_facts: tuple[CandidateFact, ...] = ()
    answer_fact_refs: tuple[str, ...] = ()
    estimate: EstimateDetail | None = None
    reuse_estimate_id: str | None = None
    limitation: str | None = None
    clarification: tuple[str, ...] | None = None

    def payload(self) -> dict:
        data = asdict(self)
        data["proposed_facts"] = [asdict(fact) | {"value": fact.value.payload()} for fact in self.proposed_facts]
        data["clarification"] = {"candidates": list(self.clarification)} if self.clarification else None
        # JSON schemas use arrays, while immutable domain types use tuples.
        return json.loads(json.dumps(data))


def decode_resolution(data: dict) -> Resolution:
    check_schema(data, RESOLUTION_SCHEMA)
    facts = []
    for fact in data["proposed_facts"]:
        value = fact["value"]
        facts.append(CandidateFact(
            fact["subject"], fact["facet"],
            FactValue(value["type"], value.get("text", value.get("value", value.get("amount"))), value.get("unit")),
            fact["statement"], fact["scope"], fact["lifetime"], tuple(fact["constraint_ids"]),
        ))
    estimate = data["estimate"]
    return Resolution(
        data["status"], Query(**data["query"]),
        Perception(data["perception"]["mode"], tuple(data["perception"]["access_evidence"]), data["perception"]["scope"]),
        tuple(data["reuse_fact_ids"]), tuple(Referent(**item) for item in data["proposed_referents"]),
        tuple(facts), tuple(data["answer_fact_refs"]),
        EstimateDetail(estimate["statement"], tuple(estimate["evidence_ids"]), estimate["uncertainty"]) if estimate else None,
        data["reuse_estimate_id"], data["limitation"],
        tuple(data["clarification"]["candidates"]) if data["clarification"] else None,
    )


@dataclass(frozen=True)
class PreparedObservation:
    proposal_id: str
    revision: int
    scene_revision: int
    weather_revision: int
    resolution: Resolution
    statements: tuple[str, ...]
    reviewed: bool
    fallback: bool = False


@dataclass(frozen=True)
class CommitReceipt:
    proposal_id: str
    fact_ids: tuple[str, ...]
    statements: tuple[str, ...]
    turn: int
    revision: int
    directive: "Directive | None" = None


@dataclass
class FactStore:
    referents: dict[str, Referent] = field(default_factory=dict)
    facts: dict[str, Fact] = field(default_factory=dict)
    observations: list[Observation] = field(default_factory=list)
    estimates: dict[str, Estimate] = field(default_factory=dict)
    commits: dict[str, CommitReceipt] = field(default_factory=dict)

    def snapshot(self) -> dict:
        return json.loads(json.dumps({
            "referents": [asdict(item) for item in self.referents.values()],
            "facts": [asdict(item) | {"detail": asdict(item.detail) | {"value": item.detail.value.payload()}}
                      for item in self.facts.values()],
            "observations": [asdict(item) for item in self.observations],
            "estimates": [asdict(item) for item in self.estimates.values()],
        }))


class PatchRejected(ValueError):
    """A decoded proposal violates authority, perception, or consistency policy."""


SUBJECT_ALIASES = {"sky": "harbor.sky", "clouds": "harbor.sky", "harbor.clouds": "harbor.sky",
                   "water": "harbor.water", "window": "office.window", "desk": "office.desk",
                   "tide_ledger": "ledger", "rescue_key": "key", "alarm_bell": "bell"}
FACET_ALIASES = {"clouds": "appearance.cloud_cover", "cloud_cover": "appearance.cloud_cover",
                 "appearance.clouds": "appearance.cloud_cover", "weather.cloud_cover": "appearance.cloud_cover",
                 "weather.clouds": "appearance.cloud_cover", "appearance.sky_condition": "appearance.cloud_cover",
                 "appearance.colour": "appearance.color"}
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")
RESOURCE_WORDS = frozenset({"key", "keys", "boat", "boats", "skiff", "rope", "ropes", "tool", "tools",
                            "thermometer", "exit", "route", "passage", "stranger", "person", "people",
                            "traveler", "maren", "locker", "weapon", "weapons"})
SAFE_CATEGORIES = frozenset({"appearance", "texture", "sound", "smell", "temperature", "presence"})
RESERVED_FACETS = frozenset({"ownership", "owner", "inventory", "permissions", "permission", "access",
                            "safety", "safe", "route", "advice", "objective", "commitment", "event",
                            "forecast", "prediction", "key_given", "ledger_read", "trust", "ending"})


def canonical_subject(subject: str) -> str:
    normalized = subject.strip().lower().replace(" ", "_")
    return SUBJECT_ALIASES.get(normalized, normalized)


def canonical_facet(facet: str) -> str:
    normalized = facet.strip().lower().replace(" ", "_")
    return FACET_ALIASES.get(normalized, normalized)


def canon_fact(item: CanonFact) -> Fact:
    return Fact(item.id, CandidateFact(item.subject, item.facet, FactValue(item.value_type, item.value),
                item.statement, item.scope, item.lifetime, ()), "authored", 0, 0, 0)


def active_facts(world: "World") -> dict[str, Fact]:
    return {item.id: canon_fact(item) for item in world.scene.canon} | {
        key: fact for key, fact in world.facts.facts.items() if fact.superseded_reason is None
    }


def access_anchors(world: "World") -> dict:
    return {anchor.id: anchor for anchor in world.scene.anchors
            if not anchor.requires_ledger_read or world.ledger_read}


def _parent(world: "World", subject: str, proposed: tuple[Referent, ...]) -> str | None:
    refs = world.facts.referents | {item.id: item for item in proposed}
    if subject in refs:
        return refs[subject].parent
    if subject in ("key", "ledger", "bell"):
        return "office"
    parent = subject.rpartition(".")[0]
    return parent or None


def _within(world: "World", subject: str, ancestor: str, proposed: tuple[Referent, ...]) -> bool:
    seen = set()
    while subject and subject not in seen:
        if subject == ancestor:
            return True
        seen.add(subject)
        subject = _parent(world, subject, proposed)
    return False


def _accessible(world: "World", subject: str, facet: str, perception: Perception,
                proposed: tuple[Referent, ...], fact_scope: str | None = None) -> bool:
    anchors = access_anchors(world)
    category = facet.split(".")[0]
    for evidence_id in perception.access_evidence:
        anchor = anchors[evidence_id]
        if (anchor.mode == perception.mode and anchor.scope == perception.scope and category in anchor.categories
                and _within(world, subject, anchor.subject, proposed)
                and (fact_scope is None or fact_scope in (anchor.scope, anchor.subject, subject))):
            return True
    return False


def needs_review(resolution: Resolution) -> bool:
    return bool(resolution.proposed_referents or resolution.proposed_facts or resolution.estimate)


def _atomic_statement(statement: str) -> bool:
    return (statement.endswith((".", "!")) and len(statement.split()) <= 50 and "?" not in statement
            and not re.search(r"[.!]\s+\S", statement)
            and not re.match(r"^(?:Maren|Narrator):", statement, re.I))


def validate_resolution(world: "World", resolution: Resolution) -> Resolution:
    """Pure validation and canonicalization; rejection never changes the overlay."""
    try:
        check_schema(resolution.payload(), RESOLUTION_SCHEMA)
    except ValueError as error:
        raise PatchRejected(str(error)) from error
    query = Query(canonical_subject(resolution.query.subject), canonical_facet(resolution.query.facet))
    referents = tuple(replace(item, id=canonical_subject(item.id), parent=canonical_subject(item.parent))
                      for item in resolution.proposed_referents)
    candidates = tuple(replace(item, subject=canonical_subject(item.subject), facet=canonical_facet(item.facet))
                       for item in resolution.proposed_facts)
    resolution = replace(resolution, query=query, proposed_referents=referents, proposed_facts=candidates)
    if not IDENTIFIER.fullmatch(query.subject) or not IDENTIFIER.fullmatch(query.facet):
        raise PatchRejected("The canonical query is not a valid identifier.")
    if resolution.perception.scope not in world.scene.scopes:
        raise PatchRejected("Unknown perception scope.")
    anchors = access_anchors(world)
    if any(item not in anchors for item in resolution.perception.access_evidence):
        raise PatchRejected("Unknown or unavailable access evidence.")
    facts = active_facts(world)
    if any(item not in facts for item in resolution.reuse_fact_ids):
        raise PatchRejected("Unknown or superseded reused fact.")
    known = set(world.scene.referents) | set(world.facts.referents)
    for referent in referents:
        if (not IDENTIFIER.fullmatch(referent.id) or referent.id in known or referent.parent not in known
                or not referent.id.startswith(referent.parent + ".")):
            raise PatchRejected("A referent must be new scenery below an established parent.")
        words = set(re.split(r"[._]", referent.id))
        # Scoped absence can describe boats in an existing view without creating a boat.
        boat_absence = (words & RESOURCE_WORDS <= {"boat", "boats"} and candidates
                        and all(fact.facet == "presence.visible" and fact.value == FactValue("boolean", False)
                                and fact.scope == resolution.perception.scope and fact.lifetime == "current_view"
                                for fact in candidates))
        if words & RESOURCE_WORDS and not boat_absence:
            raise PatchRejected("Generated referents cannot introduce resources, exits, or actors.")
        known.add(referent.id)
    if resolution.status in ("unobservable", "ambiguous", "protected"):
        if (referents or candidates or resolution.reuse_fact_ids or resolution.answer_fact_refs
                or resolution.estimate or resolution.reuse_estimate_id):
            raise PatchRejected("A limitation or clarification cannot establish facts or estimates.")
        if resolution.status == "unobservable":
            if resolution.limitation is None or resolution.clarification is not None:
                raise PatchRejected("Unobservable information needs a sensory limitation.")
            if resolution.limitation == "no_access" and _accessible(world, query.subject, query.facet,
                                                                     resolution.perception, ()):
                raise PatchRejected("The claimed lack of access contradicts supplied access evidence.")
        elif resolution.status == "ambiguous":
            if (not resolution.clarification or len(resolution.clarification) < 2 or resolution.limitation
                    or any(canonical_subject(item) not in known for item in resolution.clarification)):
                raise PatchRejected("Clarification needs at least two established competing referents.")
        elif resolution.limitation or resolution.clarification:
            raise PatchRejected("Protected responses cannot carry other response structures.")
        return resolution
    if resolution.limitation or resolution.clarification:
        raise PatchRejected("Accepted answers cannot smuggle limitations or clarifications into facts.")
    if not resolution.perception.access_evidence or resolution.perception.mode == "none":
        raise PatchRejected("Direct information requires positive access evidence.")
    constraints = dict(world.scene.constraints)
    slots = set()
    for fact in candidates:
        category = fact.facet.partition(".")[0]
        if fact.subject not in known or not IDENTIFIER.fullmatch(fact.facet) or category not in SAFE_CATEGORIES:
            raise PatchRejected("Only descriptive facts about established scenery are permitted.")
        if set(fact.facet.split(".")) & RESERVED_FACETS:
            raise PatchRejected("Descriptive facets cannot change protected mechanics or causal events.")
        if fact.subject in ("key", "ledger", "bell") and category not in ("appearance", "texture"):
            raise PatchRejected("Protected objects allow only safe appearance and texture details.")
        if fact.scope not in world.scene.scopes or any(item not in constraints for item in fact.constraint_ids):
            raise PatchRejected("Unknown fact scope or constraint.")
        if not _accessible(world, fact.subject, fact.facet, resolution.perception, referents, fact.scope):
            raise PatchRejected("The proposed fact is not perceptible through its supplied evidence.")
        if fact.value.type == "number" and not any(
            anchors[item].measurement_unit == fact.value.unit for item in resolution.perception.access_evidence
        ):
            raise PatchRejected("Exact measurements require an accepted measuring source and unit.")
        if category == "presence" and (fact.facet != "presence.visible" or fact.scope != resolution.perception.scope
                                        or fact.lifetime != "current_view" or fact.value.type != "boolean"):
            raise PatchRejected("Presence is scoped to this evidenced view, not the whole world.")
        if category == "presence" and fact.value.value is True:
            raise PatchRejected("Do not create consequential resources through positive presence facts.")
        if ("cloud" in fact.facet or fact.facet == "appearance.weather") and fact.lifetime != "current_weather_episode":
            raise PatchRejected("Weather detail must belong to the current weather episode.")
        slot = (fact.subject, fact.facet, fact.scope)
        if slot in slots:
            raise PatchRejected("Duplicate canonical fact slot.")
        slots.add(slot)
        for existing in facts.values():
            old = existing.detail
            overlaps = old.scope == fact.scope or old.scope in ("harbor", "office") or fact.scope in ("harbor", "office")
            if old.subject == fact.subject and old.facet == fact.facet and overlaps:
                raise PatchRejected("An applicable canonical fact already exists; reuse its ID instead of replacing it.")
        if (world.scene.weather == "storm" and fact.facet == "appearance.cloud_cover"
                and fact.value.type == "descriptor" and str(fact.value.value).lower() in ("clear", "cloudless", "clear_sky")):
            raise PatchRejected("Clear skies contradict the authored active storm.")
        if not _atomic_statement(fact.statement):
            raise PatchRejected("Facts require bounded complete atomic statements.")
    if any(item.id not in {fact.subject for fact in candidates} for item in referents):
        raise PatchRejected("Do not introduce unused scenery.")
    if resolution.status == "estimated":
        if (candidates or referents or resolution.answer_fact_refs
                or bool(resolution.estimate) == bool(resolution.reuse_estimate_id)):
            raise PatchRejected("An estimate is separate from confirmed facts and needs exactly one estimate source.")
        if resolution.estimate:
            if not _atomic_statement(resolution.estimate.statement):
                raise PatchRejected("An estimate needs a bounded complete atomic statement.")
            if not resolution.estimate.evidence_ids:
                raise PatchRejected("An estimate requires accepted supporting evidence.")
            permitted = set(resolution.reuse_fact_ids) | set(resolution.perception.access_evidence)
            if any(item not in permitted for item in resolution.estimate.evidence_ids):
                raise PatchRejected("Unknown estimate evidence.")
        else:
            estimate = world.facts.estimates.get(resolution.reuse_estimate_id)
            if not estimate or estimate.superseded_reason or estimate.query != query:
                raise PatchRejected("Unknown, superseded, or unrelated estimate.")
            if any(item not in facts and item not in anchors for item in estimate.detail.evidence_ids):
                raise PatchRejected("The estimate's supporting evidence is no longer available.")
            permitted = set(resolution.reuse_fact_ids) | set(resolution.perception.access_evidence)
            if any(item not in permitted for item in estimate.detail.evidence_ids):
                raise PatchRejected("A reused estimate needs its accessible supporting evidence again.")
    else:
        if resolution.estimate or resolution.reuse_estimate_id or not resolution.answer_fact_refs:
            raise PatchRejected("Confirmed answers need fact references and cannot contain an estimate.")
        proposed_refs = {f"proposed_facts/{index}": fact for index, fact in enumerate(candidates)}
        if set(proposed_refs) - set(resolution.answer_fact_refs):
            raise PatchRejected("The patch must contain only facts needed for the answer.")
        for ref in resolution.answer_fact_refs:
            if ref in proposed_refs:
                continue
            if ref not in resolution.reuse_fact_ids:
                raise PatchRejected("An answer reference must name a reused or proposed fact.")
        answered = [proposed_refs[ref] if ref in proposed_refs else facts[ref].detail
                    for ref in resolution.answer_fact_refs]
        if not any(fact.subject == query.subject and (fact.facet == query.facet or query.facet == "appearance.detail")
                   for fact in answered):
            raise PatchRejected("The answer must address the canonical subject and facet being queried.")
    for ref in resolution.reuse_fact_ids:
        fact = facts[ref].detail
        if not _accessible(world, fact.subject, fact.facet, resolution.perception, referents, fact.scope):
            raise PatchRejected("The player cannot access this reused fact through the stated source.")
    return resolution


def render_resolution(world: "World", resolution: Resolution) -> tuple[str, ...]:
    """Render canonical statements directly; there is no final generative prose pass."""
    if resolution.status == "resolved":
        facts = active_facts(world)
        return tuple(resolution.proposed_facts[int(ref.split("/")[1])].statement
                     if ref.startswith("proposed_facts/") else facts[ref].detail.statement
                     for ref in resolution.answer_fact_refs)
    if resolution.status == "estimated":
        estimate = resolution.estimate or world.facts.estimates[resolution.reuse_estimate_id].detail
        return (f"An estimate ({estimate.uncertainty}), based on the available evidence: {estimate.statement}",)
    if resolution.status == "ambiguous":
        names = ", ".join(item.replace(".", " ").replace("_", " ") for item in resolution.clarification)
        return (f"Which do you mean: {names}?",)
    if resolution.status == "protected":
        return ("You would need to examine it directly or ask Maren about it.",)
    return ({
        "no_access": "You cannot establish that detail from here.",
        "requires_touch": "You cannot tell how it feels without direct contact.",
        "requires_measurement": "You cannot determine that measurement from here.",
    }[resolution.limitation],)


def commit_observation(state: "World", prepared: PreparedObservation) -> CommitReceipt:
    """Commit once to a private turn draft; the caller publishes the complete World."""
    if prepared.proposal_id in state.facts.commits:
        return state.facts.commits[prepared.proposal_id]
    if (prepared.revision, prepared.scene_revision, prepared.weather_revision) != (
        state.revision, state.scene_revision, state.weather_revision
    ):
        raise PatchRejected("Stale observation proposal.")
    resolution = validate_resolution(state, prepared.resolution)
    if needs_review(resolution) and not prepared.reviewed:
        raise PatchRejected("New facts and estimates require a clear semantic review pass.")
    statements = render_resolution(state, resolution)
    if statements != prepared.statements:
        raise PatchRejected("Prepared statements must match accepted fact references.")
    # Nothing mutates before all checks finish.
    established_at = datetime.now(timezone.utc).isoformat()
    state.facts.referents.update({item.id: item for item in resolution.proposed_referents})
    new_ids = []
    for candidate in resolution.proposed_facts:
        fact_id = f"fact_{len(state.facts.facts) + 1:03d}"
        state.facts.facts[fact_id] = Fact(fact_id, candidate, "generated", state.turn,
                                        state.scene_revision, state.weather_revision, established_at)
        new_ids.append(fact_id)
    fact_ids = tuple(new_ids[int(ref.split("/")[1])] if ref.startswith("proposed_facts/") else ref
                     for ref in resolution.answer_fact_refs)
    estimate_id = resolution.reuse_estimate_id
    if resolution.estimate:
        estimate_id = f"estimate_{len(state.facts.estimates) + 1:03d}"
        state.facts.estimates[estimate_id] = Estimate(estimate_id, resolution.query, resolution.estimate,
            state.turn, state.scene_revision, state.weather_revision, established_at)
    if fact_ids or estimate_id:
        state.facts.observations.append(Observation(f"observation_{len(state.facts.observations) + 1:03d}",
            fact_ids, estimate_id, resolution.perception, state.turn, state.revision + 1))
    receipt = CommitReceipt(prepared.proposal_id, fact_ids, statements, state.turn, state.revision + 1)
    state.facts.commits[prepared.proposal_id] = receipt
    return receipt


def revise_scene(world: "World", scene, *, reason: str, weather_changed: bool = False) -> "World":
    """An authored event explicitly invalidates view/weather detail and its estimates."""
    from copy import deepcopy
    if not reason.strip():
        raise ValueError("An authored scene change needs a recorded reason.")
    if scene.weather != world.scene.weather and not weather_changed:
        raise ValueError("A change of weather must explicitly supersede the weather episode.")
    state = deepcopy(world)
    state.scene = scene
    state.revision += 1
    state.scene_revision += 1
    if weather_changed:
        state.weather_revision += 1
    for key, fact in state.facts.facts.items():
        canon_replaced = any(item.subject == fact.detail.subject and item.facet == fact.detail.facet
                             for item in scene.canon)
        if (canon_replaced or fact.detail.lifetime == "current_view"
                or (weather_changed and fact.detail.lifetime == "current_weather_episode")):
            state.facts.facts[key] = replace(fact, superseded_reason=reason)
    for key, estimate in state.facts.estimates.items():
        state.facts.estimates[key] = replace(estimate, superseded_reason=reason)
    from ..trace import record
    record("observation.scene_revised", "An authored event explicitly supersedes transient detail and dependent estimates.",
           revision=state.revision, scene_revision=state.scene_revision, weather_revision=state.weather_revision,
           superseded_reason=reason, weather_changed=weather_changed)
    return state
