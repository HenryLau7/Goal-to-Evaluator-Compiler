"""Stable schemas for the Goal-to-Evaluator Compiler.

These are the portable contracts that define the system's inputs and outputs.
Every component — compiler, elicitor, judge — communicates through these schemas.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Input contracts
# ---------------------------------------------------------------------------


class GoalBundle(BaseModel):
    """Portable input package describing the user's goal and current state."""

    goal: str = Field(description="The user's goal in natural language")
    hard_constraints: list[str] = Field(
        default_factory=list,
        description="Non-negotiable requirements. Violation triggers rollback.",
    )
    soft_preferences: list[str] = Field(
        default_factory=list,
        description="Desired qualities that influence evaluation weight.",
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary context the host provides (domain, files, metadata).",
    )
    blessed_state: dict[str, Any] | None = Field(
        default=None,
        description="The last-known-good state. None on first iteration.",
    )
    candidate_state: dict[str, Any] | None = Field(
        default=None,
        description="The proposed new state to evaluate.",
    )
    iteration_budget: int | None = Field(
        default=None,
        description="Max iterations before the system should consider stopping.",
    )
    current_iteration: int = Field(
        default=0,
        description="How many iterations have occurred so far.",
    )


# ---------------------------------------------------------------------------
# Preference elicitation
# ---------------------------------------------------------------------------


class ElicitationQuestion(BaseModel):
    """A single high-information tradeoff question."""

    id: str
    question: str
    options: list[str] = Field(
        default_factory=list,
        description="If non-empty, the user should choose from these.",
    )
    maps_to: str = Field(
        description="Which evaluation dimension this answer influences "
        "(e.g. 'weight:performance', 'critical_failure:data_loss', 'stop_condition').",
    )


class PreferenceAnswer(BaseModel):
    """A user's answer to one elicitation question."""

    question_id: str
    answer: str


class PreferenceProfile(BaseModel):
    """Structured preference profile compiled from elicitation answers.

    This is not free-text notes — each field directly parameterizes the EvalSpec.
    """

    outcome_priorities: list[str] = Field(
        default_factory=list,
        description="Ordered list of what matters most to the user.",
    )
    unacceptable_outcomes: list[str] = Field(
        default_factory=list,
        description="Outcomes the user considers critical failures.",
    )
    tradeoff_tolerances: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of dimension to tolerance level.",
    )
    stopping_threshold: str = Field(
        default="good_enough",
        description="When the user considers the goal sufficiently achieved.",
    )
    exploration_bias: str = Field(
        default="balanced",
        description="'conservative', 'balanced', or 'aggressive' — how much risk to take.",
    )


# ---------------------------------------------------------------------------
# Evaluation contract
# ---------------------------------------------------------------------------


class EvalCriterion(BaseModel):
    """A single evaluation criterion with weight and evidence requirement."""

    name: str
    description: str
    weight: float = Field(ge=0.0, le=1.0, description="Relative importance 0-1.")
    evidence: str = Field(
        description="What evidence the judge should look for to score this."
    )
    evidence_keys: list[str] = Field(
        default_factory=list,
        description="State dict keys the judge should inspect for this criterion.",
    )
    higher_is_better: bool = Field(
        default=True,
        description="If True, higher numeric values = better. If False, lower = better.",
    )


class FailureCondition(BaseModel):
    """A condition that, if met, triggers rollback regardless of other scores."""

    name: str
    description: str
    evidence: str = Field(
        description="What evidence indicates this failure occurred."
    )


class EvalSpec(BaseModel):
    """Structured evaluation contract produced by the compiler.

    This is the central artifact: it defines what success, failure, and drift mean
    for a specific goal, and how decisions should be made.
    """

    goal_summary: str = Field(description="Concise restatement of the goal.")
    success_criteria: list[EvalCriterion] = Field(
        description="Weighted criteria for evaluating progress."
    )
    failure_conditions: list[FailureCondition] = Field(
        description="Hard-fail conditions that trigger rollback."
    )
    drift_anchors: list[str] = Field(
        description="Questions the judge must answer to detect drift."
    )
    accept_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Weighted score above which candidate can be accepted.",
    )
    stop_threshold: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Weighted score above which further iteration is unnecessary.",
    )
    rollback_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Weighted score below which candidate should be rolled back.",
    )


# ---------------------------------------------------------------------------
# Evaluation output
# ---------------------------------------------------------------------------


class CriterionScore(BaseModel):
    """Score for a single evaluation criterion."""

    criterion_name: str
    score: float = Field(ge=0.0, le=1.0, description="0 = not met, 1 = fully met.")
    evidence_found: str
    reasoning: str


class DriftAssessment(BaseModel):
    """Answer to one drift-anchor question."""

    anchor: str
    answer: str
    drift_detected: bool


class EvalReport(BaseModel):
    """Structured evaluation of candidate state against blessed state."""

    criterion_scores: list[CriterionScore]
    failure_violations: list[str] = Field(
        default_factory=list,
        description="Names of failure conditions that were triggered.",
    )
    drift_assessments: list[DriftAssessment] = Field(default_factory=list)
    weighted_score: float = Field(
        ge=0.0, le=1.0, description="Overall weighted score."
    )
    summary: str = Field(description="Human-readable evaluation summary.")


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


class DecisionVerdict(str, Enum):
    """Exactly one of four possible decisions."""

    ACCEPT_AS_BLESSED = "accept_as_blessed"
    CONTINUE = "continue"
    ROLLBACK = "rollback"
    STOP = "stop"


class Decision(BaseModel):
    """Machine-readable action recommendation."""

    verdict: DecisionVerdict
    reasoning: str
    confidence: float = Field(
        ge=0.0, le=1.0, description="How confident the judge is in this decision."
    )
    next_hypothesis: str | None = Field(
        default=None,
        description="If verdict is 'continue', what to try next.",
    )
