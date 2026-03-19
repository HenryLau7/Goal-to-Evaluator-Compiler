"""Tests for the Elicitor — ambiguity detection and preference compilation."""

from core.elicitor import Elicitor
from core.schemas import GoalBundle, PreferenceAnswer


def test_needs_elicitation_vague_goal():
    elicitor = Elicitor()
    bundle = GoalBundle(goal="Make it better")
    assert elicitor.needs_elicitation(bundle) is True


def test_no_elicitation_for_structured_goal():
    elicitor = Elicitor()
    bundle = GoalBundle(
        goal="Improve API response time",
        hard_constraints=["No breaking changes"],
        soft_preferences=["Lower latency"],
    )
    assert elicitor.needs_elicitation(bundle) is False


def test_needs_elicitation_no_structure():
    elicitor = Elicitor()
    bundle = GoalBundle(goal="A long goal description with many words but no constraints or preferences at all")
    assert elicitor.needs_elicitation(bundle) is True


def test_generate_questions_count():
    elicitor = Elicitor()
    bundle = GoalBundle(goal="Make it better")
    questions = elicitor.generate_questions(bundle)
    # Should generate 6-7 questions (7 if no iteration budget)
    assert 6 <= len(questions) <= 7


def test_generate_questions_with_budget():
    elicitor = Elicitor()
    bundle = GoalBundle(goal="Make it better", iteration_budget=5)
    questions = elicitor.generate_questions(bundle)
    # Should skip iteration_budget question
    assert len(questions) == 6
    assert all(q.id != "iteration_budget" for q in questions)


def test_compile_profile_outcome_priority():
    elicitor = Elicitor()
    answers = [
        PreferenceAnswer(question_id="outcome_priority", answer="speed, reliability"),
    ]
    profile = elicitor.compile_profile(answers)
    assert profile.outcome_priorities == ["speed", "reliability"]


def test_compile_profile_unacceptable():
    elicitor = Elicitor()
    answers = [
        PreferenceAnswer(
            question_id="unacceptable_outcomes",
            answer="Data loss, Security breach",
        ),
    ]
    profile = elicitor.compile_profile(answers)
    assert "Data loss" in profile.unacceptable_outcomes
    assert "Security breach" in profile.unacceptable_outcomes


def test_compile_profile_exploration_bias():
    elicitor = Elicitor()

    for input_text, expected in [
        ("Conservative — safe changes", "conservative"),
        ("Aggressive — bold changes", "aggressive"),
        ("Balanced approach", "balanced"),
    ]:
        answers = [PreferenceAnswer(question_id="exploration_bias", answer=input_text)]
        profile = elicitor.compile_profile(answers)
        assert profile.exploration_bias == expected


def test_compile_profile_stopping_threshold():
    elicitor = Elicitor()

    for input_text, expected in [
        ("When it works perfectly with no compromises", "perfect"),
        ("When it works well for the primary use case", "very_high"),
        ("When it's functional and meets the core requirements", "good_enough"),
        ("minimum viable version", "minimum_viable"),
    ]:
        answers = [PreferenceAnswer(question_id="stopping_threshold", answer=input_text)]
        profile = elicitor.compile_profile(answers)
        assert profile.stopping_threshold == expected, f"Expected {expected} for '{input_text}', got {profile.stopping_threshold}"


def test_question_maps_to_filled():
    elicitor = Elicitor()
    bundle = GoalBundle(goal="Make it better")
    questions = elicitor.generate_questions(bundle)
    for q in questions:
        assert q.maps_to, f"Question {q.id} has no maps_to"
        assert q.question, f"Question {q.id} has no question text"
