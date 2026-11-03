# Data manifest

## Synthea patients
- Source: https://github.com/synthetichealth/synthea-sample-data/raw/main/downloads/synthea_sample_data_fhir_r4_sep2019.zip
- Release: September 2019, FHIR R4
- Downloaded: 2026-11-02
- Size: 81.1 MB
- SHA-256: a6fc595d9c0f4c646746af42f861b5a12d03c856af158dd837c764dfb81b66f8
- JSON files: 1180 (in synthea/fhir/; includes a few hospital and practitioner files, not only patients)
- License: Synthea sample data, free for research and educational use

## RxNorm ingredient mappings
- Source: RxNorm API (rxnav.nlm.nih.gov), related.json?tty=IN and rxcui.json?name=
- Retrieved: 2026-11-02
- Saved in: data/snapshots/rxnorm/
- 83 of 88 products mapped by API; 5 obsolete codes mapped by hand in data/manual_ingredient_map.csv, checked against RxNorm historystatus records

## FDA drug labels
- Source: openFDA drug label API (api.fda.gov/drug/label.json)
- Retrieved: 2026-11-02
- Saved in: data/snapshots/fda_labels/ (one label per ingredient, with query and date)
- Selection rule: prescription first, single ingredient, newest effective_time
- Overrides: data/manual_label_overrides.csv (brand-name searches, combination-only ingredients, drugs no longer sold)
- Result: 67 of 71 ingredients have a label; 4 have no current US label
- openFDA states its data is not validated for clinical use

## DDInter interactions
- Source: DDInter 2.0 (ddinter2.scbdd.com/download/), 8 CSV files
- Downloaded: 2 Nov 2026
- Saved in: data/raw/ddinter/ (gitignored); checksums in data/snapshots/ddinter_sha256.txt
- Licence: CC BY-NC-SA 4.0
- Used to find candidate pairs; FDA label text is the evidence for each rule
- Limitation: the download page has no files for ATC groups C, G, J, M, N and S, so some pairs are missing (digoxin + verapamil, for example)

## Interaction rules
- Files: data/processed/candidate_pairs.csv, data/interaction_rules.csv
- Scripts: scripts/find_candidate_pairs.py, scripts/build_rules.py
- Candidates: 816 real pairs checked against DDInter and FDA label text; same-pill pairs removed
- Final list: 23 rules, chosen by hand; each quote is checked word for word against the saved label
- Not reviewed by a clinician
- Known gaps, left out because the label text is not specific enough. These pairs are not proven safe:
  - verapamil + warfarin (41 patients)
  - amlodipine + warfarin (8 patients)
  - chlorthalidone + insulin (4 patients)
  - docetaxel + verapamil (9 patients)
  - hydrocodone + verapamil (2 patients)
- Known issue: the saved hydrocodone label is a hydrocodone-only product (Hysingla ER), but patients take acetaminophen/hydrocodone combinations

## Duplicate groups
- File: data/duplicate_groups.csv
- Script: scripts/build_duplicate_groups.py
- Definition: the same ingredient in 2 or more active products for one patient
- Result: 73 patients, 4 groups (furosemide 55, simvastatin 12, amlodipine 8, fluticasone 1)
- Types: different_route, different_strength, hidden_in_combination
- Judgment call: furosemide oral + injection is still flagged, with a note about the different routes, because it may be planned or a Synthea quirk
- Limitation: different drugs from the same group (two statins, for example) are not counted as duplicates in v1
- Evidence for these flags is the patient's own medicine list, so no FDA label quote is needed

## Messy names
- File: data/messy_names.csv (51 names)
- Script: scripts/check_messy_names.py
- Saved RxNorm answers: data/snapshots/rxnorm/messy_names/
- Categories: 20 Indian brands, 12 US brands, 3 short forms, 9 typos, 4 formatting, 3 no match
- US brands and short forms: answers confirmed by RxNorm
- No-match names: confirmed to return nothing from RxNorm
- Indian brands: not in RxNorm; each has a source link in the file, checked by hand on 3 Nov 2026
- Indian brands: not in RxNorm; each has a source link in the file. Page text fetched with TinyFish and compared to the answers by Claude on 3 Nov 2026; not checked by a person
- Typos and formatting: mostly made up from the correct ingredient name; two come from Synthea records
- Limitation: Indian brand sources are mostly retail pharmacy listings, not official labels

## Messy names
- File: data/messy_names.csv (51 names)
- Script: scripts/check_messy_names.py
- Saved RxNorm answers: data/snapshots/rxnorm/messy_names/
- Categories: 20 Indian brands, 12 US brands, 3 short forms, 9 typos, 4 formatting, 3 no match
- US brands and short forms: answers confirmed by RxNorm
- No-match names: confirmed to return nothing from RxNorm
- Indian brands: not in RxNorm; each has a source link in the file. Page text fetched with TinyFish and compared to the answers by Claude on 3 Nov 2026; not checked by a person
- Typos and formatting: mostly made up from the correct ingredient name; two come from Synthea records
- Limitation: Indian brand sources are mostly retail pharmacy listings, not official labels

## Selected patients
- File: data/selected_patients.csv (100 patients)
- Script: scripts/select_patients.py (seed: medreview-v1; same result on every run)
- Chosen from: 306 patients with 3+ active products
- Method: rare rules and duplicate groups first, then at least 40 with an interaction and 15 with a duplicate, then no-known-flag patients
- Result: 40 with an interaction, 15 with a duplicate, 5 with a no-label drug, 54 with no known flag (groups overlap)
- Coverage: all 23 rules and all 4 duplicate groups
- Gap: mestranol (no current label) is not covered; test it separately in Phase 1
- no_known_flag means no rule, duplicate, no-label drug, or reviewed DDInter or label candidate pair (priorities 1 to 3). It does not mean the medicines are safe

## Trimmed patient files
- Folder: data/patients/ (100 files, 3.1 MB)
- Script: scripts/trim_selected_patients.py
- Keeps only Patient and MedicationRequest resources from the Synthea bundles
- Check: active medicines in each trimmed file match the original
- References to removed resources (such as encounters) may no longer resolve
- Full files stay in data/raw/synthea/fhir/ (gitignored); v2 features that need conditions must go back to them

## Eval cases
- Files: eval/cases/ (124 cases)
- Scripts: scripts/build_patient_cases.py, build_name_cases.py, build_injection_cases.py, build_sycophancy_cases.py
- Counts: 40 interaction, 30 safe, 15 duplicate, 15 messy name, 10 injection, 10 sycophancy, 4 no-label
- Answers come from the rules and data files. Injection and sycophancy prompts were written with Claude; their expected flags still come from the rules
- Scoring check: oracle 124/124, always_wrong 0/124, silent 33/124 (the floor for an agent that never flags)
- Holdout: 21 no-known-flag patients not used in any case
- Limitation: forbidden-phrase checks only catch exact wording
- Judgment call: medicines mentioned only in a patient note do not count in v1