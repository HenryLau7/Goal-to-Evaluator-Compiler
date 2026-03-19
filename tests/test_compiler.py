"""Tests for the Compiler — GoalBundle + PreferenceProfile → EvalSpec."""

from core.compiler import Compiler
from core.schemas import GoalBundle, PreferenceProfile


def test_compile_clear_goal():
    bundle = GoalBundle(
        goal="Improve API speed",
        hard_constraints=["No breaking changes"],
        soft_preferences=["Lower latency"],
    )
    compiler = Compiler()
    spec = compiler.compile(bundle)

    assert spec.goal_summary == "Improve API speed"
    assert len(spec.success_criteria) == 1  # one soft preference
    assert spec.success_criteria[0].name == "Lower latency"
    assert len(spec.failure_conditions) == 1
    assert "No breaking changes" in spec.failure_conditions[0].description
    assert len(spec.drift_anchors) == 5


def test_compile_with_preference_profile():
    bundle = GoalBundle(goal="Make it better")
    profile = PreferenceProfile(
        outcome_priorities=["speed", "reliability"],
        unacceptable_outcomes=["data loss"],
        exploration_bias="conservative",
        stopping_threshold="very_high",
    )
    compiler = Compiler()
    spec = compiler.compile(bundle, preference_profile=profile)

    assert len(spec.success_criteria) == 2
    assert spec.success_criteria[0].name == "speed"
    assert spec.success_criteria[0].weight > spec.success_criteria[1].weight

    assert len(spec.failure_conditions) == 1
    assert "data loss" in spec.failure_conditions[0].description

    # Conservative bias → higher thresholds
    assert spec.accept_threshold == 0.80
    assert spec.rollback_threshold == 0.40


def test_compile_no_criteria_gets_default():
    bundle = GoalBundle(goal="Do something vague")
    compiler = Compiler()
    spec = compiler.compile(bundle)

    assert len(spec.success_criteria) == 1
    assert spec.success_criteria[0].name == "goal_alignment"
    assert spec.success_criteria[0].weight == 1.0


def test_direction_inference():
    compiler = Compiler()
    assert compiler._infer_direction("Reduce latency") is False
    assert compiler._infer_direction("Minimize errors") is False
    assert compiler._infer_direction("Lower memory usage") is False
    assert compiler._infer_direction("Increase throughput") is True
    assert compiler._infer_direction("Better code quality") is True


def test_evidence_key_matching():
    bundle = GoalBundle(
        goal="Improve performance",
        soft_preferences=["Reduce p95 latency"],
        blessed_state={"p95_latency_ms": 500},
        candidate_state={"p95_latency_ms": 200},
    )
    compiler = Compiler()
    spec = compiler.compile(bundle)

    criterion = spec.success_criteria[0]
    assert "p95_latency_ms" in criterion.evidence_keys
    assert criterion.higher_is_better is False


def test_stop_threshold_adjustment():
    compiler = Compiler()

    profile_perfect = PreferenceProfile(stopping_threshold="perfect")
    spec = compiler.compile(GoalBundle(goal="test"), preference_profile=profile_perfect)
    assert spec.stop_threshold == 0.98

    profile_mvp = PreferenceProfile(stopping_threshold="minimum_viable")
    spec = compiler.compile(GoalBundle(goal="test"), preference_profile=profile_mvp)
    assert spec.stop_threshold == 0.80
