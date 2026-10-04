"""Observation contracts, authoritative transactions, and real mocked model transports."""

from copy import deepcopy
from dataclasses import replace
import io
import json
from unittest.mock import patch

import httpx2
import pytest
from typesafe_sdk import ChoiceAnswer, NoulAnswer, ScoreAnswer, RetryPolicy, TypeSafeClient

from convgame.bonsai import BonsaiNarrator
from convgame.cli import play
from convgame.jev import JevDecider, questions
from convgame.observations import observation_context, prepare_observation
from convgame.trace import file_log
from convgame.world import Action, Decisions, Object, Pick, Recipient, Speaker, World, advance
from convgame.world.facts import (CandidateFact, FactValue, PatchRejected, decode_resolution,
                                 render_resolution, revise_scene, validate_resolution)
from convgame.world.scene import AccessAnchor, CanonFact, DEFAULT_SCENE


OBSERVE = Decisions(
    action=Pick("observe", 1), action_object=Pick("unknown", 0), recipient=Pick("none", 1),
    intent=Pick("none", 0), object=Pick("unknown", 0), off_world=Pick("no", 1),
    rescue_plan=Pick("yes", 1), handover=Pick("yes", 1), tension=1,
    tension_confidence=1, hostility=1, reassurance=1,
)


def cloud_payload():
    return {
        "status": "resolved",
        "query": {"subject": "harbor.sky", "facet": "appearance.cloud_cover"},
        "perception": {"mode": "sight", "access_evidence": ["scene.window_harbor_view"], "scope": "office.window_view"},
        "reuse_fact_ids": [],
        "proposed_referents": [{"id": "harbor.sky", "kind": "scenery", "parent": "harbor"}],
        "proposed_facts": [{
            "subject": "harbor.sky", "facet": "appearance.cloud_cover",
            "value": {"type": "descriptor", "text": "low_dark_overcast"},
            "statement": "Low, dark clouds cover the harbor sky.",
            "scope": "harbor", "lifetime": "current_weather_episode",
            "constraint_ids": ["scene.storm_active"],
        }],
        "answer_fact_refs": ["proposed_facts/0"],
        "estimate": None, "reuse_estimate_id": None, "limitation": None, "clarification": None,
    }


def reuse_payload(fact_id="fact_001", subject="sky", facet="appearance.clouds"):
    data = cloud_payload()
    data.update(proposed_referents=[], proposed_facts=[], reuse_fact_ids=[fact_id], answer_fact_refs=[fact_id])
    data["query"] = {"subject": subject, "facet": facet}
    return data


def limitation_payload(reason="requires_touch", subject="harbor.water", facet="temperature.feel"):
    data = cloud_payload()
    data.update(status="unobservable", proposed_referents=[], proposed_facts=[], answer_fact_refs=[], limitation=reason)
    data["query"] = {"subject": subject, "facet": facet}
    return data


class Model:
    """Domain-level model double for policy/transaction tests (transport is tested below)."""

    def __init__(self, proposals, verdicts=None):
        self.proposals = iter(proposals)
        self.verdicts = iter(verdicts or [{"verdict": "pass", "reason": "Compatible and perceptible."}] * 2)
        self.resolutions = []
        self.reviews = []

    def resolve_observation(self, context, rejection=None):
        self.resolutions.append((context, rejection))
        proposal = next(self.proposals)
        if isinstance(proposal, Exception):
            raise proposal
        return decode_resolution(proposal)

    def review_observation(self, context, resolution):
        self.reviews.append((context, resolution))
        verdict = next(self.verdicts)
        if isinstance(verdict, Exception):
            raise verdict
        return verdict

    def narrate(self, world, line, directive):
        return directive.fallback


def establish_clouds(world=None):
    world = world or World()
    prepared = prepare_observation(world, "Are there clounds on the sky?", Model([cloud_payload()]))
    return advance(world, OBSERVE, observation=prepared)


def test_observation_has_no_object_enum_and_cannot_change_mechanics_or_emotions():
    original = World(ledger_read=True, plan_agreed=True, trust=1)
    before = deepcopy(original)
    prepared = prepare_observation(original, "Are there clouds?", Model([cloud_payload()]))
    assert original == before  # Preparation is read-only, even with a clear review pass.
    state, directive = advance(original, OBSERVE, observation=prepared)
    assert "sky" not in set(Object)
    assert directive.events == ("observation",)
    assert not directive.player_spoke
    assert all(beat.speaker == Speaker.NARRATOR and beat.approved for beat in directive.beats)
    assert (state.trust, state.suspicion, state.composure) == (original.trust, original.suspicion, original.composure)
    assert state.ledger_read and state.plan_agreed and not state.key_given
    assert state.turn == state.revision == 1
    fact = state.facts.facts["fact_001"]
    assert fact.origin == "generated" and fact.established_turn == 1
    assert state.facts.observations[0].fact_ids == ("fact_001",)
    assert state.facts.observations[0].perception.access_evidence == ("scene.window_harbor_view",)
    assert original == before
    assert not World().facts.facts


