'''

'''


from ast_engine.config.registry import enrichment, utils, models

from pathlib import Path

# ingest spreadshet

xlsx_in = "ast_engine/tests/data/Test_Registry.xlsx"

template_dict = {
    "name": "Featureclass_Name(valid characters only)",
    "datasource": "Datasource",
    "aggregate_columns": [
        "Fields_to_Summarize",
        "Fields_to_Summarize2",
        "Fields_to_Summarize3",
        "Fields_to_Summarize4",
        "Fields_to_Summarize5",
        "Fields_to_Summarize6",
    ],
    "definition":"Definition_Query",
}

datasets = utils.ingest_spreadsheet(template_dict, xlsx_in)
# for value in datasets:
    # print(value)
# print(datasets)
# print(len(datasets))

hydrated = utils.hydrate_base_datasets(datasets)
# print(hydrated)

for dataset in hydrated:
    print(dataset)
    enriched = enrichment.Enrich(dataset)
    enriched.enrich()

# utils.dump_yaml()