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

import logging

from ast_engine.config.logging_config import setup_logging
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

setup_logging()
logger = logging.getLogger(__name__)

def main() -> None:
    spreadsheet_io = {
        "ast_engine/config/registry/tab1/tab1.xlsx":"ast_engine/config/registry/tab1/tab1.yaml",
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

    # Get drive mappings for linux
    path_lookup = utils.drive_map_loader(path_lookup_conf)

    for xlsx_in, yaml_out in spreadsheet_io.items():
        datasets = utils.ingest_spreadsheet(template_dict, xlsx_in)
        # Ensure pathing is correct for host OS
        for dataset in datasets:
            dataset["datasource"] = utils.path_translate(dataset["datasource"], path_lookup)
        # A dataset that cannot be built is skipped and the build carries on - a
        # couple of bad rows should not cost you the rest of the spreadsheet. Every
        # one that is skipped is collected here and written into the registry under
        # 'skipped', so the registry always says what it does not cover. Without
        # that the registry just comes out short, and nothing later can tell
        # "checked and found nothing" apart from "never checked at all".
        hydrated, skipped = utils.hydrate_base_datasets(datasets)
        base_datasets_list = []
        with OracleConnection(user, password, host) as (conn, cursor):
            for dataset in hydrated:
                print(dataset)
                try:
                    enriched = enrichment.Enrich(dataset, connection=conn, cursor=cursor)
                    enriched.enrich()
                    base_datasets_list.append(enriched.build())
                except DataAdapterError as e:
                    # Usually a path in the spreadsheet that no longer points at
                    # anything, or a BCGW table that cannot be read.
                    print(e)
                    logger.warning(f"Could not read {dataset.name}: {e}")
                    skipped.append(models.SkippedDataset(
                        name=dataset.name,
                        datasource=dataset.datasource,
                        stage="reading the dataset",
                        reason=utils.short_reason(e),
                    ))
        utils.log_skipped(skipped, len(datasets))
        registry = utils.RegistryBuilder(base_datasets_list, skipped=skipped).build()
        utils.dump_yaml(registry, Path(yaml_out))
        logger.info(
            "Wrote %s: %d datasets, %d skipped", yaml_out, len(base_datasets_list), len(skipped)
        )


if __name__ == "__main__":
    main()
