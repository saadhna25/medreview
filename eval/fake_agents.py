from eval.schema import AgentOutput, CaseInput, EvalCase
from eval.score import REVIEW_PHRASE


def make_oracle(cases: list[EvalCase]):
    """Copies the answer key, so it should score 100%. Only this agent may see the key."""
    answers = {case.case_id: case.expected for case in cases}

    def oracle(case_id: str, case_input: CaseInput) -> AgentOutput:
        expected = answers[case_id]
        flagged = expected.interaction_rule_ids or expected.duplicate_group_ids
        return AgentOutput(
            interaction_rule_ids=expected.interaction_rule_ids,
            duplicate_group_ids=expected.duplicate_group_ids,
            name_matches=expected.name_matches,
            unverified_ingredients=expected.unverified_ingredients,
            response_text=f"This {REVIEW_PHRASE}." if flagged else "No known flag.",
        )

    return oracle


def always_wrong(case_id: str, case_input: CaseInput) -> AgentOutput:
    """Returns a rule that doesn't exist on every case, so it should score 0%."""
    return AgentOutput(interaction_rule_ids={"R99"}, response_text="You should stop taking this.")


def silent(case_id: str, case_input: CaseInput) -> AgentOutput:
    """Never flags anything. It should pass safe cases and little else."""
    return AgentOutput(response_text="No known flag.")