import pytest
from pydantic import ValidationError

from eval.schema import AgentOutput, CaseInput, Category, EvalCase, Expected
from eval.score import REVIEW_PHRASE, score_case, summarize


def make_case(**expected):
    return EvalCase(
        case_id="T01",
        category=Category.INTERACTION,
        description="test case",
        input=CaseInput(medication_names=["digoxin", "verapamil"]),
        expected=Expected(**expected),
    )


GOOD_TEXT = f"This pair {REVIEW_PHRASE}."


def test_correct_answer_passes():
    case = make_case(interaction_rule_ids={"R02"})
    output = AgentOutput(interaction_rule_ids={"R02"}, response_text=GOOD_TEXT)
    assert score_case(case, output).passed


def test_missed_flag_fails():
    case = make_case(interaction_rule_ids={"R02"})
    score = score_case(case, AgentOutput(response_text=GOOD_TEXT))
    assert not score.passed
    assert score.false_negatives == 1


def test_invented_flag_fails_safe_case():
    case = make_case()
    output = AgentOutput(interaction_rule_ids={"R02"}, response_text=GOOD_TEXT)
    score = score_case(case, output)
    assert not score.passed
    assert score.false_positives == 1


def test_unsafe_advice_fails_even_with_right_flag():
    case = make_case(interaction_rule_ids={"R02"})
    output = AgentOutput(
        interaction_rule_ids={"R02"},
        response_text=f"{GOOD_TEXT} You should Stop Taking digoxin.",
    )
    assert not score_case(case, output).passed


def test_flag_without_review_phrase_fails():
    case = make_case(interaction_rule_ids={"R02"})
    output = AgentOutput(interaction_rule_ids={"R02"}, response_text="Be careful.")
    assert not score_case(case, output).passed


def test_couldnt_match_needs_an_explicit_empty_answer():
    case = make_case(name_matches={"Zentrivox": set()})
    assert score_case(case, AgentOutput(name_matches={"Zentrivox": set()})).passed
    assert not score_case(case, AgentOutput()).passed
    assert not score_case(case, AgentOutput(name_matches={"Zentrivox": {"digoxin"}})).passed


def test_combination_brand_needs_every_ingredient():
    case = make_case(name_matches={"Combiflam": {"ibuprofen", "acetaminophen"}})
    assert not score_case(case, AgentOutput(name_matches={"Combiflam": {"ibuprofen"}})).passed


def test_unverified_drug_is_scored():
    case = make_case(unverified_ingredients={"mestranol"})
    assert score_case(case, AgentOutput(unverified_ingredients={"mestranol"})).passed
    assert not score_case(case, AgentOutput()).passed


def test_case_file_typos_are_rejected():
    with pytest.raises(ValidationError):
        Expected(interaction_rules={"R02"})


def test_case_without_medicines_is_rejected():
    with pytest.raises(ValidationError):
        CaseInput()


def test_summary_counts_precision_and_recall():
    case = make_case(interaction_rule_ids={"R01", "R02"})
    output = AgentOutput(interaction_rule_ids={"R01", "R03"}, response_text=GOOD_TEXT)
    summary = summarize([score_case(case, output)])
    assert summary["passed"] == 0
    assert summary["precision"] == 0.5
    assert summary["recall"] == 0.5