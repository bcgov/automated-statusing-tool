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
        "definition": "Definition_Query",
    }

    datasets = utils.ingest_spreadsheet(template_dict, xlsx_in)
    hydrated = utils.hydrate_base_datasets(datasets)

    # One BCGW connection, reused to enrich every Oracle dataset in the build.
    user, password, host = get_credentials()
    base_datasets_list = []
    with OracleConnection(user, password, host) as (conn, cursor):
        for dataset in hydrated:
            print(dataset)
            enriched = enrichment.Enrich(dataset, connection=conn, cursor=cursor)
            enriched.enrich()
            base_datasets_list.append(enriched.build())

    registry = models.Registry(version="0.1", datasets=base_datasets_list)
    utils.dump_yaml(registry, Path("ast_engine/tests/data/Test_Registry.yaml"))


if __name__ == "__main__":
    main()
