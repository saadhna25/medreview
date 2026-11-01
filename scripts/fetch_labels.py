import csv
import json
import re
import time
from datetime import date
from pathlib import Path

import httpx

STATS_CSV = Path("data/processed/ingredient_stats.csv")
OVERRIDES_CSV = Path("data/manual_label_overrides.csv")
LABEL_DIR = Path("data/snapshots/fda_labels")
INDEX_CSV = Path("data/processed/label_index.csv")
URL = "https://api.fda.gov/drug/label.json"
SECTIONS = ["boxed_warning", "contraindications", "warnings_and_cautions", "warnings",
            "precautions", "drug_interactions", "do_not_use", "ask_doctor_or_pharmacist"]
FIELDS = ["ingredient", "status", "file", "set_id", "effective_time", "generic_name",
          "product_type", "selected_from", "label_kind", "has_interaction_text", "note"] + \
         [f"has_{s}" for s in SECTIONS]


def slug(name):
    """Turn 'insulin, regular, human' into 'insulin_regular_human' for file names."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def load_overrides():
    with open(OVERRIDES_CSV) as f:
        return {row["ingredient"]: row for row in csv.DictReader(f)}


def search_labels(query, client):
    """Return up to 20 labels matching the query, newest first."""
    response = client.get(URL, params={"search": query, "sort": "effective_time:desc", "limit": 20})
    time.sleep(0.3)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return response.json().get("results", [])


def is_single_ingredient(label):
    names = label.get("openfda", {}).get("generic_name", [])
    return bool(names) and not any(" AND " in n.upper() for n in names)


def has_interaction_text(label):
    """True if the label discusses interactions anywhere we know to look."""
    if "drug_interactions" in label or "ask_doctor_or_pharmacist" in label:
        return True
    text = " ".join(" ".join(label.get(s, [])) for s in ["precautions", "warnings"])
    return "interact" in text.lower()


def choose_label(ingredient, client, override):
    """Selection rule: prescription first, single ingredient, newest. Overrides adjust it."""
    action = override["action"] if override else None
    if action == "brand":
        attempts = [("manual_brand", f'openfda.brand_name:"{override["value"]}"')]
    else:
        base = f'openfda.generic_name:"{ingredient}"'
        attempts = [
            ("prescription", base + ' AND openfda.product_type:"HUMAN PRESCRIPTION DRUG"'),
            ("any", base),
        ]
    for selected_from, query in attempts:
        labels = search_labels(query, client)
        if action != "combination":
            labels = [l for l in labels if is_single_ingredient(l)]
        if labels:
            return labels[0], selected_from, query
    return None, None, None


def main():
    LABEL_DIR.mkdir(parents=True, exist_ok=True)
    overrides = load_overrides()
    with open(STATS_CSV) as f:
        ingredients = [row["ingredient"] for row in csv.DictReader(f)]

    rows = []
    with httpx.Client(timeout=30) as client:
        for ingredient in ingredients:
            override = overrides.get(ingredient)
            note = override["note"] if override else ""

            if override and override["action"] == "withdrawn":
                rows.append({"ingredient": ingredient, "status": "no_current_label", "note": note})
                continue

            out_file = LABEL_DIR / f"{slug(ingredient)}.json"
            if out_file.exists():
                saved = json.loads(out_file.read_text())
            else:
                label, selected_from, query = choose_label(ingredient, client, override)
                if label is None:
                    rows.append({"ingredient": ingredient, "status": "missing", "note": note})
                    continue
                saved = {
                    "ingredient": ingredient,
                    "selected_from": selected_from,
                    "query": query,
                    "retrieved_on": date.today().isoformat(),
                    "label": label,
                }
                out_file.write_text(json.dumps(saved, indent=2))

            label = saved["label"]
            openfda = label.get("openfda", {})
            row = {
                "ingredient": ingredient,
                "status": "found",
                "file": out_file.name,
                "set_id": label.get("set_id"),
                "effective_time": label.get("effective_time"),
                "generic_name": "|".join(openfda.get("generic_name", [])),
                "product_type": "|".join(openfda.get("product_type", [])),
                "selected_from": saved["selected_from"],
                "label_kind": "single" if is_single_ingredient(label) else "combination",
                "has_interaction_text": has_interaction_text(label),
                "note": note,
            }
            for section in SECTIONS:
                row[f"has_{section}"] = section in label
            rows.append(row)

    with open(INDEX_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    found = [r for r in rows if r["status"] == "found"]
    print(f"Ingredients: {len(ingredients)}  found: {len(found)}  "
          f"no current label: {sum(r['status'] == 'no_current_label' for r in rows)}  "
          f"missing: {sum(r['status'] == 'missing' for r in rows)}")
    print(f"Combination labels used: {sum(r['label_kind'] == 'combination' for r in found)}")
    print(f"Labels with interaction text somewhere: {sum(r['has_interaction_text'] for r in found)}")

    print("\nStill missing:")
    for r in rows:
        if r["status"] == "missing":
            print(f"  {r['ingredient']}")
    print("\nFound, but no interaction text anywhere:")
    for r in found:
        if not r["has_interaction_text"]:
            print(f"  {r['ingredient']}  ({r['product_type']})")


if __name__ == "__main__":
    main()