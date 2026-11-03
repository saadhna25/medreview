import json
import re
import sys
import time
from collections import Counter

import httpx

from find_candidate_pairs import PROCESSED, ROOT, read_csv

INPUT = ROOT / "data" / "messy_names.csv"
CACHE_DIR = ROOT / "data" / "snapshots" / "rxnorm" / "messy_names"
RXNAV = "https://rxnav.nlm.nih.gov/REST"
CHECK_WITH_RXNORM = {"us_brand", "abbreviation"}


def get_json(path, params=None):
    response = httpx.get(f"{RXNAV}/{path}", params=params, timeout=30)
    response.raise_for_status()
    time.sleep(0.1)
    return response.json()


def lookup_ingredients(name):
    """Asks RxNorm which ingredients a name maps to. Saves each answer for repeatability."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / (re.sub(r"[^a-z0-9]+", "_", name.lower()) + ".json")
    if cache_file.exists():
        with open(cache_file, encoding="utf-8") as f:
            return json.load(f)["ingredients"]

    ids = get_json("rxcui.json", {"name": name, "search": 2}).get("idGroup", {}).get("rxnormId", [])
    ingredients = set()
    for rxcui in ids:
        properties = get_json(f"rxcui/{rxcui}/properties.json").get("properties", {})
        if properties.get("tty") == "IN":
            ingredients.add(properties["name"].lower())
            continue
        related = get_json(f"rxcui/{rxcui}/related.json", {"tty": "IN"})
        for group in related.get("relatedGroup", {}).get("conceptGroup", []):
            for concept in group.get("conceptProperties", []):
                ingredients.add(concept["name"].lower())

    result = sorted(ingredients)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({"query": name, "search": 2, "date": time.strftime("%Y-%m-%d"), "ingredients": result}, f, indent=2)
    return result


def main():
    rows = read_csv(INPUT)
    known = {r["ingredient"].strip().lower() for r in read_csv(PROCESSED / "ingredient_stats.csv")}
    problems = []

    names = [r["name"].lower() for r in rows]
    for name, count in Counter(names).items():
        if count > 1:
            problems.append(f"{name}: listed {count} times")

    for row in rows:
        name, category = row["name"], row["category"]
        expected = {x.strip().lower() for x in row["expected_ingredients"].split(";") if x.strip()}

        # Every answer must be one of your 71 ingredients.
        for ingredient in expected - known:
            problems.append(f"{name}: {ingredient} is not in your ingredient list")

        if category == "indian_brand" and not row["source_url"]:
            problems.append(f"{name}: Indian brand has no source link")

        # RxNorm decides whether US brands and short forms are correct.
        if category in CHECK_WITH_RXNORM:
            found = set(lookup_ingredients(name))
            if found != expected:
                problems.append(f"{name}: expected {sorted(expected)}, RxNorm says {sorted(found)}")

        # Made-up names must not exist in RxNorm.
        if category == "no_match":
            found = lookup_ingredients(name)
            if expected or found:
                problems.append(f"{name}: should have no match, RxNorm says {found}")

    print(f"Names checked: {len(rows)}")
    print(f"Categories: {dict(Counter(r['category'] for r in rows))}")
    print(f"Problems: {len(problems)}")
    for problem in problems:
        print(f"  {problem}")
    if problems:
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()