def test_fact_persists_after_its_response_leaves_history_and_paraphrase_reuses_id():
    state, directive = establish_clouds()
    state.history = [{"role": "assistant", "content": directive.fallback[0].text}]
    quiet = replace(OBSERVE, action=Pick("none", 1))
    for index in range(4):
        state, _ = advance(state, quiet)
        state.history.extend([{"role": "user", "content": f"silent {index}"},
                              {"role": "assistant", "content": "No words reach Maren."}])
        state.history = state.history[-6:]
    assert "clouds" not in json.dumps(state.history)
    model = Model([reuse_payload()])
    prepared = prepare_observation(state, "Has the sky cleared yet?", model)
    final, reply = advance(state, OBSERVE, observation=prepared)
    assert not model.reviews  # Reuse does not require a semantic enrichment review.
    assert len(final.facts.facts) == 1
    assert final.facts.observations[-1].fact_ids == ("fact_001",)
    assert reply.fallback[0].text == directive.fallback[0].text
    assert prepared.resolution.query.subject == "harbor.sky"
    assert prepared.resolution.query.facet == "appearance.cloud_cover"
    assert "fact_001" in json.dumps(model.resolutions[0][0])


def test_snapshot_and_turn_drafts_do_not_share_overlay_or_history_collections():
    state, _ = establish_clouds()
    state.history = [{"role": "assistant", "content": "Original."}]
    snapshot = state.snapshot()
    snapshot["observations"]["facts"][0]["detail"]["statement"] = "Changed."
    snapshot["observations"]["observations"][0]["fact_ids"].clear()
    snapshot["observations"]["referents"].clear()
    next_state, _ = advance(state, replace(OBSERVE, action=Pick("none", 1)))
    next_state.facts.facts.clear()
    next_state.facts.referents.clear()
    next_state.facts.observations.clear()
    next_state.history[0]["content"] = "Changed."
    assert len(state.facts.facts) == len(state.facts.referents) == len(state.facts.observations) == 1
    assert state.facts.facts["fact_001"].detail.statement.startswith("Low, dark")
    assert state.history[0]["content"] == "Original."


@pytest.mark.parametrize("reason", ["requires_touch", "requires_measurement"])
def test_remote_temperature_limit_never_creates_a_temperature_fact(reason):
    model = Model([limitation_payload(reason)])
    prepared = prepare_observation(World(), "How cold is the water?", model)
    state, directive = advance(World(), OBSERVE, observation=prepared)
    assert not state.facts.facts and not state.facts.referents and not state.facts.estimates
    assert state.turn == 1 and not model.reviews
    assert "cannot" in directive.fallback[0].text


def test_cellar_does_not_reveal_sky_and_bright_sun_allows_clear_or_light_clouds():
    cellar = replace(DEFAULT_SCENE, location="A windowless cellar.", anchors=(), canon=(),
                     fallback="You cannot see the sky from the cellar.", look="A windowless cellar.")
    data = limitation_payload("no_access", "harbor.sky", "appearance.cloud_cover")
    data["perception"].update(mode="none", access_evidence=[], scope="office")
    world = World(scene=cellar)
    prepared = prepare_observation(world, "Are there clouds?", Model([data]))
    state, directive = advance(world, OBSERVE, observation=prepared)
    assert not state.facts.facts and "cannot" in directive.fallback[0].text
    with pytest.raises(PatchRejected, match="evidence"):
        validate_resolution(world, decode_resolution(cloud_payload()))
    sunny = replace(DEFAULT_SCENE, weather="sunshine", constraints=(("scene.sunshine", "Bright sunshine outdoors."),),
                    canon=(), location="An outdoor harbor in bright sunshine.")
    for descriptor in ("clear", "thin_horizon_clouds"):
        data = cloud_payload()
        data["proposed_facts"][0].update(value={"type": "descriptor", "text": descriptor}, constraint_ids=["scene.sunshine"])
        assert validate_resolution(World(scene=sunny), decode_resolution(data)).proposed_facts[0].value.value == descriptor


