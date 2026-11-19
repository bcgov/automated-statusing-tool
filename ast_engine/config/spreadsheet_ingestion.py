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

import argparse
import getpass
import os
import sys
from pathlib import Path

import logging

from ast_engine.config.logging_config import setup_logging
from ast_engine.config.registry import enrichment, utils, models
from ast_engine.config.settings import Settings
from ast_engine.core.data_adapters.oracle import OracleConnection
from ast_engine.core.data_adapters.exceptions import DataAdapterError

setup_logging()
logger = logging.getLogger(__name__)

def main() -> None:

    settings = Settings()
    parser = argparse.ArgumentParser(
        description="Build a dataset registry from an input spreadsheet."
    )
    parser.add_argument(
        "--input",
        "-i",
        help="Folder that contains the spreadsheet (xlsx) files.",
        required=False,
    )
    parser.add_argument(
        "--file",
        "-f",
        help="Single spreadsheet (xlsx) file to ingest.",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Folder to write the registry (yaml) files.",
        required=False,
    )
    args = parser.parse_args()
    # logger.info(f"Command line arguments: {args}")
    if args.output is not None:
        logger.info(f"Using output folder from command line: {args.output}")
        output_dir = args.output
    elif settings.registry_output_path is not None:
        logger.info(f"Using registry output path from settings: {settings.registry_output_path}")
        output_dir = settings.registry_output_path
    else:
        output_dir = "ast_engine/tests/registry"
        logger.info(f"No output folder specified, defaulting to {output_dir}")
    folder_path = None
    folder_path = args.input if args.input is not None else settings.registry_spreadsheet_path
    if folder_path is not None:
        logger.info(f"Using folder path: {folder_path}")
        spreadsheet_io = {
            f"{folder_path}/{xlsx}": f"{output_dir}/{xlsx.replace('.xlsx', '.yaml')}"
            for xlsx in os.listdir(folder_path)
            if xlsx.endswith(".xlsx")
        }
        if len(spreadsheet_io) == 0:
            raise FileNotFoundError(f"No .xlsx files found in {folder_path}")
    elif args.file is not None:
        if not os.path.isfile(args.file):
            raise FileNotFoundError(f"File not found: {args.file}")
        if not args.file.endswith(".xlsx"):
            raise ValueError(f"File is not an .xlsx spreadsheet: {args.file}")
        spreadsheet_io = {
            args.file: f"{output_dir}/{Path(args.file).stem}.yaml"
        }
    else: # demo mode
        logger.info("No parameters provided. Running in demo mode")
        spreadsheet_io = {
            "ast_engine/tests/registry/Test_Registry.xlsx":"ast_engine/tests/registry/Test_Registry.yaml",
            "ast_engine/tests/registry/Test_Registry_2.xlsx":"ast_engine/tests/registry/Test_Registry_2.yaml",
        }
    logger.info(f"Spreadsheet I/O mapping: {spreadsheet_io}")
    print("\n")
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
    user, password, host = utils.get_credentials()

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
