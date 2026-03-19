"""Tests for core schemas — validates contract structure and serialization."""

from core.schemas import (
    CriterionScore,
    Decision,
    DecisionVerdict,
    DriftAssessment,
    EvalCriterion,
    EvalReport,
    EvalSpec,
    FailureCondition,
    GoalBundle,
    PreferenceAnswer,
    PreferenceProfile,
    ElicitationQuestion,
)


def test_goal_bundle_minimal():
    bundle = GoalBundle(goal="Do something")
    assert bundle.goal == "Do something"
    assert bundle.hard_constraints == []
    assert bundle.soft_preferences == []
    assert bundle.blessed_state is None
    assert bundle.candidate_state is None
    assert bundle.iteration_budget is None
    assert bundle.current_iteration == 0


def test_goal_bundle_full():
    bundle = GoalBundle(
        goal="Improve performance",
        hard_constraints=["no regressions"],
        soft_preferences=["faster queries"],
        context={"db": "postgres"},
        blessed_state={"latency": 100},
        candidate_state={"latency": 80},
        iteration_budget=5,
        current_iteration=2,
    )
    assert len(bundle.hard_constraints) == 1
    assert bundle.context["db"] == "postgres"
    assert bundle.iteration_budget == 5


def test_preference_profile_defaults():
    profile = PreferenceProfile()
    assert profile.stopping_threshold == "good_enough"
    assert profile.exploration_bias == "balanced"
    assert profile.outcome_priorities == []


def test_eval_spec_thresholds():
    spec = EvalSpec(
        goal_summary="test",
        success_criteria=[
            EvalCriterion(
                name="x", description="x", weight=1.0, evidence="x"
            )
        ],
        failure_conditions=[],
        drift_anchors=["anchor1"],
    )
    assert spec.accept_threshold == 0.7
    assert spec.stop_threshold == 0.9
    assert spec.rollback_threshold == 0.3


def test_decision_verdicts():
    assert DecisionVerdict.ACCEPT_AS_BLESSED.value == "accept_as_blessed"
    assert DecisionVerdict.CONTINUE.value == "continue"
    assert DecisionVerdict.ROLLBACK.value == "rollback"
    assert DecisionVerdict.STOP.value == "stop"


def test_eval_report_serialization():
    report = EvalReport(
        criterion_scores=[
            CriterionScore(
                criterion_name="x",
                score=0.8,
                evidence_found="found",
                reasoning="good",
            )
        ],
        weighted_score=0.8,
        summary="OK",
    )
    data = report.model_dump()
    assert data["weighted_score"] == 0.8
    assert len(data["criterion_scores"]) == 1


def test_decision_serialization():
    decision = Decision(
        verdict=DecisionVerdict.ACCEPT_AS_BLESSED,
        reasoning="Good enough",
        confidence=0.9,
    )
    data = decision.model_dump()
    assert data["verdict"] == "accept_as_blessed"
    assert data["next_hypothesis"] is None


def test_elicitation_question():
    q = ElicitationQuestion(
        id="q1",
        question="What matters?",
        options=["a", "b"],
        maps_to="weight:x",
    )
    assert q.id == "q1"
    assert len(q.options) == 2


def test_eval_criterion_direction():
    c = EvalCriterion(
        name="latency",
        description="lower is better",
        weight=0.8,
        evidence="check latency",
        higher_is_better=False,
    )
    assert c.higher_is_better is False

    c2 = EvalCriterion(
        name="throughput",
        description="higher is better",
        weight=0.8,
        evidence="check throughput",
    )
    assert c2.higher_is_better is True
