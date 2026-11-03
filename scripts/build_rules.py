import csv
import sys

from find_candidate_pairs import (
    DDINTER_NAMES,
    LEVEL_RANK,
    PROCESSED,
    ROOT,
    load_ddinter,
    load_labels,
    load_same_pill_pairs,
    read_csv,
)

OUTPUT = ROOT / "data" / "interaction_rules.csv"

# All insulin ingredients in your data. The labels say "insulin" in general.
INSULIN = ["insulin isophane", "insulin, regular, human", "insulin lispro"]

# Each rule: drug A, drug B, effect in plain words, label used, section, exact quote, note.
RULES = [
    (["amlodipine"], ["simvastatin"], "Higher simvastatin exposure; label sets a dose limit",
     "amlodipine", "drug_interactions",
     "Do not exceed doses greater than 20 mg daily of simvastatin.", ""),
    (["digoxin"], ["verapamil"], "Verapamil raises digoxin levels",
     "digoxin", "drug_interactions",
     "Verapamil 50-75% NA", "Label table entry; the instruction applies to this group of drugs"),
    (["hydrochlorothiazide"], INSULIN, "Insulin dose may need adjusting",
     "hydrochlorothiazide", "drug_interactions",
     "Antidiabetic drugs (oral agents and insulin) Dosage adjustment of the antidiabetic drug may be required.", ""),
    (INSULIN, ["metformin"], "Higher risk of low blood sugar",
     "metformin", "drug_interactions",
     "with an insulin secretagogue (e.g., sulfonylurea) or insulin may increase the risk of hypoglycemia.", ""),
    (["simvastatin"], ["verapamil"], "Higher simvastatin exposure; label sets a dose limit",
     "simvastatin", "drug_interactions",
     "For patients taking verapamil, diltiazem, or dronedarone, do not exceed simvastatin 10 mg daily.", ""),
    (["digoxin"], ["simvastatin"], "Digoxin levels need monitoring",
     "simvastatin", "drug_interactions",
     "Digoxin: During simvastatin initiation, monitor digoxin levels.", ""),
    (["simvastatin"], ["warfarin"], "Bleeding or raised INR reported",
     "simvastatin", "drug_interactions",
     "There are postmarketing reports of clinically evident bleeding and/or increased INR in patients taking concomitant statins and warfarin.", ""),
    (["furosemide"], ["naproxen"], "Naproxen can weaken furosemide's effect",
     "naproxen", "drug_interactions",
     "NSAIDs reduced the natriuretic effect of loop diuretics (e.g., furosemide)", ""),
    (["naproxen"], ["warfarin"], "Higher risk of serious bleeding",
     "naproxen", "drug_interactions",
     "Naproxen and anticoagulants such as warfarin have a synergistic effect on bleeding.", ""),
    (["digoxin"], ["naproxen"], "Naproxen can raise digoxin levels",
     "naproxen", "drug_interactions",
     "The concomitant use of naproxen with digoxin has been reported to increase the serum concentration and prolong the half-life of", ""),
    (["metoprolol"], ["verapamil"], "Higher risk of slow heart rate",
     "metoprolol", "drug_interactions",
     "Digitalis glycosides, clonidine, diltiazem, and verapamil slow atrioventricular conduction and decrease heart rate.", ""),
    (["clopidogrel"], ["warfarin"], "Higher bleeding risk",
     "clopidogrel", "drug_interactions",
     "Nonsteroidal anti-inflammatory drugs (NSAIDs), warfarin, selective serotonin and serotonin norepinephrine reuptake inhibitors (SSRIs, SNRIs): Increases risk of bleeding.", ""),
    (["atenolol"], ["verapamil"], "Risk of slow heart rate and heart block",
     "atenolol", "warnings",
     "Bradycardia and heart block can occur and the left ventricular end diastolic pressure can rise when beta-blockers are administered with verapamil or diltiazem.", ""),
    (["sertraline"], ["warfarin"], "Monitor for side effects; doses may need reducing",
     "sertraline", "drug_interactions",
     "Protein-bound drugs: Monitor for adverse reactions and reduce dosage of Sertraline HCl Capsules or other protein-bound drugs (e.g., warfarin) as warranted", ""),
    (["acetaminophen"], ["warfarin"], "High acetaminophen doses can raise INR",
     "acetaminophen", "drug_interactions",
     "dose of 4,000 mg/day has been shown to cause an increase in international normalized ratio (INR) in some patients who have been stabilized on sodium warfarin as an anticoagulant.", "Dose-dependent"),
    (["fluoxetine"], ["warfarin"], "May increase bleeding risk",
     "fluoxetine", "drug_interactions",
     "Drugs that Interfere with Hemostasis (e.g. NSAIDs, Aspirin, Warfarin): May potentiate the risk of bleeding", ""),
    (["methotrexate"], ["naproxen"], "Higher risk of methotrexate toxicity",
     "naproxen", "drug_interactions",
     "Concomitant use of NSAIDs and methotrexate may increase the risk for methotrexate toxicity", ""),
    (["fluoxetine"], ["metoprolol"], "Fluoxetine can double metoprolol levels",
     "metoprolol", "drug_interactions",
     "Drugs that are strong inhibitors of CYP2D6 such as quinidine, fluoxetine, paroxetine, and propafenone were shown to double metoprolol concentrations.", ""),
    (["ferrous sulfate"], ["levothyroxine"], "Iron can reduce levothyroxine absorption; take 4 hours apart",
     "levothyroxine", "drug_interactions",
     "Phosphate Binders (e.g., calcium carbonate, ferrous sulfate, sevelamer, lanthanum) Phosphate binders may bind to levothyroxine. Administer levothyroxine sodium tablets at least 4 hours apart from these agents.", ""),
    (["digoxin"], ["metformin"], "May raise digoxin levels by an unclear amount",
     "digoxin", "drug_interactions",
     "Digoxin concentrations increased, but magnitude is unclear Alprazolam, azithromycin, cyclosporine, diclofenac, diphenoxylate, epoprostenol, esomeprazole, ibuprofen, ketoconazole, lansoprazole, metformin, omeprazole", ""),
    (["carbamazepine"], ["verapamil"], "Verapamil can raise carbamazepine levels",
     "carbamazepine", "precautions",
     "acetazolamide, verapamil, ticlopidine, grapefruit juice, and protease inhibitors.", "Quote ends a list that starts: Drugs that have been shown, or would be expected, to increase plasma carbamazepine levels"),
    (["carbamazepine"], ["warfarin"], "Carbamazepine can lower warfarin levels",
     "carbamazepine", "precautions",
     "valproate, warfarin, ziprasidone, zonisamide.", "Quote ends a list that starts: carbamazepine causes, or would be expected to cause, decreased levels of the following drugs"),
    (["clopidogrel"], ["fluoxetine"], "Higher bleeding risk",
     "clopidogrel", "drug_interactions",
     "Nonsteroidal anti-inflammatory drugs (NSAIDs), warfarin, selective serotonin and serotonin norepinephrine reuptake inhibitors (SSRIs, SNRIs): Increases risk of bleeding.", "Label names the group SSRIs; fluoxetine belongs to it"),
]