def test_accepted_contact_allows_qualitative_temperature_without_inventing_touch():
    touch = AccessAnchor("event.water_contact", "harbor.water", "touch", "harbor", ("temperature",),
                         "An authored action has already placed the player's hand in harbor water.")
    world = World(scene=replace(DEFAULT_SCENE, anchors=DEFAULT_SCENE.anchors + (touch,)))
    data = cloud_payload()
    data["query"] = {"subject": "water", "facet": "temperature.feel"}
    data["perception"] = {"mode": "touch", "access_evidence": ["event.water_contact"], "scope": "harbor"}
    data["proposed_referents"][0].update(id="harbor.water")
    data["proposed_facts"][0].update(subject="water", facet="temperature.feel",
        value={"type": "descriptor", "text": "cold"}, statement="The water feels cold against your hand.")
    prepared = prepare_observation(world, "How cold is the water?", Model([data]))
    state, reply = advance(world, OBSERVE, observation=prepared)
    assert state.facts.facts["fact_001"].detail.value == FactValue("descriptor", "cold")
    assert reply.fallback[0].text == "The water feels cold against your hand."
    with pytest.raises(PatchRejected, match="evidence"):
        validate_resolution(World(), decode_resolution(data))


def test_estimate_remains_qualified_separate_and_can_be_reused():
    data = cloud_payload()
    data.update(status="estimated", proposed_referents=[], proposed_facts=[], answer_fact_refs=[],
                estimate={"statement": "The water is probably cold during the storm.",
                          "evidence_ids": ["scene.window_harbor_view"], "uncertainty": "likely"})
    data["query"] = {"subject": "harbor.water", "facet": "temperature.feel"}
    model = Model([data])
    prepared = prepare_observation(World(), "Is the water likely cold?", model)
    state, reply = advance(World(), OBSERVE, observation=prepared)
    assert len(model.reviews) == 1 and not state.facts.facts
    assert state.facts.observations[0].estimate_id == "estimate_001"
    assert "estimate (likely)" in reply.fallback[0].text.lower()
    data.update(estimate=None, reuse_estimate_id="estimate_001")
    model = Model([data])
    prepared = prepare_observation(state, "What was your estimate?", model)
    final, reused = advance(state, OBSERVE, observation=prepared)
    assert len(final.facts.estimates) == 1 and not model.reviews
    assert reused.fallback == reply.fallback
    bad = deepcopy(data)
    bad.update(status="resolved", reuse_estimate_id=None, reuse_fact_ids=["estimate_001"], answer_fact_refs=["estimate_001"])
    with pytest.raises(PatchRejected, match="fact"):
        validate_resolution(state, decode_resolution(bad))


def test_scoped_absence_does_not_create_a_usable_boat_or_global_absence():
    data = cloud_payload()
    data["query"] = {"subject": "harbor.boats", "facet": "presence.visible"}
    data["proposed_referents"][0].update(id="harbor.boats")
    data["proposed_facts"][0].update(subject="harbor.boats", facet="presence.visible", value={"type": "boolean", "value": False},
        statement="You see no other boats in the stretch of harbor visible from here.",
        scope="office.window_view", lifetime="current_view")
    prepared = prepare_observation(World(), "Are there more boats?", Model([data]))
    state, _ = advance(World(), OBSERVE, observation=prepared)
    assert state.facts.facts["fact_001"].detail.scope == "office.window_view"
    assert state.facts.referents["harbor.boats"].kind == "scenery"
    for field, value in [("scope", "harbor"), ("lifetime", "encounter"), ("value", {"type": "boolean", "value": True})]:
        bad = deepcopy(data)
        bad["proposed_facts"][0][field] = value
        with pytest.raises(PatchRejected):
            validate_resolution(World(), decode_resolution(bad))
    boat = CanonFact("canon.visible_boat", "harbor.boats", "presence.visible", "boolean", True,
                     "A boat is visible through the window.", "office.window_view", "current_view")
    with pytest.raises(PatchRejected, match="canonical fact"):
        validate_resolution(World(scene=replace(DEFAULT_SCENE, canon=DEFAULT_SCENE.canon + (boat,))), decode_resolution(data))


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(key_given=True),
    lambda d: d["proposed_facts"][0].update(trust=1),
    lambda d: d["proposed_referents"][0].update(kind="inventory"),
    lambda d: d["proposed_facts"].append(deepcopy(d["proposed_facts"][0])),
    lambda d: d["proposed_facts"].extend([deepcopy(d["proposed_facts"][0])] * 2),
    lambda d: d["proposed_facts"][0].update(value={"type": "descriptor", "text": "x" * 121}),
    lambda d: d["proposed_facts"][0].update(value={"type": "number", "amount": float("nan"), "unit": "C"}),
    lambda d: d["proposed_facts"][0].update(value={"type": "boolean", "value": 0}),
    lambda d: d["proposed_facts"][0].update(statement="Text\x1b."),
])
def test_strict_decode_rejects_malformed_and_unrestricted_state_edits(mutation):
    data = cloud_payload()
    mutation(data)
    original = World()
    with pytest.raises(ValueError):
        decode_resolution(data)
    assert not original.facts.facts and original.turn == 0


