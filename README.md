# Goal-to-Evaluator Compiler

A framework-agnostic system that converts open-ended goals into structured evaluation contracts, then uses those contracts to judge progress and emit one of four decisions: **accept**, **continue**, **rollback**, or **stop**.

Built for autonomous and semi-autonomous agent workflows that need to iterate toward a goal without drifting.

## The Problem

When an agent iterates on a task, three things go wrong:

1. **Vague goals** produce unstable evaluation. The agent doesn't know what "better" means, so it optimizes proxies that drift from the user's intent.
2. **No rollback signal.** The agent keeps going even when a candidate is worse than the last known-good state.
3. **No stopping signal.** The agent iterates past the point of diminishing returns.

This project solves all three by introducing a portable **evaluation coprocessor** that any host agent or workflow can plug into.

## How It Works

```
GoalBundle ──► Compiler ──► EvalSpec
                  ▲
                  │ (if goal is ambiguous)
                  │
              Elicitor ──► PreferenceProfile
                  ▲
                  │
              User answers 5-8 tradeoff questions


EvalSpec + blessed_state + candidate_state ──► Judge ──► EvalReport + Decision
```

**Three operations, two data flows:**

| Operation | Input | Output |
|-----------|-------|--------|
| **Compile** | GoalBundle + optional PreferenceProfile | EvalSpec |
| **Elicit** | GoalBundle (ambiguous) | Tradeoff questions → PreferenceProfile |
| **Judge** | EvalSpec + GoalBundle (with states) | EvalReport + Decision |

## Installation

Requires Python 3.12+.

```bash
# Clone the repository
git clone <repo-url>
cd Goal-to-Evaluator-Compiler

# Create a conda environment (recommended)
conda create -n goal-eval python=3.12 -y
conda activate goal-eval

# Install in editable mode
pip install -e ".[dev]"
```

## Quick Start

### 1. Clear goal — compile and judge directly

When the goal has enough structure (constraints, preferences), skip elicitation and go straight to evaluation.

```python
from core import Compiler, Judge, GoalBundle

bundle = GoalBundle(
    goal="Improve API response time for the /users endpoint",
    hard_constraints=[
        "Must not break existing API contract",
        "All existing tests must pass",
    ],
    soft_preferences=[
        "Reduce p95 latency below 200ms",
        "Minimize memory footprint increase",
    ],
    blessed_state={
        "p95_latency_ms": 450,
        "memory_mb": 128,
        "tests_passing": True,
    },
    candidate_state={
        "p95_latency_ms": 180,
        "memory_mb": 135,
        "tests_passing": True,
    },
)

compiler = Compiler()
spec = compiler.compile(bundle)

judge = Judge()
report, decision = judge.evaluate(spec, bundle)

print(decision.verdict.value)   # "accept_as_blessed"
print(decision.reasoning)       # Score 0.83 exceeds accept threshold...
print(report.weighted_score)    # 0.83
```

### 2. Ambiguous goal — elicit preferences first

When the goal is vague ("make it better"), the system detects ambiguity and generates targeted tradeoff questions before compiling.

```python
from core import Compiler, Elicitor, GoalBundle
from core.schemas import PreferenceAnswer

bundle = GoalBundle(goal="Make the app better")

elicitor = Elicitor()

# Check if elicitation is needed
if elicitor.needs_elicitation(bundle):
    questions = elicitor.generate_questions(bundle)

    # Present questions to the user and collect answers.
    # Each question has an id, text, options, and maps_to field.
    answers = [
        PreferenceAnswer(
            question_id="outcome_priority",
            answer="User experience / polish, Speed / performance",
        ),
        PreferenceAnswer(
            question_id="unacceptable_outcomes",
            answer="Breaking existing functionality, Data loss or corruption",
        ),
        # ... answer all questions
    ]

    profile = elicitor.compile_profile(answers)

    compiler = Compiler()
    spec = compiler.compile(bundle, preference_profile=profile)
    # spec now has criteria weighted by user preferences,
    # failure conditions from unacceptable outcomes,
    # and thresholds tuned to exploration bias
```

### 3. Using the interactive adapter

The `InteractiveAdapter` wires together the full pipeline with a callback for user interaction.

```python
from core import GoalBundle
from adapters.interactive import InteractiveAdapter

def ask_user(question: str, options: list[str]) -> str:
    """Present a question to the user and return their answer."""
    print(question)
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    return input("> ")

adapter = InteractiveAdapter(question_handler=ask_user)

bundle = GoalBundle(
    goal="Refactor the auth module",
    blessed_state={"tests_passing": True, "code_quality": 6},
    candidate_state={"tests_passing": True, "code_quality": 8},
)

result = adapter.run(bundle)

print(result["decision"].verdict.value)      # The verdict
print(result["elicitation_occurred"])          # Whether questions were asked
print(result["eval_report"].weighted_score)   # Overall score
```

## Core Concepts

### GoalBundle

The portable input package. Everything the system needs to know:

