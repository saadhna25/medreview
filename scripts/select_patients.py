import csv
import hashlib
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from find_candidate_pairs import PROCESSED, ROOT, read_csv
from scan_medications import FHIR_DIR, get_active_meds

OUTPUT = ROOT / "data" / "selected_patients.csv"
SEED = "medreview-v1"
TOTAL = 100
MIN_INTERACTION = 40
MIN_DUPLICATE = 15
PER_RULE = 2
PER_DUPLICATE = 3
PER_NO_LABEL = 2


def stable_order(patient):
    """Gives the same order on every run, without using randomness."""
    return hashlib.sha256(f"{SEED}:{patient['file']}".encode()).hexdigest()


def main():
    ingredients_by_product = defaultdict(set)
    for row in read_csv(PROCESSED / "med_ingredients.csv"):
        ingredients_by_product[row["rxnorm_code"]].add(row["ingredient_name"].strip().lower())

    rules = read_csv(ROOT / "data" / "interaction_rules.csv")
    duplicate_groups = read_csv(ROOT / "data" / "duplicate_groups.csv")
    no_label_ingredients = {
        r["ingredient"].strip().lower()
        for r in read_csv(PROCESSED / "label_index.csv")
        if r["status"] != "found"
    }
    pair_priority = {
        frozenset([r["ingredient_a"], r["ingredient_b"]]): int(r["review_priority"])
        for r in read_csv(PROCESSED / "candidate_pairs.csv")
    }
    patient_ids = {r["file"]: r["patient_id"] for r in read_csv(PROCESSED / "patient_ingredients.csv")}

    patients = []
    for path in sorted(Path(FHIR_DIR).glob("*.json")):
        with open(path, encoding="utf-8") as f:
            bundle = json.load(f)
        codes = {code for code, _name in get_active_meds(bundle)}
        if len(codes) < 3:
            continue

        ingredients = set()
        for code in codes:
            ingredients |= ingredients_by_product.get(code, set())

        rule_ids = [
            r["rule_id"] for r in rules
            if ingredients & set(r["drug_a_ingredients"].split(";"))
            and ingredients & set(r["drug_b_ingredients"].split(";"))
        ]
        group_ids = [
            g["group_id"] for g in duplicate_groups
            if {g["product_a_code"], g["product_b_code"]} <= codes
        ]
        no_label = sorted(ingredients & no_label_ingredients)

        # Clean means nothing suspicious: priority 1, 2 and 3 pairs all disqualify a patient.
        pairs = [frozenset(p) for p in combinations(sorted(ingredients), 2)]
        suspicious = any(pair_priority.get(p, 0) in (1, 2, 3) for p in pairs)

        patients.append({
            "patient_id": patient_ids.get(path.name, ""),
            "file": path.name,
            "num_products": len(codes),
            "ingredients": ";".join(sorted(ingredients)),
            "rule_ids": rule_ids,
            "group_ids": group_ids,
            "no_label": no_label,
            "clean": not (rule_ids or group_ids or no_label or suspicious),
        })

    patients.sort(key=stable_order)
    selected = {}

    def add(candidates, how_many):
        added = 0
        for patient in candidates:
            if added >= how_many or len(selected) >= TOTAL:
                break
            if patient["file"] not in selected:
                selected[patient["file"]] = patient
                added += 1

    # Step 1: rare cases first, so every rule and duplicate group is represented if possible.
    rule_counts = Counter(rule_id for p in patients for rule_id in p["rule_ids"])
    for r in sorted(rules, key=lambda x: rule_counts[x["rule_id"]]):
        rule_id = r["rule_id"]
        already = sum(rule_id in p["rule_ids"] for p in selected.values())
        add([p for p in patients if rule_id in p["rule_ids"]], max(PER_RULE - already, 0))
    for g in duplicate_groups:
        group_id = g["group_id"]
        already = sum(group_id in p["group_ids"] for p in selected.values())
        add([p for p in patients if group_id in p["group_ids"]], max(PER_DUPLICATE - already, 0))
    for ingredient in sorted(no_label_ingredients):
        already = sum(ingredient in p["no_label"] for p in selected.values())
        add([p for p in patients if ingredient in p["no_label"]], max(PER_NO_LABEL - already, 0))

    # Step 2: reach the minimum counts for interactions and duplicates.
    count_with = lambda key: sum(bool(p[key]) for p in selected.values())
    add([p for p in patients if p["rule_ids"]], max(MIN_INTERACTION - count_with("rule_ids"), 0))
    add([p for p in patients if p["group_ids"]], max(MIN_DUPLICATE - count_with("group_ids"), 0))

    # Step 3: fill the rest with clean patients, then anyone left if clean patients run out.
    add([p for p in patients if p["clean"]], TOTAL - len(selected))
    add(patients, TOTAL - len(selected))

    rows = []
    for patient in sorted(selected.values(), key=stable_order):
        rows.append({
            "patient_id": patient["patient_id"],
            "file": patient["file"],
            "num_products": patient["num_products"],
            "ingredients": patient["ingredients"],
            "rule_ids": ";".join(patient["rule_ids"]),
            "duplicate_groups": ";".join(patient["group_ids"]),
            "no_label_ingredients": ";".join(patient["no_label"]),
            "no_known_flag": patient["clean"],
        })

    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    chosen = list(selected.values())
    covered_rules = {rule_id for p in chosen for rule_id in p["rule_ids"]}
    covered_groups = {group_id for p in chosen for group_id in p["group_ids"]}
    covered_no_label = {name for p in chosen for name in p["no_label"]}

    print(f"Patients with 3+ products: {len(patients)}")
    print(f"Clean patients available: {sum(p['clean'] for p in patients)}")
    print(f"Selected: {len(chosen)}")
    print(f"  With an interaction: {count_with('rule_ids')}")
    print(f"  With a duplicate: {count_with('group_ids')}")
    print(f"  With a no-label drug: {count_with('no_label')}")
    print(f"  No known flag: {sum(p['clean'] for p in chosen)}")
    print(f"Rules covered: {len(covered_rules)} of {len(rules)}")
    print(f"Rules not covered: {sorted({r['rule_id'] for r in rules} - covered_rules)}")
    print(f"Duplicate groups not covered: {sorted({g['group_id'] for g in duplicate_groups} - covered_groups)}")
    print(f"No-label drugs not covered: {sorted(no_label_ingredients - covered_no_label)}")
    print(f"\nSaved: {OUTPUT}")


if __name__ == "__main__":
    main()