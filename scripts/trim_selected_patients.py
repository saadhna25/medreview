import json
import sys
from pathlib import Path

from find_candidate_pairs import ROOT, read_csv
from scan_medications import FHIR_DIR, get_active_meds

SELECTED = ROOT / "data" / "selected_patients.csv"
OUTPUT_DIR = ROOT / "data" / "patients"
KEEP = {"Patient", "MedicationRequest"}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_csv(SELECTED)
    problems = []
    original_size = 0
    trimmed_size = 0
    largest = 0

    for row in rows:
        source = Path(FHIR_DIR) / row["file"]
        target = OUTPUT_DIR / row["file"]
        with open(source, encoding="utf-8") as f:
            bundle = json.load(f)

        # Keeps the bundle's shape, but only the two resource types MedReview reads.
        trimmed = dict(bundle)
        trimmed["entry"] = [
            entry for entry in bundle.get("entry", [])
            if entry.get("resource", {}).get("resourceType") in KEEP
        ]

        with open(target, "w", encoding="utf-8") as f:
            json.dump(trimmed, f, separators=(",", ":"))

        # The key check: the saved file must give the same active medicines as the original.
        with open(target, encoding="utf-8") as f:
            saved = json.load(f)
        if get_active_meds(saved) != get_active_meds(bundle):
            problems.append(f"{row['file']}: active medicines changed")
        if not any(e.get("resource", {}).get("resourceType") == "Patient" for e in saved["entry"]):
            problems.append(f"{row['file']}: no Patient resource")

        original_size += source.stat().st_size
        size = target.stat().st_size
        trimmed_size += size
        largest = max(largest, size)

    print(f"Files written: {len(rows)}")
    print(f"Original: {original_size / 1e6:.1f} MB")
    print(f"Trimmed: {trimmed_size / 1e6:.1f} MB (largest {largest / 1e6:.2f} MB)")
    print(f"Problems: {len(problems)}")
    for problem in problems:
        print(f"  {problem}")
    if problems:
        sys.exit(1)
    print(f"Saved in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()