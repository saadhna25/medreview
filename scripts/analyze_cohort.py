import csv
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from scan_medications import FHIR_DIR, get_active_meds, get_patient_id

INGREDIENTS_CSV = Path("data/processed/med_ingredients.csv")
OUT_DIR = Path("data/processed")


def load_product_ingredients():
    """Map each product code to the set of ingredient names it contains."""
    mapping = defaultdict(set)
    with open(INGREDIENTS_CSV) as f:
        for row in csv.DictReader(f):
            mapping[row["rxnorm_code"]].add(row["ingredient_name"])
    return mapping


def main():
    product_ingredients = load_product_ingredients()
    patients_per_ingredient = Counter()
    patients_per_ingredient_3plus = Counter()
    pair_counts = Counter()
    duplicate_counts = Counter()
    patient_rows = []

    for path in sorted(FHIR_DIR.glob("*.json")):
        bundle = json.loads(path.read_text())
        patient_id = get_patient_id(bundle)
        if patient_id is None:
            continue
        meds = get_active_meds(bundle)
        if not meds:
            continue

        ingredient_counts = Counter()
        for code, name in meds:
            if not product_ingredients[code]:
                print(f"WARNING: no ingredients for {code} {name}")
            for ingredient in product_ingredients[code]:
                ingredient_counts[ingredient] += 1

        ingredients = sorted(ingredient_counts)
        duplicates = sorted(i for i, n in ingredient_counts.items() if n > 1)
        three_plus = len(meds) >= 3

        for ingredient in ingredients:
            patients_per_ingredient[ingredient] += 1
            if three_plus:
                patients_per_ingredient_3plus[ingredient] += 1
        for pair in combinations(ingredients, 2):
            pair_counts[pair] += 1
        for ingredient in duplicates:
            duplicate_counts[ingredient] += 1

        patient_rows.append({
            "patient_id": patient_id,
            "file": path.name,
            "num_products": len(meds),
            "num_ingredients": len(ingredients),
            "ingredients": "|".join(ingredients),
            "duplicates": "|".join(duplicates),
        })

    with open(OUT_DIR / "patient_ingredients.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(patient_rows[0].keys()))
        writer.writeheader()
        writer.writerows(patient_rows)

    with open(OUT_DIR / "ingredient_stats.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ingredient", "num_patients", "num_patients_3plus"])
        for ingredient, count in patients_per_ingredient.most_common():
            writer.writerow([ingredient, count, patients_per_ingredient_3plus[ingredient]])

    with open(OUT_DIR / "ingredient_pairs.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ingredient_a", "ingredient_b", "num_patients"])
        for (a, b), count in pair_counts.most_common():
            writer.writerow([a, b, count])

    print(f"Patients with at least one active medicine: {len(patient_rows)}")
    print(f"Different ingredient pairs taken together: {len(pair_counts)}")
    print(f"Patients with a duplicate ingredient: {sum(1 for r in patient_rows if r['duplicates'])}")

    print("\nTop 20 ingredients (all patients / patients on 3+ medicines):")
    for ingredient, count in patients_per_ingredient.most_common(20):
        print(f"  {count:4d} / {patients_per_ingredient_3plus[ingredient]:4d}  {ingredient}")

    print("\nTop 20 pairs taken together:")
    for (a, b), count in pair_counts.most_common(20):
        print(f"  {count:4d}  {a} + {b}")

    print("\nDuplicate ingredients (number of patients):")
    for ingredient, count in duplicate_counts.most_common():
        print(f"  {count:4d}  {ingredient}")


if __name__ == "__main__":
    main()