| Field | Type | Purpose |
|-------|------|---------|
| `goal` | `str` | The user's goal in natural language |
| `hard_constraints` | `list[str]` | Non-negotiable requirements. Violation triggers rollback. |
| `soft_preferences` | `list[str]` | Desired qualities that influence evaluation weight. |
| `context` | `dict` | Arbitrary context (domain, files, metadata). |
| `blessed_state` | `dict \| None` | Last-known-good state. `None` on first iteration. |
| `candidate_state` | `dict \| None` | Proposed new state to evaluate. |
| `iteration_budget` | `int \| None` | Max iterations before considering stop. |
| `current_iteration` | `int` | How many iterations have occurred. |

### EvalSpec

The evaluation contract produced by the Compiler. Defines what success, failure, and drift mean for a specific goal.

- **`success_criteria`** — Weighted criteria with evidence requirements and direction (`higher_is_better`).
- **`failure_conditions`** — Hard-fail conditions that trigger rollback regardless of score.
- **`drift_anchors`** — Questions the judge must answer to detect goal drift.
- **`accept_threshold`** / **`stop_threshold`** / **`rollback_threshold`** — Score boundaries that determine the decision.

### PreferenceProfile

Structured output of the elicitation step. Each field directly parameterizes the EvalSpec:

- **`outcome_priorities`** — Ordered list of what matters most (becomes weighted criteria).
- **`unacceptable_outcomes`** — Become failure conditions.
- **`tradeoff_tolerances`** — Inform criteria weights.
- **`stopping_threshold`** — Adjusts the stop threshold (`perfect` = 0.98, `minimum_viable` = 0.80).
- **`exploration_bias`** — Adjusts all thresholds (`conservative` raises them, `aggressive` lowers them).

### Decision

Exactly one of four verdicts:

| Verdict | When | What it means |
|---------|------|---------------|
| `accept_as_blessed` | Score >= accept threshold, < stop threshold, no failures | Candidate is meaningfully better. Promote it to blessed. |
| `continue` | Score between rollback and accept thresholds | Blessed state is still valid. Keep iterating. |
| `rollback` | Failure conditions triggered, or score < rollback threshold, or significant drift | Candidate is worse. Revert to blessed. |
| `stop` | Score >= stop threshold, or iteration budget exhausted | Goal sufficiently achieved. Stop iterating. |

## Project Structure

```
core/                   # Framework-agnostic evaluation logic
  schemas.py            # All data contracts (GoalBundle, EvalSpec, Decision, etc.)
  compiler.py           # GoalBundle + PreferenceProfile → EvalSpec
  elicitor.py           # Ambiguity detection and preference question generation
  judge.py              # EvalSpec + states → EvalReport + Decision

adapters/               # Thin integration layers
  interactive.py        # Orchestrates the full compile→elicit→judge pipeline

examples/               # Runnable demonstrations
  clear_goal.py         # Well-specified goal → accept
  ambiguous_goal.py     # Vague goal → elicitation → compile
  rollback_case.py      # Constraint violation → rollback

tests/                  # Comprehensive test suite
  test_schemas.py       # Contract structure and serialization
  test_compiler.py      # Compilation logic and threshold tuning
  test_elicitor.py      # Ambiguity detection and profile compilation
  test_judge.py         # Scoring, decisions, and drift detection
  test_integration.py   # Full end-to-end pipeline flows
```

## Running Examples

```bash
python examples/clear_goal.py
python examples/ambiguous_goal.py
python examples/rollback_case.py
```

## Running Tests

```bash
pytest tests/ -v
```

## Extending the System

### Custom Judge

Subclass `Judge` and override scoring methods for domain-specific evaluation:

```python
from core.judge import Judge
from core.schemas import CriterionScore

class CodeQualityJudge(Judge):
    def score_criterion(self, criterion, candidate, blessed):
        # Custom scoring logic for code quality metrics
        if criterion.name == "test_coverage":
            coverage = candidate.get("coverage_pct", 0)
            return CriterionScore(
                criterion_name=criterion.name,
                score=min(coverage / 100, 1.0),
                evidence_found=f"coverage={coverage}%",
                reasoning=f"Test coverage is {coverage}%",
            )
        return super().score_criterion(criterion, candidate, blessed)
```

### Custom Compiler

Subclass `Compiler` to add domain-specific compilation logic (e.g., LLM-backed goal parsing):

```python
from core.compiler import Compiler
from core.schemas import GoalBundle, EvalSpec, PreferenceProfile

class LLMCompiler(Compiler):
    def compile(self, bundle, preference_profile=None):
        # Use an LLM to parse the goal into structured criteria,
        # then fall back to the base compiler for threshold logic
        spec = super().compile(bundle, preference_profile)
        # ... augment spec with LLM-derived criteria
        return spec
```

### Writing a New Adapter

Adapters are thin wrappers that wire the core components into a specific workflow. See `adapters/interactive.py` for the pattern. An adapter should:

1. Accept a `GoalBundle` from the host
2. Optionally run elicitation
3. Compile to `EvalSpec`
4. Judge candidate vs blessed
5. Return `EvalReport` + `Decision`

## Anti-Drift Guarantees

Every evaluation includes five drift-anchor questions that the judge must assess:

1. Which original user goal does this change serve?
2. What concrete evidence shows this is a real improvement?
3. Did complexity increase without proportional value?
4. Would a realistic user accept this as progress?
5. Are we optimizing a proxy that no longer reflects the original intent?

If drift is detected on multiple anchors, the judge recommends rollback.

## License

MIT
