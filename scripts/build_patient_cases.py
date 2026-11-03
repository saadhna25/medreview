import json
import sys
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.schema import CaseInput, Category, EvalCase, Expected
from find_candidate_pairs import PROCESSED, ROOT, read_csv
from scan_medications import get_active_meds

OUTPUT = ROOT / "eval" / "cases" / "patient_cases.json"
PATIENT_DIR = ROOT / "data" / "patients"
NUM_INTERACTION = 40
NUM_SAFE = 30
NUM_DUPLICATE = 15

# Pairs we chose not to make rules. They must never appear in a safe case.
KNOWN_GAPS = [
    {"verapamil", "warfarin"},
    {"amlodipine", "warfarin"},
    {"docetaxel", "verapamil"},
    {"hydrocodone", "verapamil"},
]
KNOWN_GAP_GROUPS = [({"chlorthalidone"}, {"insulin isophane", "insulin, regular, human", "insulin lispro"})]


def split(value):
    return {item for item in value.split(";") if item}


def rules_for(ingredients, rules):
    return {
        r["rule_id"] for r in rules
        if ingredients & split(r["drug_a_ingredients"]) and ingredients & split(r["drug_b_ingredients"])
    }


def has_known_gap(ingredients):
    if any(pair <= ingredients for pair in KNOWN_GAPS):
        return True
    return any(ingredients & a and ingredients & b for a, b in KNOWN_GAP_GROUPS)


def patient_case(case_id, category, patient):
    return EvalCase(
        case_id=case_id,
        category=category,
        description=f"Patient record: {patient['file']}",
        input=CaseInput(patient_file=patient["file"]),
        expected=Expected(
            interaction_rule_ids=split(patient["rule_ids"]),
            duplicate_group_ids=split(patient["duplicate_groups"]),
            unverified_ingredients=split(patient["no_label_ingredients"]),
        ),
    )


def name_cases(rules, names_by_ingredient, no_label, needed):
    """Builds extra cases from messy names: messy names in, correct flags out."""
    options = {}
    for rule in sorted(rules, key=lambda r: r["rule_id"]):
        pairs = []
        for a, b in product(sorted(split(rule["drug_a_ingredients"])), sorted(split(rule["drug_b_ingredients"]))):
            pairs += list(product(names_by_ingredient.get(a, []), names_by_ingredient.get(b, [])))
        if pairs:
            options[rule["rule_id"]] = pairs

    ingredients_of = {}
    for ingredient, names in names_by_ingredient.items():
        for name in names:
            ingredients_of.setdefault(name, set()).add(ingredient)

    cases = []
    used = set()
    position = 0
    while len(cases) < needed:
        added = False
        for rule_id, pairs in options.items():
            if position < len(pairs) and len(cases) < needed:
                name_a, name_b = pairs[position]
                key = frozenset([name_a, name_b])
                if name_a != name_b and key not in used:
                    used.add(key)
                    ingredients = ingredients_of[name_a] | ingredients_of[name_b]
                    cases.append((rule_id, name_a, name_b, ingredients))
                    added = True
        position += 1
        if not added and position > max((len(p) for p in options.values()), default=0):
            break
    return [
        EvalCase(
            case_id="",
            category=Category.INTERACTION,
            description=f"Messy names for {rule_id}: {name_a} + {name_b}",
            input=CaseInput(medication_names=[name_a, name_b]),
            expected=Expected(
                interaction_rule_ids=rules_for(ingredients, rules),
                name_matches={name_a: ingredients_of[name_a], name_b: ingredients_of[name_b]},
                unverified_ingredients=ingredients & no_label,
            ),
        )
        for rule_id, name_a, name_b, ingredients in cases
    ]


def to_json(case):
    """Sorts every list, so the file is identical on every run."""
    data = case.model_dump(mode="json")
    expected = data["expected"]
    for key in ("interaction_rule_ids", "duplicate_group_ids", "unverified_ingredients"):
        expected[key] = sorted(expected[key])
    expected["name_matches"] = {k: sorted(v) for k, v in sorted(expected["name_matches"].items())}
    return data


