import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_patient_cases import patient_case, split, to_json
from eval.schema import CaseInput, Category, EvalCase, Expected
from find_candidate_pairs import PROCESSED, ROOT, read_csv

PATIENT_CASES = ROOT / "eval" / "cases" / "patient_cases.json"
OUTPUT = ROOT / "eval" / "cases" / "name_cases.json"

# How many names to test from each category. Adds up to 15.
QUOTAS = {
    "indian_brand": 5,
    "us_brand": 1,
    "abbreviation": 1,
    "typo": 3,
    "format": 2,
    "no_match": 3,
}


def main():
    rows = read_csv(ROOT / "data" / "messy_names.csv")
    no_label = {
        r["ingredient"].strip().lower()
        for r in read_csv(PROCESSED / "label_index.csv") if r["status"] != "found"
    }
    patients = read_csv(ROOT / "data" / "selected_patients.csv")
    problems = []

    # Names already tested in interaction cases are skipped, so these cases add new coverage.
    with open(PATIENT_CASES, encoding="utf-8") as f:
        used_names = {name for case in json.load(f) for name in case["input"]["medication_names"]}

    name_cases = []
    for category, quota in QUOTAS.items():
        candidates = [r for r in rows if r["category"] == category and r["name"] not in used_names]
        # Combination brands come first, because they are the hardest to match.
        candidates.sort(key=lambda r: -len(split(r["expected_ingredients"])))
        chosen = candidates[:quota]
        if len(chosen) != quota:
            problems.append(f"{category}: found {len(chosen)} unused names, wanted {quota}")
        for row in chosen:
            name_cases.append(EvalCase(
                case_id=f"NAME{len(name_cases) + 1:03d}",
                category=Category.MESSY_NAME,
                description=f"{category}: {row['name']}",
                input=CaseInput(medication_names=[row["name"]]),
                expected=Expected(name_matches={row["name"]: split(row["expected_ingredients"])}),
            ))

    # The 3 patients kept back earlier, plus mestranol, which no selected patient takes.
    no_label_patients = [
        p for p in patients
        if p["no_label_ingredients"] and not p["rule_ids"] and not p["duplicate_groups"]
    ]
    no_label_cases = [
        patient_case(f"NOLABEL{i:03d}", Category.NO_LABEL, p)
        for i, p in enumerate(no_label_patients, start=1)
    ]
    if "mestranol" not in no_label:
        problems.append("mestranol is not marked as having no current label")
    no_label_cases.append(EvalCase(
        case_id=f"NOLABEL{len(no_label_cases) + 1:03d}",
        category=Category.NO_LABEL,
        description="Mestranol: no current label and no selected patient",
        input=CaseInput(medication_names=["Mestranol"]),
        expected=Expected(
            name_matches={"Mestranol": {"mestranol"}},
            unverified_ingredients={"mestranol"},
        ),
    ))

    covered = {i for c in no_label_cases for i in c.expected.unverified_ingredients}

    print(f"Messy-name cases: {len(name_cases)}")
    for case in name_cases:
        name, ingredients = next(iter(case.expected.name_matches.items()))
        print(f"  {case.case_id} | {name} -> {sorted(ingredients) or 'no match'}")
    print(f"No-label cases: {len(no_label_cases)}")
    print(f"No-label drugs covered: {sorted(covered)}")
    print(f"No-label drugs not covered: {sorted(no_label - covered)}")
    print(f"Problems: {len(problems)}")
    for problem in problems:
        print(f"  {problem}")
    if problems:
        print("File was NOT written.")
        sys.exit(1)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump([to_json(c) for c in name_cases + no_label_cases], f, indent=2)
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    main()