@pytest.mark.parametrize("mutation", [
    lambda d: d["perception"].update(access_evidence=["invented.window"]),
    lambda d: d["perception"].update(access_evidence=[]),
    lambda d: d["perception"].update(mode="touch"),
    lambda d: d["perception"].update(scope="entire_world"),
    lambda d: d["proposed_facts"][0].update(scope="entire_world"),
    lambda d: d["proposed_facts"][0].update(constraint_ids=["invented.storm"]),
    lambda d: d["proposed_facts"][0].update(facet="inventory.spare_key"),
    lambda d: d["proposed_facts"][0].update(value={"type": "number", "amount": 5, "unit": "C"}),
    lambda d: d["proposed_facts"][0].update(value={"type": "descriptor", "text": "clear"}),
    lambda d: d["answer_fact_refs"].append("fact_999"),
    lambda d: d["reuse_fact_ids"].append("fact_999"),
    lambda d: d["proposed_referents"][0].update(parent="unknown"),
    lambda d: d["proposed_facts"][0].update(lifetime="encounter"),
    lambda d: d.update(status="unobservable", limitation="no_access"),
])
def test_invalid_patch_is_pure_and_rejected_as_a_whole(mutation):
    data = cloud_payload()
    mutation(data)
    world = World()
    before = deepcopy(world)
    with pytest.raises(PatchRejected):
        validate_resolution(world, decode_resolution(data))
    assert world == before


@pytest.mark.parametrize("subject", ["harbor.spare_key", "harbor.boat", "office.hidden_exit", "office.stranger", "office.rope"])
def test_structured_resources_and_characters_cannot_be_created(subject):
    data = cloud_payload()
    parent = subject.split(".")[0]
    data["query"]["subject"] = subject
    data["proposed_referents"][0].update(id=subject, parent=parent)
    data["proposed_facts"][0].update(subject=subject)
    with pytest.raises(PatchRejected, match="resources"):
        validate_resolution(World(), decode_resolution(data))


def test_ledger_color_is_safe_but_new_advice_and_ownership_are_protected():
    data = cloud_payload()
    data["query"] = {"subject": "ledger", "facet": "appearance.color"}
    data["perception"].update(access_evidence=["scene.office_view"], scope="office")
    data["proposed_referents"] = []
    data["proposed_facts"][0].update(subject="ledger", facet="appearance.color", value={"type": "descriptor", "text": "brown"},
                                   statement="The ledger has a brown cover.", scope="office", lifetime="encounter")
    prepared = prepare_observation(World(), "What color is the ledger?", Model([data]))
    state, _ = advance(World(), OBSERVE, observation=prepared)
    assert not state.ledger_read and not state.plan_agreed and not state.key_given
    for facet in ("advice.secret_route", "ownership.owner", "permissions.readable", "temperature.feel"):
        bad = deepcopy(data)
        bad["proposed_facts"][0]["facet"] = facet
        with pytest.raises(PatchRejected):
            validate_resolution(World(), decode_resolution(bad))


def test_alias_duplicate_and_conflicting_slot_are_rejected_and_cross_facet_gets_reviewed():
    state, _ = establish_clouds()
    data = cloud_payload()
    data["proposed_referents"] = []
    data["proposed_facts"][0].update(subject="clouds", facet="appearance.clouds")
    with pytest.raises(PatchRejected, match="canonical fact"):
        validate_resolution(state, decode_resolution(data))
    data["proposed_facts"][0].update(subject="harbor.sky", facet="appearance.coverage",
        value={"type": "descriptor", "text": "clear"}, statement="The sky is completely clear.")
    data["query"]["facet"] = "appearance.coverage"
    model = Model([data, reuse_payload()], [{"verdict": "reject", "reason": "Cross-facet contradiction with fact_001."}])
    prepared = prepare_observation(state, "Is the sky clear?", model)
    final, _ = advance(state, OBSERVE, observation=prepared)
    assert len(model.reviews) == 1 and "Cross-facet" in model.resolutions[1][1]
    assert len(final.facts.facts) == 1


