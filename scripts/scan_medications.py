import csv
import json
from collections import Counter
from pathlib import Path

FHIR_DIR = Path("data/raw/synthea/fhir")
OUT_DIR = Path("data/processed")
RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"

status_counts = Counter()
missing_code = 0


def get_patient_id(bundle):
    """Return the patient's id, or None if this file isn't a patient."""
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Patient":
            return resource.get("id")
    return None


def get_active_meds(bundle):
    """Return a set of (rxnorm_code, name) for medicines the patient takes now."""
    global missing_code
    meds = set()
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") != "MedicationRequest":
            continue
        status = resource.get("status")
        status_counts[status] += 1
        if status != "active":
            continue
        codings = resource.get("medicationCodeableConcept", {}).get("coding", [])
        rx = [c for c in codings if c.get("system") == RXNORM]
        if not rx:
            missing_code += 1
            continue
        meds.add((rx[0].get("code"), rx[0].get("display")))
    return meds


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    patient_rows = []
    patients_per_med = Counter()
    med_names = {}
    skipped = 0

    for path in sorted(FHIR_DIR.glob("*.json")):
        bundle = json.loads(path.read_text())
        patient_id = get_patient_id(bundle)
        if patient_id is None:
            skipped += 1
            continue
        meds = get_active_meds(bundle)
        patient_rows.append({"file": path.name, "patient_id": patient_id,
                             "active_med_count": len(meds)})
        for code, name in meds:
            patients_per_med[code] += 1
            med_names[code] = name

    with open(OUT_DIR / "patient_med_counts.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "patient_id", "active_med_count"])
        writer.writeheader()
        writer.writerows(patient_rows)

    with open(OUT_DIR / "medication_names.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["rxnorm_code", "name", "num_patients"])
        for code, count in patients_per_med.most_common():
            writer.writerow([code, med_names[code], count])

    three_plus = sum(1 for r in patient_rows if r["active_med_count"] >= 3)
    print(f"Patient files: {len(patient_rows)}  (skipped non-patient files: {skipped})")
    print(f"Prescription statuses: {dict(status_counts)}")
    print(f"Active prescriptions with no RxNorm code: {missing_code}")
    print(f"Patients with 3+ active medicines: {three_plus}")
    print(f"Different active medicines: {len(patients_per_med)}")
    print("\nTop 15 medicines by number of patients:")
    for code, count in patients_per_med.most_common(15):
        print(f"  {count:4d}  {med_names[code]}")


if __name__ == "__main__":
    main()