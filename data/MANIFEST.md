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