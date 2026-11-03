from collections import Counter

from eval.fake_agents import always_wrong, make_oracle, silent
from eval.run import load_cases, run_agent
from eval.score import summarize

EXPECTED_COUNTS = {
    "interaction": 40,
    "safe": 30,
    "duplicate": 15,
    "messy_name": 15,
    "injection": 10,
    "sycophancy": 10,
    "no_label": 4,
}


def test_case_counts_match_the_plan():
    cases = load_cases()
    assert dict(Counter(case.category.value for case in cases)) == EXPECTED_COUNTS


def test_oracle_passes_everything():
    cases = load_cases()
    summary = summarize(run_agent(make_oracle(cases), cases))
    assert summary["passed"] == summary["cases"]
    assert summary["precision"] == 1.0
    assert summary["recall"] == 1.0


def test_always_wrong_passes_nothing():
    cases = load_cases()
    summary = summarize(run_agent(always_wrong, cases))
    assert summary["passed"] == 0
    assert summary["recall"] == 0.0


def test_silent_agent_cannot_pass_flag_cases():
    cases = load_cases()
    summary = summarize(run_agent(silent, cases))
    assert summary["by_category"]["safe"]["passed"] == 30
    assert summary["by_category"]["interaction"]["passed"] == 0
    assert summary["by_category"]["duplicate"]["passed"] == 0
    assert summary["by_category"]["messy_name"]["passed"] == 0
    assert summary["recall"] == 0.0