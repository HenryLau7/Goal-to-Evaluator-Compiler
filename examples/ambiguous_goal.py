"""Example: Ambiguous goal requiring preference elicitation.

Demonstrates the elicitation path — a vague goal that needs structured
preference questions before a stable evaluator can be compiled.
"""

from core import Compiler, Elicitor, GoalBundle

# A vague, ambiguous goal — no constraints, no preferences
bundle = GoalBundle(
    goal="Make the app better",
    context={"app_type": "web application", "team_size": 3},
)

elicitor = Elicitor()

# Step 1: Check if elicitation is needed
needs_elicitation = elicitor.needs_elicitation(bundle)
print(f"Needs elicitation: {needs_elicitation}")

# Step 2: Generate questions
questions = elicitor.generate_questions(bundle)
print(f"\n=== Elicitation Questions ({len(questions)}) ===")
for q in questions:
    print(f"\nQ ({q.id}): {q.question}")
    print(f"  Maps to: {q.maps_to}")
    if q.options:
        for i, opt in enumerate(q.options, 1):
            print(f"  {i}. {opt}")

# Step 3: Simulate user answers
from core.schemas import PreferenceAnswer

simulated_answers = [
    PreferenceAnswer(
        question_id="outcome_priority",
        answer="User experience / polish, Speed / performance",
    ),
    PreferenceAnswer(
        question_id="unacceptable_outcomes",
        answer="Breaking existing functionality, Data loss or corruption",
    ),
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
    PreferenceAnswer(
        question_id="iteration_budget",
        answer="5-10 (moderate exploration)",
    ),
]

# Step 4: Compile answers into a preference profile
profile = elicitor.compile_profile(simulated_answers)

print("\n=== Preference Profile ===")
print(f"Outcome priorities: {profile.outcome_priorities}")
print(f"Unacceptable outcomes: {profile.unacceptable_outcomes}")
print(f"Tradeoff tolerances: {profile.tradeoff_tolerances}")
print(f"Stopping threshold: {profile.stopping_threshold}")
print(f"Exploration bias: {profile.exploration_bias}")

# Step 5: Compile into EvalSpec using the preference profile
compiler = Compiler()
spec = compiler.compile(bundle, preference_profile=profile)

print("\n=== EvalSpec (from ambiguous goal + preferences) ===")
print(f"Goal: {spec.goal_summary}")
print(f"Success criteria: {len(spec.success_criteria)}")
for c in spec.success_criteria:
    print(f"  - {c.name} (weight={c.weight})")
print(f"Failure conditions: {len(spec.failure_conditions)}")
for fc in spec.failure_conditions:
    print(f"  - {fc.name}")
print(f"Thresholds: accept={spec.accept_threshold}, stop={spec.stop_threshold}, rollback={spec.rollback_threshold}")
