'''
Build the dataset registry from an input spreadsheet.

Reads the statusing input spreadsheet, hydrates BaseDatasets, enriches each one
with real geometry/CRS/columns/row-count, and writes the result to a registry
YAML.

Enriching a BCGW (Oracle) dataset reads its metadata over a live database
connection, so this script opens one OracleConnection and reuses it across every
dataset (file datasets need no connection). 

Credentials come from the BCGW_USER / BCGW_PASSWORD / BCGW_HOST environment
variables if set, otherwise the script prompts for them (the password is read
with getpass so it never echoes ).
'''


import getpass
import os
import sys
from pathlib import Path

from ast_engine.config.registry import enrichment, utils, models
from ast_engine.core.data_adapters.oracle import OracleConnection
from ast_engine.core.data_adapters.exceptions import DataAdapterError

def get_credentials() -> tuple[str, str, str]:
    '''BCGW credentials from the environment, falling back to a prompt.'''
    user = os.environ.get("BCGW_USER") or input("BCGW username: ").strip()
    password = os.environ.get("BCGW_PASSWORD") or getpass.getpass("BCGW password: ")
    host = os.environ.get("BCGW_HOST") or input(
        "BCGW host/DSN (e.g. bcgw.bcgov:1521/idwprod1.bcgov): "
    ).strip()
    if not (user and password and host):
        sys.exit("Missing BCGW credentials; aborting.")
    return user, password, host


def main() -> None:
    # xlsx_in = "ast_engine/tests/data/Test_Registry.xlsx"
    # yaml_out = "ast_engine/tests/data/Test_Registry.yaml"
    spreadsheet_io = {
        "ast_engine/tests/data/Test_Registry.xlsx":"ast_engine/tests/data/Test_Registry.yaml",
        "ast_engine/tests/data/Test_Registry_2.xlsx":"ast_engine/tests/data/Test_Registry_2.yaml",
    }
    path_lookup_conf = "ast_engine/config/drive_map.conf"

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
        "definition_query": "Definition_Query",
    }

    # One BCGW connection, reused to enrich every Oracle dataset in the build.
    user, password, host = get_credentials()

    # Get drive mappings
    path_lookup = utils.drive_map_loader(path_lookup_conf)

    for xlsx_in, yaml_out in spreadsheet_io.items():
        datasets = utils.ingest_spreadsheet(template_dict, xlsx_in)
        for dataset in datasets:
            dataset["datasource"] = utils.path_translate(dataset["datasource"], path_lookup)
        hydrated = utils.hydrate_base_datasets(datasets)
        base_datasets_list = []
        with OracleConnection(user, password, host) as (conn, cursor):
            for dataset in hydrated:
                print(dataset)
                try:
                    enriched = enrichment.Enrich(dataset, connection=conn, cursor=cursor)
                    enriched.enrich()
                    base_datasets_list.append(enriched.build())
                except DataAdapterError as e:
                    print(e)
                    print(f"skipping {dataset.name} due to a read error")
                    continue

        registry = models.Registry(version="0.1", datasets=base_datasets_list)
        utils.dump_yaml(registry, Path(yaml_out))


if __name__ == "__main__":
    main()
