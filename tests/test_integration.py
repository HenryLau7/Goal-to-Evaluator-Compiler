"""Integration tests — full end-to-end pipeline flows."""

from core.compiler import Compiler
from core.elicitor import Elicitor
from core.judge import Judge
from core.schemas import (
    DecisionVerdict,
    GoalBundle,
    PreferenceAnswer,
)
from adapters.interactive import InteractiveAdapter


def test_clear_goal_end_to_end():
    """Well-specified goal: compile → judge → accept."""
    bundle = GoalBundle(
        goal="Improve API response time",
        hard_constraints=["No breaking changes", "Tests must pass"],
        soft_preferences=["Reduce latency"],
        blessed_state={"latency_ms": 500, "tests_passing": True},
        candidate_state={"latency_ms": 200, "tests_passing": True},
    )

    compiler = Compiler()
    spec = compiler.compile(bundle)

    judge = Judge()
    report, decision = judge.evaluate(spec, bundle)

    assert decision.verdict in (
        DecisionVerdict.ACCEPT_AS_BLESSED,
        DecisionVerdict.STOP,
    )
    assert len(report.failure_violations) == 0


def test_ambiguous_goal_end_to_end():
    """Vague goal: elicit → compile → verify spec structure."""
    bundle = GoalBundle(goal="Make things better")

    elicitor = Elicitor()
    assert elicitor.needs_elicitation(bundle)

    questions = elicitor.generate_questions(bundle)
    assert len(questions) >= 6

    answers = [
        PreferenceAnswer(question_id="outcome_priority", answer="speed, reliability"),
        PreferenceAnswer(question_id="unacceptable_outcomes", answer="data loss"),
        PreferenceAnswer(
            question_id="tradeoff_quality_speed",
            answer="Balance both — good enough quality at reasonable speed",
        ),
        PreferenceAnswer(
            question_id="tradeoff_simplicity_completeness",
            answer="Moderate coverage — handle common edge cases",
        ),
        PreferenceAnswer(
            question_id="stopping_threshold",
            answer="When it works well for the primary use case",
        ),
        PreferenceAnswer(
            question_id="exploration_bias",
            answer="Balanced — some experimentation with guardrails",
        ),
    ]

    profile = elicitor.compile_profile(answers)
    assert len(profile.outcome_priorities) == 2
    assert "data loss" in profile.unacceptable_outcomes

    compiler = Compiler()
    spec = compiler.compile(bundle, preference_profile=profile)

    assert len(spec.success_criteria) == 2
    assert len(spec.failure_conditions) == 1
    assert spec.stop_threshold == 0.95  # very_high


def test_rollback_end_to_end():
    """Candidate violates constraints: compile → judge → rollback."""
    bundle = GoalBundle(
        goal="Refactor auth module",
        hard_constraints=["All tests must pass"],
        soft_preferences=["Cleaner code"],
        blessed_state={"tests_passing": True, "code_quality": 6},
        candidate_state={
            "tests_passing": False,
            "code_quality": 8,
            "failures": ["All tests must pass"],
        },
    )

    compiler = Compiler()
    spec = compiler.compile(bundle)

    judge = Judge()
    report, decision = judge.evaluate(spec, bundle)

    assert decision.verdict == DecisionVerdict.ROLLBACK
    assert len(report.failure_violations) > 0


def test_interactive_adapter_clear_goal():
    """InteractiveAdapter with a clear goal should skip elicitation."""
    bundle = GoalBundle(
        goal="Improve API response time",
        hard_constraints=["No breaking changes"],
        soft_preferences=["Reduce latency"],
        blessed_state={"latency_ms": 500},
        candidate_state={"latency_ms": 200},
    )

    adapter = InteractiveAdapter()
    result = adapter.run(bundle)

    assert result["elicitation_occurred"] is False
    assert result["eval_spec"] is not None
    assert result["eval_report"] is not None
    assert result["decision"] is not None
    assert result["decision"].verdict in (
        DecisionVerdict.ACCEPT_AS_BLESSED,
        DecisionVerdict.STOP,
    )


def test_interactive_adapter_ambiguous_goal():
    """InteractiveAdapter with ambiguous goal should trigger elicitation."""
    call_log = []

    def mock_handler(question, options):
        call_log.append(question)
        return "Balanced"

    bundle = GoalBundle(goal="Make it better")
    adapter = InteractiveAdapter(question_handler=mock_handler)
    result = adapter.run(bundle)

    assert result["elicitation_occurred"] is True
    assert len(call_log) >= 6
    assert result["preference_profile"] is not None


def test_interactive_adapter_no_candidate():
    """InteractiveAdapter without candidate state should compile but not judge."""
    bundle = GoalBundle(
        goal="Improve API response time",
        hard_constraints=["No breaking changes"],
        soft_preferences=["Reduce latency"],
    )

    adapter = InteractiveAdapter()
    result = adapter.run(bundle)

    assert result["eval_spec"] is not None
    assert result["eval_report"] is None
    assert result["decision"] is None


def test_full_progression_scenario():
    """Simulate a multi-iteration progression: continue → accept → stop."""
    compiler = Compiler()
    judge = Judge()

    bundle = GoalBundle(
        goal="Improve code quality",
        soft_preferences=["Better test coverage"],
        blessed_state={"test_coverage": 40},
        candidate_state={"test_coverage": 50},
    )

    spec = compiler.compile(bundle)

    # Iteration 1: moderate improvement → continue or accept
    report1, decision1 = judge.evaluate(spec, bundle)
    assert decision1.verdict in (
        DecisionVerdict.CONTINUE,
        DecisionVerdict.ACCEPT_AS_BLESSED,
    )

    # Iteration 2: candidate becomes blessed, new candidate is much better
    bundle2 = GoalBundle(
        goal="Improve code quality",
        soft_preferences=["Better test coverage"],
        blessed_state={"test_coverage": 50},
        candidate_state={"test_coverage": 85},
    )
    report2, decision2 = judge.evaluate(spec, bundle2)
    assert decision2.verdict in (
        DecisionVerdict.ACCEPT_AS_BLESSED,
        DecisionVerdict.STOP,
    )
