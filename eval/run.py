import argparse
import json
import sys
from pathlib import Path

from eval.fake_agents import always_wrong, make_oracle, silent
from eval.schema import EvalCase
from eval.score import score_case, summarize

ROOT = Path(__file__).resolve().parent.parent
CASE_DIR = ROOT / "eval" / "cases"
PATIENT_DIR = ROOT / "data" / "patients"
RESULT_DIR = ROOT / "eval" / "results"


def load_cases() -> list[EvalCase]:
    """Loads every case file and stops if any case is broken."""
    cases = []
    for path in sorted(CASE_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            cases += [EvalCase(**item) for item in json.load(f)]

    case_ids = [case.case_id for case in cases]
    repeated = sorted({case_id for case_id in case_ids if case_ids.count(case_id) > 1})
    if repeated:
        raise ValueError(f"Repeated case IDs: {repeated}")
    for case in cases:
        patient_file = case.input.patient_file
        if patient_file and not (PATIENT_DIR / patient_file).exists():
            raise ValueError(f"{case.case_id}: patient file not found: {patient_file}")
    return cases


def run_agent(agent, cases: list[EvalCase]):
    # The key line for fairness: an agent receives the input, never case.expected.
    return [score_case(case, agent(case.case_id, case.input)) for case in cases]


def get_agent(name: str, cases: list[EvalCase]):
    agents = {"oracle": make_oracle(cases), "always_wrong": always_wrong, "silent": silent}
    return agents[name]


def percent(value):
    return "n/a" if value is None else f"{value:.1%}"


def main():
    parser = argparse.ArgumentParser(description="Score an agent on the MedReview eval cases.")
    parser.add_argument("--agent", required=True, choices=["oracle", "always_wrong", "silent"])
    args = parser.parse_args()

    cases = load_cases()
    scores = run_agent(get_agent(args.agent, cases), cases)
    summary = summarize(scores)

    print(f"Agent: {args.agent}")
    print(f"Passed: {summary['passed']} of {summary['cases']} ({summary['passed'] / summary['cases']:.1%})")
    print(f"Flag precision: {percent(summary['precision'])}")
    print(f"Flag recall: {percent(summary['recall'])}")
    print("By case type:")
    for name, result in summary["by_category"].items():
        print(f"  {name}: {result['passed']} of {result['cases']}")

    failures = [score for score in scores if not score.passed]
    if failures:
        print("First 3 failures:")
        for score in failures[:3]:
            print(f"  {score.case_id}: {'; '.join(score.reasons)}")

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    output = RESULT_DIR / f"{args.agent}.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(
            {"agent": args.agent, "summary": summary, "cases": [s.model_dump() for s in scores]},
            f, indent=2,
        )
    print(f"Saved: {output}")


if __name__ == "__main__":
    sys.exit(main())