def test_reviewer_rejects_misleading_values_presuppositions_and_safety_shortcuts():
    data = cloud_payload()
    data["proposed_facts"][0]["statement"] = "A spare rescue boat waits below the clear sky, making the route safe."
    model = Model([data, data], [{"verdict": "reject", "reason": "Invented resource and safety shortcut."}] * 2)
    prepared = prepare_observation(World(), "What is inside the spare boat?", model)
    state, directive = advance(World(), OBSERVE, observation=prepared)
    assert len(model.resolutions) == len(model.reviews) == 2
    assert not state.facts.facts and not state.facts.referents and not state.facts.observations
    assert not state.key_given and state.turn == 1
    assert "cannot" in directive.fallback[0].text


def test_entire_patch_requires_review_and_every_new_fact_is_part_of_the_answer():
    data = cloud_payload()
    data["proposed_facts"].append(deepcopy(data["proposed_facts"][0]))
    data["proposed_facts"][1].update(facet="appearance.color", value={"type": "descriptor", "text": "gray"},
                                    statement="The harbor sky is gray.")
    with pytest.raises(PatchRejected, match="only facts needed"):
        validate_resolution(World(), decode_resolution(data))
    data["answer_fact_refs"].append("proposed_facts/1")
    prepared = prepare_observation(World(), "Describe the sky.", Model([data]))
    with pytest.raises(PatchRejected, match="review"):
        advance(World(), OBSERVE, observation=replace(prepared, reviewed=False))
    state, directive = advance(World(), OBSERVE, observation=prepared)
    assert len(state.facts.facts) == len(directive.beats) == 2
    assert all(beat.approved for beat in directive.beats)


def test_stale_proposals_replays_and_mismatched_rendering():
    world = World()
    prepared = prepare_observation(world, "Are there clouds?", Model([cloud_payload()]))
    newer, _ = advance(world, replace(OBSERVE, action=Pick("none", 1)))
    with pytest.raises(PatchRejected, match="Stale"):
        advance(newer, OBSERVE, observation=prepared)
    assert not newer.facts.facts
    with pytest.raises(PatchRejected, match="statements"):
        advance(world, OBSERVE, observation=replace(prepared, statements=("The key is yours.",)))
    state, directive = advance(world, OBSERVE, observation=prepared)
    same, replay = advance(state, OBSERVE, observation=prepared)
    assert same is state and replay == directive
    assert same.turn == 1 and len(same.facts.observations) == 1
    ended, _ = advance(state, replace(OBSERVE, action=Pick("none", 1)))
    unchanged, original_reply = advance(ended, OBSERVE, observation=prepared)
    assert unchanged is ended and original_reply == directive


def test_weather_change_explicitly_supersedes_weather_and_estimates_but_keeps_cosmetic_facts():
    state, _ = establish_clouds()
    cosmetic = replace(state.facts.facts["fact_001"], id="fact_002", detail=CandidateFact(
        "office.desk", "texture.grain", FactValue("descriptor", "fine"), "The desk has fine wood grain.",
        "office", "encounter", ()))
    state.facts.facts[cosmetic.id] = cosmetic
    sunny = replace(DEFAULT_SCENE, weather="sunshine", constraints=(("scene.sunshine", "The storm ended; the sun is out."),),
                    canon=(), look="Sunlight fills the harbor office.")
    changed = revise_scene(state, sunny, reason="Authored storm ending.", weather_changed=True)
    assert changed.weather_revision == state.weather_revision + 1
    assert changed.scene_revision == state.scene_revision + 1
    assert changed.facts.facts["fact_001"].superseded_reason == "Authored storm ending."
    assert changed.facts.facts["fact_002"].superseded_reason is None
    assert state.facts.facts["fact_001"].superseded_reason is None
    with pytest.raises(PatchRejected, match="superseded"):
        validate_resolution(changed, decode_resolution(reuse_payload()))
    clear = cloud_payload()
    clear["proposed_referents"] = []
    clear["proposed_facts"][0].update(value={"type": "descriptor", "text": "clear"},
        statement="The sky is clear.", constraint_ids=["scene.sunshine"])
    prepared = prepare_observation(changed, "Has the sky cleared?", Model([clear]))
    final, _ = advance(changed, OBSERVE, observation=prepared)
    assert final.facts.facts["fact_003"].weather_revision == 1
    assert not World().facts.facts


@pytest.mark.parametrize("changes", [
    {"action": Pick("observe", 0.2)},
    {"off_world": Pick("yes", 1)},
    {"recipient": Pick("maren", 1)},
])
def test_observation_confidence_offworld_and_mixed_channels_do_not_resolve_or_change_mood(changes):
    state, directive = advance(World(), replace(OBSERVE, **changes))
    assert state.turn == 1 and not state.facts.facts
    assert state.trust == World().trust and state.suspicion == World().suspicion
    assert directive.event in ("clarify", "off_world", "mixed_observation")
    assert not directive.player_spoke


