"""Example: Rollback case — candidate violates hard constraints.

Demonstrates the rollback path — a candidate state that breaks critical
constraints, causing the judge to recommend rollback.
"""

from core import Compiler, Judge, GoalBundle

bundle = GoalBundle(
    goal="Refactor the authentication module to use JWT tokens",
    hard_constraints=[
        "All existing tests must pass",
        "No security vulnerabilities introduced",
        "Login flow must remain functional",
    ],
    soft_preferences=[
        "Cleaner code structure",
        "Better token expiration handling",
    ],
    context={
        "module": "auth",
        "current_auth": "session-based",
        "target_auth": "JWT",
    },
    blessed_state={
        "tests_passing": True,
        "login_functional": True,
        "security_score": 8.5,
        "code_quality": 6.0,
    },
    candidate_state={
        "tests_passing": False,  # Tests broken!
        "login_functional": True,
        "security_score": 7.0,  # Security degraded
        "code_quality": 8.0,
        # Explicit failure markers
        "failures": ["All existing tests must pass"],
        "violated_constraints": ["No security vulnerabilities introduced"],
    },
)

compiler = Compiler()
spec = compiler.compile(bundle)

judge = Judge()
report, decision = judge.evaluate(spec, bundle)

print("=== EvalReport ===")
print(f"Weighted score: {report.weighted_score:.2f}")
print(f"Failure violations: {report.failure_violations}")
print(f"Summary: {report.summary}")

print("\n=== Decision ===")
print(f"Verdict: {decision.verdict.value}")
print(f"Reasoning: {decision.reasoning}")
print(f"Confidence: {decision.confidence:.2f}")

# Verify it's a rollback
assert decision.verdict.value == "rollback", f"Expected rollback, got {decision.verdict.value}"
print("\n✓ Correctly identified rollback scenario")