def normalize(text):
    return " ".join(text.split())


def main():
    labels = load_labels()
    label_info = {r["ingredient"].strip().lower(): r for r in read_csv(PROCESSED / "label_index.csv")}
    levels, _ = load_ddinter()
    same_pill = load_same_pill_pairs()
    patient_counts = {
        frozenset([r["ingredient_a"].strip().lower(), r["ingredient_b"].strip().lower()]): int(r["num_patients"])
        for r in read_csv(PROCESSED / "ingredient_pairs.csv")
    }

    rows = []
    problems = []
    for number, (drugs_a, drugs_b, effect, owner, section, quote, note) in enumerate(RULES, start=1):
        rule_id = f"R{number:02d}"
        name = f"{drugs_a[0]} + {drugs_b[0]}"
        pairs = [frozenset([a, b]) for a in drugs_a for b in drugs_b]

        # The key check: the quote must appear word for word in the saved label section.
        section_text = normalize(labels.get(owner, {}).get(section, ""))
        if not section_text:
            problems.append(f"{rule_id} {name}: section {section} not found in {owner} label")
        elif normalize(quote) not in section_text:
            problems.append(f"{rule_id} {name}: quote not found in {owner}:{section}")

        # The pair must really occur in patients, and not only inside one pill.
        counts = [patient_counts[p] for p in pairs if p in patient_counts]
        if not counts:
            problems.append(f"{rule_id} {name}: pair not found in patients")
        if all(p in same_pill for p in pairs):
            problems.append(f"{rule_id} {name}: pair only occurs inside one pill")

        found_levels = [
            levels.get(frozenset(DDINTER_NAMES.get(d, d) for d in p), "") for p in pairs
        ]
        level = max(found_levels, key=lambda x: LEVEL_RANK.get(x, -1))
        info = label_info.get(owner, {})

        rows.append({
            "rule_id": rule_id,
            "drug_a_ingredients": ";".join(drugs_a),
            "drug_b_ingredients": ";".join(drugs_b),
            "max_patients": max(counts, default=0),
            "effect": effect,
            "label_ingredient": owner,
            "label_section": section,
            "label_set_id": info.get("set_id", ""),
            "label_effective_time": info.get("effective_time", ""),
            "evidence_quote": quote,
            "ddinter_level": level or "not listed",
            "note": note,
        })

    print(f"Rules checked: {len(rows)}")
    if problems:
        print(f"Problems: {len(problems)}. Rules file was NOT written.")
        for problem in problems:
            print(f"  {problem}")
        sys.exit(1)

    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print("Problems: 0")
    for r in rows:
        print(f"  {r['rule_id']} | {r['drug_a_ingredients'].split(';')[0]} + "
              f"{r['drug_b_ingredients'].split(';')[0]} | {r['max_patients']} patients | {r['ddinter_level']}")
    print(f"\nSaved: {OUTPUT}")


if __name__ == "__main__":
    main()