def test_observation_requires_preparation_and_final_turn_retains_it_before_timeout():
    with pytest.raises(ValueError, match="prepared"):
        advance(World(), OBSERVE)
    world = World(turn=11, revision=11)
    prepared = prepare_observation(world, "Are there clouds?", Model([cloud_payload()]))
    state, directive = advance(world, OBSERVE, observation=prepared)
    assert state.turn == 12 and state.ending == "timeout"
    assert directive.events == ("observation", "timeout")
    assert directive.fallback[0].text == "Low, dark clouds cover the harbor sky."
    with patch("urllib.request.urlopen", side_effect=TimeoutError()):
        with pytest.raises(TimeoutError):
            BonsaiNarrator("http://localhost:8080").narrate(state, "", directive)
    assert "fact_001" in state.facts.facts
    assert "tide" in directive.fallback[-1].text.lower()


def test_approved_observation_never_uses_a_final_prose_pass():
    state, directive = establish_clouds()
    with patch("urllib.request.urlopen") as transport:
        reply = BonsaiNarrator("http://localhost:8080").narrate(state, "Are there clouds?", directive)
    transport.assert_not_called()
    assert reply == directive.fallback


def sdk_response(action="observe", recipient="none"):
    values = {"action": action, "action_object": "unknown", "recipient": recipient, "intent": "none",
              "object": "none", "off_world": "no", "rescue_plan": "no", "handover": "no"}
    answers = {name: ChoiceAnswer(choice=value, confidence=0.99, probabilities={value: 1}).model_dump()
               for name, value in values.items()}
    answers["tension"] = ScoreAnswer(score=0, confidence=1, legend={0: "calm", 1: "pushy", 2: "violent"},
                                     probabilities={0: 1, 1: 0, 2: 0}).model_dump()
    answers["hostility"] = NoulAnswer(noul=0).model_dump()
    answers["reassurance"] = NoulAnswer(noul=0).model_dump()
    return {"model": "jev-latest", "answers": answers, "usage": {"input_tokens": 20, "output_tokens": 10}}


def test_real_jev_decoder_and_bonsai_transport_resolve_review_commit_and_reuse():
    jev_calls, bonsai_calls = [], []
    def jev_transport(request):
        jev_calls.append(json.loads(request.content))
        return httpx2.Response(200, json=sdk_response())
    decider = JevDecider.__new__(JevDecider)
    decider.questions = questions()
    decider.client = TypeSafeClient(api_key="test-only", retry=RetryPolicy(max_retries=0), transport=httpx2.MockTransport(jev_transport))
    model_replies = iter([cloud_payload(), {"verdict": "pass", "reason": "Storm-compatible, perceptible minimal cloud detail."}, reuse_payload()])
    def bonsai_transport(request, timeout):
        body = json.loads(request.data)
        bonsai_calls.append(body)
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": json.dumps(next(model_replies))}}]}).encode())
    world = World()
    narrator = BonsaiNarrator("http://localhost:8080/v1", model="local-test")
    try:
        with patch("urllib.request.urlopen", bonsai_transport):
            for line in ("Are there clounds on the sky?", "Has it cleared?"):
                decisions = decider.decide(world, line)
                prepared = prepare_observation(world, line, narrator)
                world, directive = advance(world, decisions, observation=prepared)
                assert narrator.narrate(world, line, directive) == directive.fallback
    finally:
        decider.close()
    assert len(jev_calls) == 2 and len(bonsai_calls) == 3 and len(world.facts.facts) == 1
    assert decisions.action.value == Action.OBSERVE and decisions.action_object.value == Object.UNKNOWN
    assert all(body["chat_template_kwargs"] == {"enable_thinking": False} for body in bonsai_calls)
    assert all(body["model"] == "local-test" and body["stream"] is False for body in bonsai_calls)
    assert all(body["response_format"]["schema"]["additionalProperties"] is False for body in bonsai_calls)
    review_context = json.loads(bonsai_calls[1]["messages"][1]["content"])
    assert review_context["candidate"]["proposed_facts"][0]["facet"] == "appearance.cloud_cover"
    assert "scene.storm_active" in review_context["scene"]["constraints"]
    assert "fact_001" in json.dumps(jev_calls[1]["state"])
    prompt = jev_calls[0]["questions"]["action"]["instructions"]
    assert "private or imagined questions" in prompt and "What color is the ledger?" in prompt


@pytest.mark.parametrize("response", ["{}", "not JSON", '[{"verdict":"pass"}]',
    '{"verdict":"maybe","reason":"unsure"}', '{"verdict":"pass","reason":"yes","key_given":true}'])
