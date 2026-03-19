"""Judge: evaluates candidate state against blessed state using an EvalSpec.

The judge is the runtime evaluation engine. Given an EvalSpec (the contract),
a candidate state, and a blessed state, it produces an EvalReport and a Decision.

This implementation provides a rule-based judge that works with structured states
(dicts with comparable values). For complex domains, extend Judge and override
the scoring methods.
"""

from typing import Any

from core.schemas import (
    CriterionScore,
    Decision,
    DecisionVerdict,
    DriftAssessment,
    EvalReport,
    EvalSpec,
    GoalBundle,
)


class Judge:
    """Evaluates candidate state against blessed state per an EvalSpec.

    The default implementation scores structured dict states by checking
    for the presence and quality of evidence fields. Override score_criterion()
    and check_failure() for domain-specific logic.

    Usage:
        judge = Judge()
        report, decision = judge.evaluate(spec, bundle)
    """

    def evaluate(
        self,
        spec: EvalSpec,
        bundle: GoalBundle,
    ) -> tuple[EvalReport, Decision]:
        """Run full evaluation and produce report + decision."""
        candidate = bundle.candidate_state or {}
        blessed = bundle.blessed_state

        # Score each criterion
        criterion_scores = [
            self.score_criterion(criterion, candidate, blessed)
            for criterion in spec.success_criteria
        ]

        # Check failure conditions
        failure_violations = [
            fc.name
            for fc in spec.failure_conditions
            if self.check_failure(fc.name, fc.description, candidate, blessed)
        ]

        # Assess drift
        drift_assessments = [
            self.assess_drift(anchor, candidate, blessed, spec)
            for anchor in spec.drift_anchors
        ]

        # Compute weighted score
        weighted_score = self._compute_weighted_score(
            criterion_scores, spec.success_criteria
        )

        # Build report
        report = EvalReport(
            criterion_scores=criterion_scores,
            failure_violations=failure_violations,
            drift_assessments=drift_assessments,
            weighted_score=weighted_score,
            summary=self._build_summary(
                criterion_scores, failure_violations, drift_assessments, weighted_score
            ),
        )

        # Make decision
        decision = self._decide(report, spec, bundle)

        return report, decision

    def score_criterion(
        self,
        criterion: Any,
        candidate: dict[str, Any],
        blessed: dict[str, Any] | None,
    ) -> CriterionScore:
        """Score a single criterion by examining candidate vs blessed state.

        Uses evidence_keys (if provided by the compiler) to find relevant state
        values, falling back to name-based matching. When multiple evidence keys
        match, scores are averaged.
        """
        name = criterion.name
        evidence_keys = getattr(criterion, "evidence_keys", []) or []
        higher_is_better = getattr(criterion, "higher_is_better", True)

        # Collect all evidence pairs (candidate_val, blessed_val)
        pairs = []
        for key in evidence_keys:
            c_val = candidate.get(key)
            b_val = (blessed or {}).get(key)
            if c_val is not None:
                pairs.append((key, c_val, b_val))

        # Fall back to name-based matching if no evidence_keys matched
        if not pairs:
            c_val = self._find_evidence(name, candidate)
            b_val = self._find_evidence(name, blessed) if blessed else None
            if c_val is not None:
                pairs.append((name, c_val, b_val))

        if pairs:
            scores = []
            evidence_parts = []
            reasoning_parts = []
            for key, c_val, b_val in pairs:
                if b_val is not None:
                    s = self._compare_values(c_val, b_val, higher_is_better)
                    reasoning_parts.append(f"{key}: {c_val} (was {b_val})")
                else:
                    s = 0.7
                    reasoning_parts.append(f"{key}: {c_val} (no baseline)")
                scores.append(s)
                evidence_parts.append(f"{key}={c_val}")

            avg_score = sum(scores) / len(scores)
            return CriterionScore(
                criterion_name=name,
                score=round(avg_score, 4),
                evidence_found="; ".join(evidence_parts),
                reasoning="; ".join(reasoning_parts),
            )
        else:
            return CriterionScore(
                criterion_name=name,
                score=0.0,
                evidence_found="No evidence found in candidate state.",
                reasoning=f"No evidence of '{name}' found in candidate state.",
            )

    def check_failure(
        self,
        name: str,
        description: str,
        candidate: dict[str, Any],
        blessed: dict[str, Any] | None,
    ) -> bool:
        """Check if a failure condition is triggered.

        Default: looks for explicit failure markers in candidate state.
        A key named 'failures' or 'errors' containing the condition name triggers it.
        Override for domain-specific failure detection.
        """
        # Check explicit failure markers
        failures = candidate.get("failures", [])
        if isinstance(failures, list):
            for f in failures:
                if isinstance(f, str) and (name in f or f in name or f in description):
                    return True

        errors = candidate.get("errors", [])
        if isinstance(errors, list):
            for e in errors:
                if isinstance(e, str) and (name in e or e in name or e in description):
                    return True

        # Check for violated_constraints marker
        violated = candidate.get("violated_constraints", [])
        if isinstance(violated, list):
            for v in violated:
                if isinstance(v, str) and (v in name or v in description or name in v):
                    return True

        return False

    def assess_drift(
        self,
        anchor: str,
        candidate: dict[str, Any],
        blessed: dict[str, Any] | None,
        spec: EvalSpec,
    ) -> DriftAssessment:
        """Assess whether drift has occurred for a given anchor question.

        Default: checks for complexity increase and goal alignment signals.
        Override for domain-specific drift detection.
        """
        drift_detected = False
        answer = "No drift signals detected."

        # Check if complexity increased disproportionately
        if "complexity" in anchor.lower():
            c_complexity = candidate.get("complexity", 0)
            b_complexity = (blessed or {}).get("complexity", 0)
            if isinstance(c_complexity, (int, float)) and isinstance(
                b_complexity, (int, float)
            ):
                if c_complexity > b_complexity * 1.5 and c_complexity > b_complexity + 2:
                    drift_detected = True
                    answer = (
                        f"Complexity increased from {b_complexity} to {c_complexity} "
                        "without clear proportional value."
                    )

        # Check for explicit drift markers
        if candidate.get("drift_detected", False):
            drift_detected = True
            answer = "Explicit drift marker found in candidate state."

        return DriftAssessment(
            anchor=anchor, answer=answer, drift_detected=drift_detected
        )

    def _find_evidence(
        self, criterion_name: str, state: dict[str, Any]
    ) -> Any | None:
        """Look for evidence of a criterion in a state dict.

        Tries exact key match, then normalized key match.
        """
        if criterion_name in state:
            return state[criterion_name]

        normalized = criterion_name.lower().replace(" ", "_").replace("-", "_")
        for key, value in state.items():
            if key.lower().replace(" ", "_").replace("-", "_") == normalized:
                return value

        return None

    def _compare_values(
        self,
        candidate_val: Any,
        blessed_val: Any,
        higher_is_better: bool = True,
    ) -> float:
        """Compare candidate value to blessed value, returning a score 0-1.

        For numeric values: ratio-based comparison respecting direction.
        For booleans: binary.
        For strings: equality check.
        For other types: presence check.
        """
        if isinstance(candidate_val, bool) and isinstance(blessed_val, bool):
            return 1.0 if candidate_val == blessed_val or candidate_val else 0.5

        if isinstance(candidate_val, (int, float)) and isinstance(
            blessed_val, (int, float)
        ):
            if blessed_val == 0:
                return 0.8 if candidate_val > 0 else 0.5

            # For lower-is-better metrics, invert the ratio
            if higher_is_better:
                ratio = candidate_val / blessed_val
            else:
                ratio = blessed_val / candidate_val

            if ratio >= 1.0:
                return min(1.0, 0.7 + 0.3 * min(ratio, 2.0) / 2.0)
            else:
                return max(0.0, ratio * 0.7)

        if isinstance(candidate_val, str) and isinstance(blessed_val, str):
            if candidate_val == blessed_val:
                return 0.7  # Same as before, no improvement
            return 0.5  # Different, can't tell if better

        return 0.6  # Present but incomparable

    def _compute_weighted_score(
        self,
        scores: list[CriterionScore],
        criteria: list[Any],
    ) -> float:
        """Compute weighted average score."""
        if not scores:
            return 0.0

        criteria_map = {c.name: c.weight for c in criteria}
        total_weight = sum(criteria_map.get(s.criterion_name, 0.5) for s in scores)

        if total_weight == 0:
            return 0.0

        weighted_sum = sum(
            s.score * criteria_map.get(s.criterion_name, 0.5) for s in scores
        )
        return round(weighted_sum / total_weight, 4)

    def _decide(
        self,
        report: EvalReport,
        spec: EvalSpec,
        bundle: GoalBundle,
    ) -> Decision:
        """Apply decision policy to produce a verdict."""
        # Rule 1: Any failure violation → rollback
        if report.failure_violations:
            return Decision(
                verdict=DecisionVerdict.ROLLBACK,
                reasoning=(
                    f"Critical failure conditions triggered: "
                    f"{', '.join(report.failure_violations)}"
                ),
                confidence=0.95,
            )

        # Rule 2: Significant drift detected → rollback
        drift_count = sum(1 for d in report.drift_assessments if d.drift_detected)
        if drift_count >= 2:
            return Decision(
                verdict=DecisionVerdict.ROLLBACK,
                reasoning=f"Drift detected on {drift_count} anchors — candidate has diverged from goal.",
                confidence=0.8,
            )

        # Rule 3: Score above stop threshold → stop
        if report.weighted_score >= spec.stop_threshold:
            return Decision(
                verdict=DecisionVerdict.STOP,
                reasoning=(
                    f"Score {report.weighted_score:.2f} meets or exceeds stop threshold "
                    f"{spec.stop_threshold:.2f}. Goal sufficiently achieved."
                ),
                confidence=0.9,
            )

        # Rule 4: Score above accept threshold → accept_as_blessed
        if report.weighted_score >= spec.accept_threshold:
            return Decision(
                verdict=DecisionVerdict.ACCEPT_AS_BLESSED,
                reasoning=(
                    f"Score {report.weighted_score:.2f} exceeds accept threshold "
                    f"{spec.accept_threshold:.2f}. Candidate is meaningfully better."
                ),
                confidence=0.8,
                next_hypothesis="Continue improving from this new baseline.",
            )

        # Rule 5: Score below rollback threshold → rollback
        if report.weighted_score < spec.rollback_threshold:
            return Decision(
                verdict=DecisionVerdict.ROLLBACK,
                reasoning=(
                    f"Score {report.weighted_score:.2f} is below rollback threshold "
                    f"{spec.rollback_threshold:.2f}. Candidate is materially worse."
                ),
                confidence=0.85,
            )

        # Rule 6: Budget exhausted → stop
        if (
            bundle.iteration_budget is not None
            and bundle.current_iteration >= bundle.iteration_budget
        ):
            return Decision(
                verdict=DecisionVerdict.STOP,
                reasoning=(
                    f"Iteration budget ({bundle.iteration_budget}) exhausted. "
                    f"Current score: {report.weighted_score:.2f}."
                ),
                confidence=0.7,
            )

        # Rule 7: Otherwise → continue
        return Decision(
            verdict=DecisionVerdict.CONTINUE,
            reasoning=(
                f"Score {report.weighted_score:.2f} is between rollback "
                f"({spec.rollback_threshold:.2f}) and accept ({spec.accept_threshold:.2f}). "
                "Iteration may improve the candidate."
            ),
            confidence=0.6,
            next_hypothesis="Address the lowest-scoring criteria to improve overall score.",
        )

    def _build_summary(
        self,
        scores: list[CriterionScore],
        failures: list[str],
        drift: list[DriftAssessment],
        weighted_score: float,
    ) -> str:
        parts = [f"Weighted score: {weighted_score:.2f}."]

        if failures:
            parts.append(f"FAILURES: {', '.join(failures)}.")

        drift_issues = [d for d in drift if d.drift_detected]
        if drift_issues:
            parts.append(f"Drift detected on {len(drift_issues)} anchor(s).")

        low_scores = [s for s in scores if s.score < 0.4]
        if low_scores:
            names = ", ".join(s.criterion_name for s in low_scores)
            parts.append(f"Low-scoring criteria: {names}.")

        high_scores = [s for s in scores if s.score >= 0.8]
        if high_scores:
            names = ", ".join(s.criterion_name for s in high_scores)
            parts.append(f"Strong criteria: {names}.")

        return " ".join(parts)