def main():
    patients = read_csv(ROOT / "data" / "selected_patients.csv")
    rules = read_csv(ROOT / "data" / "interaction_rules.csv")
    no_label = {
        r["ingredient"].strip().lower()
        for r in read_csv(PROCESSED / "label_index.csv") if r["status"] != "found"
    }
    ingredients_by_product = {}
    for row in read_csv(PROCESSED / "med_ingredients.csv"):
        ingredients_by_product.setdefault(row["rxnorm_code"], set()).add(row["ingredient_name"].strip().lower())

    problems = []

    # Checks the answer key against the committed patient files, not only the CSV.
    for patient in patients:
        path = PATIENT_DIR / patient["file"]
        if not path.exists():
            problems.append(f"{patient['file']}: patient file is missing")
            continue
        with open(path, encoding="utf-8") as f:
            bundle = json.load(f)
        found = set()
        for code, _name in get_active_meds(bundle):
            found |= ingredients_by_product.get(code, set())
        if found != split(patient["ingredients"]):
            problems.append(f"{patient['file']}: ingredients differ from the CSV")
        if rules_for(found, rules) != split(patient["rule_ids"]):
            problems.append(f"{patient['file']}: rule matches differ from the CSV")

    # Each patient is used once, so no flag gets counted twice.
    with_duplicate = [p for p in patients if p["duplicate_groups"]]
    with_rule_only = [p for p in patients if p["rule_ids"] and not p["duplicate_groups"]]
    safe = [p for p in patients if p["no_known_flag"] == "True"]
    no_label_only = [
        p for p in patients
        if p["no_label_ingredients"] and not p["rule_ids"] and not p["duplicate_groups"]
    ]

    for patient in safe:
        if has_known_gap(split(patient["ingredients"])):
            problems.append(f"{patient['file']}: safe patient has a known-gap pair")

    duplicate_cases = [
        patient_case(f"DUP{i:03d}", Category.DUPLICATE, p)
        for i, p in enumerate(with_duplicate[:NUM_DUPLICATE], start=1)
    ]
    safe_cases = [
        patient_case(f"SAFE{i:03d}", Category.SAFE, p)
        for i, p in enumerate(safe[:NUM_SAFE], start=1)
    ]
    interaction_cases = [
        patient_case("", Category.INTERACTION, p) for p in with_rule_only[:NUM_INTERACTION]
    ]
    num_from_patients = len(interaction_cases)

    # Tops up interactions with brand and short-form names. Typos stay in the messy-name cases.
    names_by_ingredient = {}
    for row in read_csv(ROOT / "data" / "messy_names.csv"):
        ingredients = split(row["expected_ingredients"])
        if row["category"] in ("us_brand", "indian_brand", "abbreviation") and len(ingredients) == 1:
            names_by_ingredient.setdefault(next(iter(ingredients)), []).append(row["name"])

    interaction_cases += name_cases(rules, names_by_ingredient, no_label, NUM_INTERACTION - num_from_patients)
    for i, case in enumerate(interaction_cases, start=1):
        case.case_id = f"INT{i:03d}"

    cases = interaction_cases + safe_cases + duplicate_cases

    if len(interaction_cases) != NUM_INTERACTION:
        problems.append(f"Interaction cases: {len(interaction_cases)}, wanted {NUM_INTERACTION}")
    if len(safe_cases) != NUM_SAFE:
        problems.append(f"Safe cases: {len(safe_cases)}, wanted {NUM_SAFE}")
    if len(duplicate_cases) != NUM_DUPLICATE:
        problems.append(f"Duplicate cases: {len(duplicate_cases)}, wanted {NUM_DUPLICATE}")

    covered = set().union(*(c.expected.interaction_rule_ids for c in cases)) if cases else set()
    uncovered = sorted({r["rule_id"] for r in rules} - covered)

    print(f"Patients used once each: {len(with_duplicate) + len(with_rule_only) + len(safe)}")
    print(f"Interaction cases: {len(interaction_cases)} ({num_from_patients} patients, {len(interaction_cases) - num_from_patients} messy-name lists)")
    print(f"Safe cases: {len(safe_cases)}")
    print(f"Duplicate cases: {len(duplicate_cases)}")
    print(f"Duplicate groups covered: {sorted(set().union(*(c.expected.duplicate_group_ids for c in duplicate_cases)))}")
    print(f"Rules not covered: {uncovered}")
    print(f"No-label-only patients, kept for a later step: {len(no_label_only)}")
    print(f"Problems: {len(problems)}")
    for problem in problems:
        print(f"  {problem}")
    if problems:
        print("File was NOT written.")
        sys.exit(1)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump([to_json(c) for c in cases], f, indent=2)
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    main()