def test_malformed_semantic_verdict_is_a_service_failure(response):
    narrator = BonsaiNarrator("http://localhost:8080")
    replies = iter([json.dumps(cloud_payload()), response])
    def transport(request, timeout):
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": next(replies)}}]}).encode())
    world = World()
    with patch("urllib.request.urlopen", transport), pytest.raises(ValueError):
        prepare_observation(world, "Are there clouds?", narrator)
    assert world.turn == world.revision == 0 and not world.facts.facts


@pytest.mark.parametrize("failure_at", ["resolution", "review"])
def test_cli_preparation_failures_use_no_turn_but_postcommit_render_failure_keeps_facts(failure_at, monkeypatch, capsys):
    model = Model([TimeoutError(), cloud_payload()] if failure_at == "resolution" else [cloud_payload(), cloud_payload()],
                  [TimeoutError(), {"verdict": "pass", "reason": "Accepted."}] if failure_at == "review" else None)
    def failed_render(*args):
        raise TimeoutError()
    model.narrate = failed_render
    worlds = []
    class Decider:
        def decide(self, world, line):
            worlds.append(deepcopy(world))
            return OBSERVE
    lines = iter(["Are there clouds?", "Are there clouds?", "/status", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    assert play(Decider(), model) == 0
    output = capsys.readouterr()
    assert worlds[0] == worlds[1] and worlds[1].turn == 0
    assert "Turn 1/12" in output.out and "Low, dark clouds" in output.out
    assert "No turn used" in output.err and "scripted scene response" in output.err


def test_cli_free_commands_do_not_resolve_or_modify_overlay_and_logs_record_transaction(monkeypatch, capsys, tmp_path):
    model = Model([cloud_payload(), reuse_payload()])
    seen = []
    class Decider:
        def decide(self, world, line):
            seen.append(deepcopy(world))
            return OBSERVE
    lines = iter(["/look", "/status", "Are there clouds?", "/look", "/status", "Has the sky cleared?", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    path = tmp_path / "observation.log"
    with file_log(path):
        play(Decider(), model)
    assert seen[0].turn == 0 and seen[1].turn == 1 and len(seen[1].facts.facts) == 1
    assert len(model.resolutions) == 2 and len(model.reviews) == 1
    output = capsys.readouterr().out
    assert output.count("Low, dark clouds cover the harbor sky.") == 2
    assert "Turn 1/12" in output
    log = path.read_text()
    for event in ("observation.proposed", "observation.reviewed", "observation.prepared", "observation.committed"):
        assert event in log
    for field in ("access_evidence", "reused_fact_ids", "patch", "verdict", "revision"):
        assert field in log


def test_ambiguous_and_protected_responses_are_structured_and_add_no_world_facts():
    data = limitation_payload()
    data.update(status="ambiguous", limitation=None, clarification={"candidates": ["ledger", "bell"]})
    resolution = validate_resolution(World(), decode_resolution(data))
    assert "ledger, bell" in render_resolution(World(), resolution)[0]
    data.update(status="protected", clarification=None)
    prepared = prepare_observation(World(), "Is there a safe secret exit?", Model([data]))
    state, directive = advance(World(), OBSERVE, observation=prepared)
    assert state.turn == 1 and not state.facts.facts
    assert "ask Maren" in directive.fallback[0].text


def test_reused_fact_requires_current_access_even_if_it_is_in_player_memory():
    state, _ = establish_clouds()
    cellar = replace(DEFAULT_SCENE, anchors=(), location="A cellar without a window.")
    moved = revise_scene(state, cellar, reason="Authored move to cellar.")
    assert moved.facts.facts["fact_001"].superseded_reason is None
    data = reuse_payload()
    data["perception"].update(mode="none", access_evidence=[], scope="office")
    with pytest.raises(PatchRejected, match="positive access"):
        validate_resolution(moved, decode_resolution(data))


def test_reuse_cannot_answer_an_unrelated_question_without_review():
    state, _ = establish_clouds()
    data = reuse_payload(subject="harbor.water", facet="temperature.feel")
    with pytest.raises(PatchRejected, match="canonical subject and facet"):
        validate_resolution(state, decode_resolution(data))


def test_character_only_narration_does_not_receive_narrator_discoveries():
    state, _ = establish_clouds()
    state.history = [{"role": "assistant", "content": "Narrator: Low, dark clouds cover the harbor sky."}]
    speech = replace(OBSERVE, action=Pick("none", 1), recipient=Pick("maren", 1),
                     intent=Pick("chat", 1), reassurance=0, hostility=0, tension=0)
    state, directive = advance(state, speech)
    payloads = []
    def transport(request, timeout):
        body = json.loads(request.data)
        payloads.append(json.loads(body["messages"][1]["content"]))
        return io.BytesIO(b'{"choices":[{"message":{"content":"[{\\"speaker\\":\\"Maren\\",\\"text\\":\\"The storm is still here.\\"}]"}}]}')
    with patch("urllib.request.urlopen", transport):
        BonsaiNarrator("http://localhost:8080").narrate(state, "Maren, how is the weather?", directive)
    assert "fact_001" not in json.dumps(payloads)
    assert "Low, dark" not in json.dumps(payloads)
    assert "character_knowledge" in payloads[0]


def test_estimate_and_view_fact_lifetimes_follow_authored_events():
    data = limitation_payload()
    data.update(status="estimated", limitation=None,
                estimate={"statement": "The water is probably cold.",
                          "evidence_ids": ["scene.window_harbor_view"], "uncertainty": "likely"})
    world = World()
    prepared = prepare_observation(world, "Is the water probably cold?", Model([data]))
    world, _ = advance(world, OBSERVE, observation=prepared)
    moved = revise_scene(world, replace(DEFAULT_SCENE, anchors=()), reason="Authored movement away from the window.")
    assert moved.facts.estimates["estimate_001"].superseded_reason is not None
    data.update(estimate=None, reuse_estimate_id="estimate_001")
    data["perception"].update(mode="none", access_evidence=[])
    with pytest.raises(PatchRejected):
        validate_resolution(moved, decode_resolution(data))
    with pytest.raises(ValueError, match="weather episode"):
        revise_scene(World(), replace(DEFAULT_SCENE, weather="sunshine"), reason="Unmarked weather change.")


def test_duplicate_json_fields_are_rejected_by_bonsai_decoder():
    response = '{"verdict":"pass","verdict":"reject","reason":"Contradiction."}'
    def transport(request, timeout):
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": response}}]}).encode())
    with patch("urllib.request.urlopen", transport), pytest.raises(ValueError, match="duplicate observation"):
        BonsaiNarrator("http://localhost:8080").review_observation(observation_context(World(), "Clouds?"), cloud_payload())


def test_live_evaluator_reports_continuity_channels_and_leaves_semantic_metrics_for_human_review(capsys):
    from convgame.evaluate_observations import CHANNEL_SCENARIOS, SCENARIOS, _summary, evaluate
    interpretations = iter((action, recipient) for _, _, action, recipient in SCENARIOS + CHANNEL_SCENARIOS)
    class Decider:
        def decide(self, world, line):
            action, recipient = next(interpretations)
            return replace(OBSERVE, action=Pick(action, 1), recipient=Pick(recipient, 1),
                action_object=Pick("none", 1), intent=Pick("chat" if recipient == "maren" else "none", 1),
                object=Pick("none", 1), rescue_plan=Pick("no", 1), handover=Pick("no", 1),
                tension=0, hostility=0, reassurance=0)
    class EvaluationModel(Model):
        def resolve_observation(self, context, rejection=None):
            line = context["untrusted_player_line"]
            if "sky" in line or "clounds" in line:
                return decode_resolution(reuse_payload() if context["mechanical_state"]["observations"]["facts"] else cloud_payload())
            data = limitation_payload("no_access", "office", "appearance.detail")
            data["perception"].update(mode="none", access_evidence=[], scope="office")
            return decode_resolution(data)
    rows = evaluate(Decider(), EvaluationModel([], [{"verdict": "pass", "reason": "Compatible."}] * 2), 0.6)
    assert all(row["classification_correct"] and row["mechanics_unchanged"] for row in rows)
    assert next(row for row in rows if row["scenario"] == "clouds_again")["continuity_same_fact_ids"]
    summary = _summary(rows)
    assert summary["service_errors"] == 0 and summary["human_reviewed_lines"] == 0
    assert summary["sensible_answer_rate"] is None and summary["contradictions"] is None
    assert "clouds_again" in capsys.readouterr().out


def test_live_evaluator_checks_local_service_before_any_paid_jev_request(tmp_path, monkeypatch):
    from convgame.evaluate_observations import main
    output = tmp_path / "evaluation.json"
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-only")
    monkeypatch.setattr("sys.argv", ["evaluate_observations", "--output", str(output),
                                    "--log-file", str(tmp_path / "evaluation.log")])
    with patch("convgame.evaluate_observations.BonsaiNarrator.check", side_effect=TimeoutError()), \
            patch("convgame.jev.JevDecider") as jev:
        assert main() == 1
    jev.assert_not_called()
    report = json.loads(output.read_text())
    assert report["blocked_by"] == "TimeoutError" and report["summary"]["evaluated_lines"] == 0
