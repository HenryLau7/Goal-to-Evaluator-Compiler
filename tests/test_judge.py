"""Tests for the Judge — evaluation and decision logic."""

from core.compiler import Compiler
from core.judge import Judge
from core.schemas import (
    DecisionVerdict,
    EvalCriterion,
    EvalSpec,
    FailureCondition,
    GoalBundle,
)


def _make_spec(**overrides):
    """Helper to create a minimal EvalSpec."""
    defaults = dict(
        goal_summary="test goal",
        success_criteria=[
            EvalCriterion(
                name="quality",
                description="overall quality",
                weight=1.0,
                evidence="check quality key",
                evidence_keys=["quality"],
            )
        ],
        failure_conditions=[],
        drift_anchors=["Is this still aligned?"],
    )
    defaults.update(overrides)
    return EvalSpec(**defaults)


def test_accept_as_blessed():
    spec = _make_spec(accept_threshold=0.7, stop_threshold=0.95)
    bundle = GoalBundle(
        goal="improve quality",
        blessed_state={"quality": 5},
        candidate_state={"quality": 7},
    )
    judge = Judge()
    report, decision = judge.evaluate(spec, bundle)

    assert report.weighted_score >= spec.accept_threshold
    assert report.weighted_score < spec.stop_threshold
    assert decision.verdict == DecisionVerdict.ACCEPT_AS_BLESSED


def test_rollback_on_failure():
    spec = _make_spec(
        failure_conditions=[
            FailureCondition(
                name="tests_must_pass",
                description="All tests must pass",
                evidence="check test results",
            )
        ]
    )
    bundle = GoalBundle(
        goal="refactor",
        blessed_state={"quality": 5},
        candidate_state={
            "quality": 8,
            "failures": ["tests_must_pass"],
        },
    )
    judge = Judge()
    report, decision = judge.evaluate(spec, bundle)

    assert decision.verdict == DecisionVerdict.ROLLBACK
    assert "tests_must_pass" in report.failure_violations


def test_rollback_on_low_score():
    spec = _make_spec(rollback_threshold=0.3)
    bundle = GoalBundle(
        goal="improve quality",
        blessed_state={"quality": 10},
        candidate_state={"quality": 1},
    )
    judge = Judge()
    report, decision = judge.evaluate(spec, bundle)

    assert report.weighted_score < 0.3
    assert decision.verdict == DecisionVerdict.ROLLBACK


def test_continue_on_moderate_score():
    spec = _make_spec(accept_threshold=0.8, rollback_threshold=0.3)
    bundle = GoalBundle(
        goal="improve quality",
        blessed_state={"quality": 10},
        candidate_state={"quality": 8},
    )
    judge = Judge()
    report, decision = judge.evaluate(spec, bundle)

    assert 0.3 <= report.weighted_score < 0.8
    assert decision.verdict == DecisionVerdict.CONTINUE


def test_stop_on_high_score():
    spec = _make_spec(stop_threshold=0.85)
    bundle = GoalBundle(
        goal="improve quality",
        blessed_state={"quality": 5},
        candidate_state={"quality": 15},
    )
    judge = Judge()
    report, decision = judge.evaluate(spec, bundle)

    assert report.weighted_score >= 0.85
    assert decision.verdict == DecisionVerdict.STOP


def test_stop_on_budget_exhaustion():
    spec = _make_spec()
    bundle = GoalBundle(
        goal="improve quality",
        blessed_state={"quality": 10},
        candidate_state={"quality": 8},
        iteration_budget=5,
        current_iteration=5,
    )
    judge = Judge()
    report, decision = judge.evaluate(spec, bundle)

    assert decision.verdict == DecisionVerdict.STOP
    assert "budget" in decision.reasoning.lower()


def test_lower_is_better_scoring():
    spec = _make_spec(
        success_criteria=[
            EvalCriterion(
                name="latency",
                description="lower is better",
                weight=1.0,
                evidence="check latency",
                evidence_keys=["latency_ms"],
                higher_is_better=False,
            )
        ]
    )
    bundle = GoalBundle(
        goal="reduce latency",
        blessed_state={"latency_ms": 500},
        candidate_state={"latency_ms": 200},
    )
    judge = Judge()
    report, decision = judge.evaluate(spec, bundle)

    # 500/200 = 2.5 ratio, should score high
    assert report.weighted_score > 0.8


def test_drift_detection():
    spec = _make_spec(
        drift_anchors=["Did complexity increase without proportional value?"]
    )
    bundle = GoalBundle(
        goal="simple refactor",
        blessed_state={"quality": 5, "complexity": 3},
        candidate_state={"quality": 6, "complexity": 10},
    )
    judge = Judge()
    report, _ = judge.evaluate(spec, bundle)

    drift_items = [d for d in report.drift_assessments if d.drift_detected]
    assert len(drift_items) > 0


def test_no_candidate_state():
    """Judge should handle missing candidate gracefully."""
    spec = _make_spec()
    bundle = GoalBundle(goal="test", blessed_state={"quality": 5})
    judge = Judge()
    report, decision = judge.evaluate(spec, bundle)

    assert report.weighted_score == 0.0


def test_multiple_criteria_weighted_average():
    spec = _make_spec(
        success_criteria=[
            EvalCriterion(
                name="speed",
                description="fast",
                weight=0.8,
                evidence="check speed",
                evidence_keys=["speed"],
            ),
            EvalCriterion(
                name="accuracy",
                description="correct",
                weight=0.2,
                evidence="check accuracy",
                evidence_keys=["accuracy"],
            ),
        ]
    )
    bundle = GoalBundle(
        goal="test",
        blessed_state={"speed": 5, "accuracy": 5},
        candidate_state={"speed": 10, "accuracy": 5},
    )
    judge = Judge()
    report, _ = judge.evaluate(spec, bundle)

    # Speed should score high (ratio 2.0), accuracy should score 0.7 (same)
    # Weighted: (high * 0.8 + 0.7 * 0.2) / 1.0
    assert report.weighted_score > 0.7
