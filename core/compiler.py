"""Compiler: transforms GoalBundle + optional PreferenceProfile into EvalSpec.

The compiler is the bridge between "what the user wants" and "how to evaluate progress."
It does not execute work — it produces a contract that a judge can use.

This is a rule-based compiler that works with structured goals. For truly open-ended
natural language goals, an LLM-backed compiler can extend this by overriding compile().
"""

from core.schemas import (
    EvalCriterion,
    EvalSpec,
    FailureCondition,
    GoalBundle,
    PreferenceProfile,
)

# Standard drift anchors that every evaluation should include.
DEFAULT_DRIFT_ANCHORS = [
    "Which original user goal does this change serve?",
    "What concrete evidence shows this is a real improvement?",
    "Did complexity increase without proportional value?",
    "Would a realistic user accept this as progress?",
    "Are we optimizing a proxy that no longer reflects the original intent?",
]

# Exploration bias → threshold adjustments
_BIAS_ADJUSTMENTS: dict[str, dict[str, float]] = {
    "conservative": {"accept": 0.80, "stop": 0.95, "rollback": 0.40},
    "balanced": {"accept": 0.70, "stop": 0.90, "rollback": 0.30},
    "aggressive": {"accept": 0.55, "stop": 0.85, "rollback": 0.20},
}

# Stopping threshold → stop_threshold adjustments
_STOP_ADJUSTMENTS: dict[str, float] = {
    "perfect": 0.98,
    "very_high": 0.95,
    "good_enough": 0.90,
    "minimum_viable": 0.80,
}


class Compiler:
    """Compiles a GoalBundle into an EvalSpec.

    Usage:
        compiler = Compiler()
        spec = compiler.compile(bundle, preference_profile=profile)
    """

    def compile(
        self,
        bundle: GoalBundle,
        preference_profile: PreferenceProfile | None = None,
    ) -> EvalSpec:
        profile = preference_profile or PreferenceProfile()

        success_criteria = self._build_success_criteria(bundle, profile)
        failure_conditions = self._build_failure_conditions(bundle, profile)
        thresholds = self._compute_thresholds(profile)

        return EvalSpec(
            goal_summary=bundle.goal,
            success_criteria=success_criteria,
            failure_conditions=failure_conditions,
            drift_anchors=list(DEFAULT_DRIFT_ANCHORS),
            accept_threshold=thresholds["accept"],
            stop_threshold=thresholds["stop"],
            rollback_threshold=thresholds["rollback"],
        )

    def _build_success_criteria(
        self, bundle: GoalBundle, profile: PreferenceProfile
    ) -> list[EvalCriterion]:
        criteria: list[EvalCriterion] = []
        state_keys = self._collect_state_keys(bundle)

        # If the profile has explicit outcome priorities, use them with descending weight
        if profile.outcome_priorities:
            n = len(profile.outcome_priorities)
            for i, priority in enumerate(profile.outcome_priorities):
                weight = round(1.0 - (i * 0.6 / max(n - 1, 1)), 2)
                criteria.append(
                    EvalCriterion(
                        name=priority,
                        description=f"Progress toward: {priority}",
                        weight=weight,
                        evidence=f"Observable improvement in {priority} relative to blessed state.",
                        evidence_keys=self._match_keys(priority, state_keys),
                        higher_is_better=self._infer_direction(priority),
                    )
                )

        # Soft preferences become lower-weight criteria
        existing_names = {c.name for c in criteria}
        for pref in bundle.soft_preferences:
            if pref not in existing_names:
                criteria.append(
                    EvalCriterion(
                        name=pref,
                        description=f"Soft preference: {pref}",
                        weight=0.4,
                        evidence=f"Evidence that '{pref}' is satisfied or improved.",
                        evidence_keys=self._match_keys(pref, state_keys),
                        higher_is_better=self._infer_direction(pref),
                    )
                )

        # If no criteria were produced, create a default goal-alignment criterion
        if not criteria:
            criteria.append(
                EvalCriterion(
                    name="goal_alignment",
                    description=f"Overall alignment with: {bundle.goal}",
                    weight=1.0,
                    evidence="Direct evidence that the candidate state advances the stated goal.",
                    evidence_keys=list(state_keys),
                )
            )

        return criteria

    @staticmethod
    def _infer_direction(text: str) -> bool:
        """Infer whether higher is better from criterion text.

        Returns False if the text suggests minimization (reduce, minimize, lower, etc.).
        """
        lower = text.lower()
        minimize_signals = ["reduce", "minimize", "lower", "decrease", "less", "fewer", "shrink", "cut"]
        for signal in minimize_signals:
            if signal in lower:
                return False
        return True

    def _collect_state_keys(self, bundle: GoalBundle) -> set[str]:
        """Gather all keys from blessed and candidate states."""
        keys: set[str] = set()
        if bundle.blessed_state:
            keys.update(bundle.blessed_state.keys())
        if bundle.candidate_state:
            keys.update(bundle.candidate_state.keys())
        return keys

    def _match_keys(self, criterion_text: str, state_keys: set[str]) -> list[str]:
        """Find state keys that are relevant to a criterion description.

        Uses word overlap between the criterion text and state key names.
        """
        criterion_words = set(
            criterion_text.lower().replace("-", "_").replace("/", " ").split()
        )
        # Remove common stopwords
        criterion_words -= {"the", "a", "an", "is", "of", "to", "in", "for", "and", "or", "not", "with", "below", "above", "must", "should"}

        matched = []
        for key in state_keys:
            key_words = set(key.lower().replace("_", " ").replace("-", " ").split())
            overlap = criterion_words & key_words
            if overlap:
                matched.append(key)
        return matched

    def _build_failure_conditions(
        self, bundle: GoalBundle, profile: PreferenceProfile
    ) -> list[FailureCondition]:
        conditions: list[FailureCondition] = []

        # Hard constraints → failure conditions
        for constraint in bundle.hard_constraints:
            conditions.append(
                FailureCondition(
                    name=f"constraint_violation:{constraint[:50]}",
                    description=f"Hard constraint violated: {constraint}",
                    evidence=f"Evidence that '{constraint}' has been violated.",
                )
            )

        # Unacceptable outcomes from preference profile → failure conditions
        for outcome in profile.unacceptable_outcomes:
            conditions.append(
                FailureCondition(
                    name=f"unacceptable:{outcome[:50]}",
                    description=f"Unacceptable outcome detected: {outcome}",
                    evidence=f"Evidence that '{outcome}' has occurred.",
                )
            )

        return conditions

    def _compute_thresholds(
        self, profile: PreferenceProfile
    ) -> dict[str, float]:
        # Start from exploration bias
        bias = profile.exploration_bias
        base = _BIAS_ADJUSTMENTS.get(bias, _BIAS_ADJUSTMENTS["balanced"]).copy()

        # Adjust stop threshold based on stopping_threshold preference
        if profile.stopping_threshold in _STOP_ADJUSTMENTS:
            base["stop"] = _STOP_ADJUSTMENTS[profile.stopping_threshold]

        return base
