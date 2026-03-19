"""Interactive adapter: orchestrates the full compile→elicit→judge flow.

This is a thin adapter that a host agent or CLI can use to drive the evaluation
pipeline interactively. It does not define new semantics — it wires together
core components.
"""

from typing import Any
from collections.abc import Callable

from core.compiler import Compiler
from core.elicitor import Elicitor
from core.judge import Judge
from core.schemas import (
    Decision,
    EvalReport,
    EvalSpec,
    GoalBundle,
    PreferenceAnswer,
    PreferenceProfile,
)


class InteractiveAdapter:
    """Orchestrates goal compilation, preference elicitation, and evaluation.

    The adapter accepts a question_handler callback for preference elicitation.
    The callback receives a question string and options list, returns the user's answer.

    Usage:
        def ask_user(question, options):
            # present to user, return answer string
            return input(question)

        adapter = InteractiveAdapter(question_handler=ask_user)
        result = adapter.run(bundle)
    """

    def __init__(
        self,
        question_handler: Callable[[str, list[str]], str] | None = None,
        compiler: Compiler | None = None,
        elicitor: Elicitor | None = None,
        judge: Judge | None = None,
    ):
        self.compiler = compiler or Compiler()
        self.elicitor = elicitor or Elicitor()
        self.judge = judge or Judge()
        self.question_handler = question_handler

    def run(
        self, bundle: GoalBundle
    ) -> dict[str, Any]:
        """Run the full evaluation pipeline.

        Returns a dict with:
            - eval_spec: the compiled EvalSpec
            - preference_profile: the PreferenceProfile (if elicitation occurred)
            - eval_report: the EvalReport (if candidate_state was provided)
            - decision: the Decision (if candidate_state was provided)
            - elicitation_occurred: bool
        """
        profile: PreferenceProfile | None = None
        elicitation_occurred = False

        # Phase 1: Preference elicitation (if needed)
        if self.elicitor.needs_elicitation(bundle):
            if self.question_handler is not None:
                questions = self.elicitor.generate_questions(bundle)
                answers: list[PreferenceAnswer] = []
                for q in questions:
                    answer_text = self.question_handler(q.question, q.options)
                    answers.append(
                        PreferenceAnswer(question_id=q.id, answer=answer_text)
                    )
                profile = self.elicitor.compile_profile(answers)
                elicitation_occurred = True

        # Phase 2: Compile goal into EvalSpec
        spec = self.compiler.compile(bundle, preference_profile=profile)

        result: dict[str, Any] = {
            "eval_spec": spec,
            "preference_profile": profile,
            "elicitation_occurred": elicitation_occurred,
            "eval_report": None,
            "decision": None,
        }

        # Phase 3: Judge (if candidate state exists)
        if bundle.candidate_state is not None:
            report, decision = self.judge.evaluate(spec, bundle)
            result["eval_report"] = report
            result["decision"] = decision

        return result

    def compile_only(
        self,
        bundle: GoalBundle,
        profile: PreferenceProfile | None = None,
    ) -> EvalSpec:
        """Just compile, no judging."""
        return self.compiler.compile(bundle, preference_profile=profile)

    def judge_only(
        self,
        spec: EvalSpec,
        bundle: GoalBundle,
    ) -> tuple[EvalReport, Decision]:
        """Just judge, using a pre-compiled spec."""
        return self.judge.evaluate(spec, bundle)
