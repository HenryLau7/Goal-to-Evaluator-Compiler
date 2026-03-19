"""Example: Clear goal with structured constraints.

Demonstrates the happy path — a well-specified goal that compiles directly
into an EvalSpec without preference elicitation, then gets judged.
"""

from core import Compiler, Judge, GoalBundle

# A clear, well-specified goal
bundle = GoalBundle(
    goal="Improve API response time for the /users endpoint",
    hard_constraints=[
        "Must not break existing API contract",
        "Must maintain backward compatibility",
        "All existing tests must pass",
    ],
    soft_preferences=[
        "Reduce p95 latency below 200ms",
        "Minimize memory footprint increase",
    ],
    context={
        "endpoint": "/users",
        "current_p95_ms": 450,
        "framework": "FastAPI",
    },
    blessed_state={
        "p95_latency_ms": 450,
        "memory_mb": 128,
        "tests_passing": True,
        "api_contract_intact": True,
    },
    candidate_state={
        "p95_latency_ms": 180,
        "memory_mb": 135,
        "tests_passing": True,
        "api_contract_intact": True,
    },
)

# Compile
compiler = Compiler()
spec = compiler.compile(bundle)

print("=== EvalSpec ===")
print(f"Goal: {spec.goal_summary}")
print(f"Success criteria: {len(spec.success_criteria)}")
for c in spec.success_criteria:
    print(f"  - {c.name} (weight={c.weight})")
print(f"Failure conditions: {len(spec.failure_conditions)}")
for fc in spec.failure_conditions:
    print(f"  - {fc.name}")
print(f"Thresholds: accept={spec.accept_threshold}, stop={spec.stop_threshold}, rollback={spec.rollback_threshold}")

# Judge
judge = Judge()
report, decision = judge.evaluate(spec, bundle)

print("\n=== EvalReport ===")
print(f"Weighted score: {report.weighted_score:.2f}")
print(f"Summary: {report.summary}")
for s in report.criterion_scores:
    print(f"  - {s.criterion_name}: {s.score:.2f} — {s.reasoning}")

print("\n=== Decision ===")
print(f"Verdict: {decision.verdict.value}")
print(f"Reasoning: {decision.reasoning}")
print(f"Confidence: {decision.confidence:.2f}")
if decision.next_hypothesis:
    print(f"Next hypothesis: {decision.next_hypothesis}")
