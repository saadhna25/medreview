import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from find_candidate_pairs import PROCESSED, ROOT, read_csv
from scan_medications import FHIR_DIR, get_active_meds

OUTPUT = ROOT / "data" / "duplicate_groups.csv"

# Every known product combination that doubles an ingredient.
# Any combination not listed here stops the script, so nothing is classified by guesswork.
KNOWN_GROUPS = {
    frozenset(["316672", "312961"]): (
        "different_strength",
        "Two strengths both active; may be a dose change that was never cleaned up",
    ),
    frozenset(["999969", "197361"]): (
        "hidden_in_combination",
        "Single-ingredient product plus a combination product containing the same ingredient",
    ),
    frozenset(["895994", "896209"]): (
        "hidden_in_combination",
        "Single-ingredient inhaler plus a combination inhaler containing the same ingredient",
    ),
    frozenset(["315971", "1719286"]): (
        "different_route",
        "Oral and injection both active; may be planned or a Synthea quirk. Judgment call: still flag, and mention the different routes",
    ),
}


def main():
    ingredients_by_product = defaultdict(set)
    product_names = {}
    for row in read_csv(PROCESSED / "med_ingredients.csv"):
        ingredient = row["ingredient_name"].strip().lower()
        ingredients_by_product[row["rxnorm_code"]].add(ingredient)
        product_names[row["rxnorm_code"]] = row["product_name"]

    # Counts how many patients have each (ingredient, products) combination.
    group_counts = Counter()
    patients_with_duplicate = set()
    for path in sorted(Path(FHIR_DIR).glob("*.json")):
        with open(path, encoding="utf-8") as f:
            bundle = json.load(f)

        products_by_ingredient = defaultdict(set)
        for code, _name in get_active_meds(bundle):
            for ingredient in ingredients_by_product.get(code, []):
                products_by_ingredient[ingredient].add(code)

        for ingredient, codes in products_by_ingredient.items():
            if len(codes) > 1:
                group_counts[(ingredient, frozenset(codes))] += 1
                patients_with_duplicate.add(path.name)

    unknown = [key for key in group_counts if key[1] not in KNOWN_GROUPS]
    if unknown:
        print("Unknown duplicate combinations. File was NOT written.")
        for ingredient, codes in unknown:
            print(f"  {ingredient}: {sorted(codes)}")
        sys.exit(1)

    rows = []
    ordered = sorted(group_counts.items(), key=lambda item: -item[1])
    for number, ((ingredient, codes), count) in enumerate(ordered, start=1):
        duplicate_type, note = KNOWN_GROUPS[codes]
        code_a, code_b = sorted(codes)
        rows.append({
            "group_id": f"D{number:02d}",
            "ingredient": ingredient,
            "product_a_code": code_a,
            "product_a_name": product_names[code_a],
            "product_b_code": code_b,
            "product_b_name": product_names[code_b],
            "duplicate_type": duplicate_type,
            "num_patients": count,
            "note": note,
        })

    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Patients with a duplicate: {len(patients_with_duplicate)}")
    for r in rows:
        print(f"  {r['group_id']} | {r['ingredient']} | {r['num_patients']} patients | {r['duplicate_type']}")
    print(f"\nSaved: {OUTPUT}")


if __name__ == "__main__":
    main()