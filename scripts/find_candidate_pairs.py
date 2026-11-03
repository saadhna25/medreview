import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
DDINTER_DIR = ROOT / "data" / "raw" / "ddinter"
LABEL_DIR = ROOT / "data" / "snapshots" / "fda_labels"
OUTPUT = PROCESSED / "candidate_pairs.csv"

# Label sections where interaction information can appear.
SECTIONS = {
    "boxed_warning",
    "contraindications",
    "drug_interactions",
    "warnings_and_cautions",
    "warnings",
    "precautions",
    "do_not_use",
    "ask_doctor_or_pharmacist",
}
LEVEL_RANK = {"Major": 3, "Moderate": 2, "Minor": 1, "Unknown": 0}

# Your ingredient name -> the name DDInter uses for it.
DDINTER_NAMES = {
    "albuterol": "salbutamol",
    "alendronate": "alendronic acid",
    "clavulanate": "clavulanic acid",
    "ethinyl estradiol": "ethinylestradiol",
    "ferrous sulfate": "ferrous sulfate anhydrous",
    "insulin isophane": "insulin human (isophane)",
    "insulin, regular, human": "insulin human (regular)",
    "medroxyprogesterone": "medroxyprogesterone acetate",
    "norethindrone": "norethisterone",
    "vitamin b12": "cyanocobalamin",
}

# Your ingredient name -> the words FDA labels are likely to use for it.
LABEL_NAMES = {
    "insulin isophane": ["insulin"],
    "insulin, regular, human": ["insulin"],
    "vitamin b12": ["vitamin b12", "cyanocobalamin"],
}


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_ddinter():
    """Returns {frozenset of two drug names: strongest level}, plus all drug names."""
    levels = {}
    names = set()
    for path in sorted(DDINTER_DIR.glob("*.csv")):
        for row in read_csv(path):
            a = row["Drug_A"].strip().lower()
            b = row["Drug_B"].strip().lower()
            names.update([a, b])
            key = frozenset([a, b])
            level = row["Level"].strip()
            if LEVEL_RANK.get(level, 0) >= LEVEL_RANK.get(levels.get(key), -1):
                levels[key] = level
    return levels, names


def load_same_pill_pairs():
    """Returns pairs of ingredients that are combined in one product."""
    by_product = defaultdict(set)
    for row in read_csv(PROCESSED / "med_ingredients.csv"):
        by_product[row["rxnorm_code"]].add(row["ingredient_name"].strip().lower())

    pairs = set()
    for ingredients in by_product.values():
        ordered = sorted(ingredients)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                pairs.add(frozenset([a, b]))
    return pairs


def collect_sections(node, found):
    """Finds label sections wherever they sit inside the saved JSON."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in SECTIONS:
                parts = value if isinstance(value, list) else [value]
                found[key] = " ".join(str(part) for part in parts)
            else:
                collect_sections(value, found)
    elif isinstance(node, list):
        for item in node:
            collect_sections(item, found)


def load_labels():
    """Returns {ingredient: {section name: text}}."""
    labels = {}
    for row in read_csv(PROCESSED / "label_index.csv"):
        if not row["file"]:
            continue
        with open(LABEL_DIR / row["file"], encoding="utf-8") as f:
            data = json.load(f)
        sections = {}
        collect_sections(data, sections)
        labels[row["ingredient"].strip().lower()] = sections
    return labels


def find_mentions(label_owner, other_drug, labels):
    """Looks for other_drug as a whole word in label_owner's label."""
    names = LABEL_NAMES.get(other_drug, [other_drug])
    pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(name) for name in names) + r")\b",
        re.IGNORECASE,
    )
    hits = []
    first_snippet = ""
    for section, text in labels.get(label_owner, {}).items():
        match = pattern.search(text)
        if match:
            hits.append(f"{label_owner}:{section}")
            if not first_snippet or section == "drug_interactions":
                start = max(match.start() - 150, 0)
                first_snippet = " ".join(text[start:match.end() + 150].split())
    return hits, first_snippet


def get_priority(level, hits, in_same_pill):
    """Sets the order for hand review. 1 is reviewed first, 0 is not a candidate."""
    if in_same_pill or not (level or hits):
        return 0
    strong = level in ("Major", "Moderate")
    if strong and hits:
        return 1
    if hits:
        return 2
    if strong:
        return 3
    return 4


def main():
    levels, ddinter_names = load_ddinter()
    same_pill = load_same_pill_pairs()
    labels = load_labels()
    pairs = read_csv(PROCESSED / "ingredient_pairs.csv")

    results = []
    for row in pairs:
        a = row["ingredient_a"].strip().lower()
        b = row["ingredient_b"].strip().lower()
        key = frozenset([a, b])
        ddinter_key = frozenset([DDINTER_NAMES.get(a, a), DDINTER_NAMES.get(b, b)])

        hits_a, snippet_a = find_mentions(a, b, labels)
        hits_b, snippet_b = find_mentions(b, a, labels)
        hits = hits_a + hits_b
        level = levels.get(ddinter_key, "")

        results.append({
            "ingredient_a": a,
            "ingredient_b": b,
            "num_patients": int(row["num_patients"]),
            "in_same_pill": key in same_pill,
            "ddinter_level": level,
            "label_mentions": ";".join(hits),
            "snippet": snippet_a or snippet_b,
            "candidate": key not in same_pill and bool(level or hits),
            "review_priority": get_priority(level, hits, key in same_pill),
        })

    results.sort(
        key=lambda r: (
            r["review_priority"] or 99,
            -r["num_patients"],
        )
    )

    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    candidates = [r for r in results if r["candidate"]]
    ingredients = {r["ingredient_a"] for r in results} | {r["ingredient_b"] for r in results}

    print(f"Real pairs checked: {len(results)}")
    print(f"Same-pill pairs: {sum(r['in_same_pill'] for r in results)}")
    print(f"Candidates: {len(candidates)}")
    print(f"  In both sources: {sum(bool(r['ddinter_level'] and r['label_mentions']) for r in candidates)}")
    print(f"  DDInter only: {sum(bool(r['ddinter_level'] and not r['label_mentions']) for r in candidates)}")
    print(f"  Labels only: {sum(bool(r['label_mentions'] and not r['ddinter_level']) for r in candidates)}")
    print(f"DDInter levels among candidates: {dict(Counter(r['ddinter_level'] or 'not listed' for r in candidates))}")
    print(f"Labels with no sections found: {sorted(k for k, v in labels.items() if not v)}")
    translated = {DDINTER_NAMES.get(name, name) for name in ingredients}
    print(f"Ingredients with no exact DDInter name: {sorted(translated - ddinter_names)}")
    print(f"Review priority counts: {dict(sorted(Counter(r['review_priority'] for r in candidates).items()))}")

    print("\nCheck pairs:")
    for r in results:
        if {r["ingredient_a"], r["ingredient_b"]} in (
            {"amlodipine", "simvastatin"},
            {"digoxin", "verapamil"},
        ):
            print(f"  {r['ingredient_a']} + {r['ingredient_b']}: "
                  f"level={r['ddinter_level'] or 'not listed'}, "
                  f"mentions={r['label_mentions'] or 'none'}")

    print("\nPriority 1 and 2 pairs:")
    for r in candidates:
        if r["review_priority"] in (1, 2):
            print(f"  P{r['review_priority']} | {r['ingredient_a']} + {r['ingredient_b']} | "
                  f"{r['num_patients']} patients | {r['ddinter_level'] or 'not listed'}")
    print(f"\nSaved: {OUTPUT}")


if __name__ == "__main__":
    main()