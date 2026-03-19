"""Preference Elicitor: detects ambiguous goals and generates targeted questions.

When a user's goal is underspecified, the system must not pretend a stable evaluator
exists. Instead, it generates a small number of high-information tradeoff questions
whose answers directly parameterize the evaluation contract.

This is not a generic questionnaire — each question maps to a specific evaluation
dimension, weight, critical failure, or stop condition.
"""

from core.schemas import (
    ElicitationQuestion,
    GoalBundle,
    PreferenceAnswer,
    PreferenceProfile,
)


class Elicitor:
    """Generates preference-elicitation questions and compiles answers into profiles.

    Usage:
        elicitor = Elicitor()
        if elicitor.needs_elicitation(bundle):
            questions = elicitor.generate_questions(bundle)
            # present questions to user, collect answers
            profile = elicitor.compile_profile(answers)
    """

    def needs_elicitation(self, bundle: GoalBundle) -> bool:
        """Determine if the goal is too ambiguous for direct compilation.

        A goal is considered ambiguous when there isn't enough structured
        information to build a meaningful evaluation contract.
        """
        has_constraints = len(bundle.hard_constraints) > 0
        has_preferences = len(bundle.soft_preferences) > 0

        # If the goal has both constraints and preferences, it's likely specific enough
        if has_constraints and has_preferences:
            return False

        # Short goals with no structure are almost certainly ambiguous
        word_count = len(bundle.goal.split())
        if word_count < 10 and not has_constraints:
            return True

        # Goals with no constraints and no preferences need elicitation
        if not has_constraints and not has_preferences:
            return True

        return False

    def generate_questions(self, bundle: GoalBundle) -> list[ElicitationQuestion]:
        """Generate 5-8 targeted tradeoff questions based on the goal.

        Each question maps directly to an evaluation parameter.
        """
        questions: list[ElicitationQuestion] = []

        # Q1: Outcome priority — what matters most?
        questions.append(
            ElicitationQuestion(
                id="outcome_priority",
                question=(
                    f"For the goal '{bundle.goal}', what are the most important "
                    "outcomes? Rank these or add your own."
                ),
                options=[
                    "Correctness / accuracy",
                    "Speed / performance",
                    "Simplicity / maintainability",
                    "Completeness / coverage",
                    "User experience / polish",
                ],
                maps_to="weight:outcome_priorities",
            )
        )

        # Q2: Unacceptable outcomes — what must never happen?
        questions.append(
            ElicitationQuestion(
                id="unacceptable_outcomes",
                question="What outcomes would be completely unacceptable? (These become hard-fail conditions.)",
                options=[
                    "Data loss or corruption",
                    "Breaking existing functionality",
                    "Security vulnerabilities",
                    "Significant performance degradation",
                    "Loss of backward compatibility",
                ],
                maps_to="critical_failure:unacceptable_outcomes",
            )
        )

        # Q3: Tradeoff — quality vs speed
        questions.append(
            ElicitationQuestion(
                id="tradeoff_quality_speed",
                question="When quality and speed conflict, which do you prefer?",
                options=[
                    "Always prioritize quality, even if it takes much longer",
                    "Lean toward quality, but some shortcuts are acceptable",
                    "Balance both — good enough quality at reasonable speed",
                    "Lean toward speed, accept minor quality compromises",
                ],
                maps_to="weight:tradeoff_tolerances",
            )
        )

        # Q4: Tradeoff — simplicity vs completeness
        questions.append(
            ElicitationQuestion(
                id="tradeoff_simplicity_completeness",
                question="When simplicity and completeness conflict, which do you prefer?",
                options=[
                    "Keep it simple — cover the core case well",
                    "Moderate coverage — handle common edge cases",
                    "Comprehensive — handle most edge cases",
                    "Exhaustive — cover every possible case",
                ],
                maps_to="weight:tradeoff_tolerances",
            )
        )

        # Q5: Stopping threshold — when is it done?
        questions.append(
            ElicitationQuestion(
                id="stopping_threshold",
                question="When would you consider this goal sufficiently achieved?",
                options=[
                    "When it works perfectly with no compromises",
                    "When it works well for the primary use case",
                    "When it's functional and meets the core requirements",
                    "When there's a minimum viable version that proves the concept",
                ],
                maps_to="stop_condition",
            )
        )

        # Q6: Exploration vs conservatism
        questions.append(
            ElicitationQuestion(
                id="exploration_bias",
                question="How much risk should the system take when iterating?",
                options=[
                    "Conservative — only make safe, incremental changes",
                    "Balanced — some experimentation with guardrails",
                    "Aggressive — willing to try bold changes and roll back if needed",
                ],
                maps_to="decision_policy:exploration_bias",
            )
        )

        # Q7: Iteration budget (only if not already set)
        if bundle.iteration_budget is None:
            questions.append(
                ElicitationQuestion(
                    id="iteration_budget",
                    question="How many iteration cycles should the system attempt before stopping?",
                    options=[
                        "1-3 (quick pass)",
                        "5-10 (moderate exploration)",
                        "10-20 (thorough iteration)",
                        "No limit (keep going until done or stuck)",
                    ],
                    maps_to="stop_condition:iteration_budget",
                )
            )

        return questions

    def compile_profile(self, answers: list[PreferenceAnswer]) -> PreferenceProfile:
        """Compile user answers into a structured PreferenceProfile.

        Each answer is mapped to its evaluation parameter.
        """
        profile = PreferenceProfile()
        answer_map = {a.question_id: a.answer for a in answers}

        # Outcome priorities
        if "outcome_priority" in answer_map:
            raw = answer_map["outcome_priority"]
            profile.outcome_priorities = [
                p.strip() for p in raw.split(",") if p.strip()
            ]

        # Unacceptable outcomes
        if "unacceptable_outcomes" in answer_map:
            raw = answer_map["unacceptable_outcomes"]
            profile.unacceptable_outcomes = [
                o.strip() for o in raw.split(",") if o.strip()
            ]

        # Tradeoff: quality vs speed
        if "tradeoff_quality_speed" in answer_map:
            answer = answer_map["tradeoff_quality_speed"].lower()
            if "always prioritize quality" in answer:
                profile.tradeoff_tolerances["quality_vs_speed"] = "no speed compromise"
            elif "lean toward quality" in answer:
                profile.tradeoff_tolerances["quality_vs_speed"] = "minor speed ok"
            elif "lean toward speed" in answer:
                profile.tradeoff_tolerances["quality_vs_speed"] = "minor quality ok"
            else:
                profile.tradeoff_tolerances["quality_vs_speed"] = "balanced"

        # Tradeoff: simplicity vs completeness
        if "tradeoff_simplicity_completeness" in answer_map:
            answer = answer_map["tradeoff_simplicity_completeness"].lower()
            if "simple" in answer:
                profile.tradeoff_tolerances["simplicity_vs_completeness"] = "prefer simple"
            elif "exhaustive" in answer:
                profile.tradeoff_tolerances["simplicity_vs_completeness"] = "prefer exhaustive"
            elif "comprehensive" in answer:
                profile.tradeoff_tolerances["simplicity_vs_completeness"] = "prefer comprehensive"
            else:
                profile.tradeoff_tolerances["simplicity_vs_completeness"] = "moderate"

        # Stopping threshold
        if "stopping_threshold" in answer_map:
            answer = answer_map["stopping_threshold"].lower()
            if "perfectly" in answer:
                profile.stopping_threshold = "perfect"
            elif "works well" in answer:
                profile.stopping_threshold = "very_high"
            elif "functional" in answer or "core requirements" in answer:
                profile.stopping_threshold = "good_enough"
            else:
                profile.stopping_threshold = "minimum_viable"

        # Exploration bias
        if "exploration_bias" in answer_map:
            answer = answer_map["exploration_bias"].lower()
            if "conservative" in answer:
                profile.exploration_bias = "conservative"
            elif "aggressive" in answer:
                profile.exploration_bias = "aggressive"
            else:
                profile.exploration_bias = "balanced"

        return profile
