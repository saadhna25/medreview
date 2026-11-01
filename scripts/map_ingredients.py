import csv
import json
import time
from collections import defaultdict
from pathlib import Path

import httpx

MEDS_CSV = Path("data/processed/medication_names.csv")
MANUAL_CSV = Path("data/manual_ingredient_map.csv")  # NEW
CACHE_DIR = Path("data/snapshots/rxnorm")
OUT_CSV = Path("data/processed/med_ingredients.csv")
URL = "https://rxnav.nlm.nih.gov/REST/rxcui/{code}/related.json"
NAME_URL = "https://rxnav.nlm.nih.gov/REST/rxcui.json"  # NEW
IGNORED_INGREDIENTS = {"inert ingredients"}  # NEW


def fetch_ingredients_data(code, client):
    """Get RxNorm's answer for one product, using the saved copy if it exists."""
    cache_file = CACHE_DIR / f"{code}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    response = client.get(URL.format(code=code), params={"tty": "IN"})
    response.raise_for_status()
    data = response.json()
    cache_file.write_text(json.dumps(data, indent=2))
    time.sleep(0.1)
    return data


def extract_ingredients(data):
    """Pull (ingredient_code, ingredient_name) pairs out of RxNorm's answer."""
    ingredients = []
    for group in data.get("relatedGroup", {}).get("conceptGroup", []):
        for concept in group.get("conceptProperties", []):
            ingredients.append((concept["rxcui"], concept["name"]))
    return sorted(ingredients)


def load_manual_map():  # NEW
    """Read the hand-checked file: product code -> list of ingredient names."""
    manual = defaultdict(list)
    with open(MANUAL_CSV) as f:
        for row in csv.DictReader(f):
            manual[row["rxnorm_code"]].append(row["ingredient_name"])
    return manual


def lookup_ingredient_code(name, client):  # NEW
    """Find the RxNorm code for an ingredient name, using a saved copy if it exists."""
    cache_file = CACHE_DIR / f"name_{name.replace(' ', '_')}.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text())
    else:
        response = client.get(NAME_URL, params={"name": name})
        response.raise_for_status()
        data = response.json()
        cache_file.write_text(json.dumps(data, indent=2))
        time.sleep(0.1)
    ids = data.get("idGroup", {}).get("rxnormId", [])
    if not ids:
        raise ValueError(f"No RxNorm code found for ingredient name: {name}")
    return ids[0]


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(MEDS_CSV) as f:
        meds = list(csv.DictReader(f))
    manual = load_manual_map()  # NEW

    rows = []
    unmapped = []
    combos = 0
    manual_used = 0  # NEW
    products_per_ingredient = defaultdict(list)

    with httpx.Client(timeout=20) as client:
        for med in meds:
            code = med["rxnorm_code"]
            data = fetch_ingredients_data(code, client)
            ingredients = extract_ingredients(data)
            ingredients = [i for i in ingredients if i[1] not in IGNORED_INGREDIENTS]  # NEW
            source = "rxnorm_api"
            if not ingredients and code in manual:  # NEW
                ingredients = [(lookup_ingredient_code(n, client), n) for n in manual[code]]
                source = "manual"
                manual_used += 1
            if not ingredients:
                unmapped.append(med)
                continue
            if len(ingredients) > 1:
                combos += 1
            for ing_code, ing_name in ingredients:
                rows.append({
                    "rxnorm_code": code,
                    "product_name": med["name"],
                    "num_patients": med["num_patients"],
                    "ingredient_code": ing_code,
                    "ingredient_name": ing_name,
                    "num_ingredients": len(ingredients),
                    "source": source,  # NEW
                })
                products_per_ingredient[ing_name].append(med["name"])

    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Products: {len(meds)}  mapped: {len(meds) - len(unmapped)}  unmapped: {len(unmapped)}")
    print(f"Mapped using the manual file: {manual_used}")
    print(f"Combination products (2+ ingredients): {combos}")
    print(f"Different ingredients: {len(products_per_ingredient)}")

    print("\nUnmapped products:")
    for med in unmapped:
        print(f"  {med['rxnorm_code']}  {med['name']}")

    print("\nIngredients found in more than one product:")
    for name, products in sorted(products_per_ingredient.items()):
        if len(products) > 1:
            print(f"  {name}: {len(products)} products")


if __name__ == "__main__":
    main()