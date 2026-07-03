"""
Build a registry YAML from one statusing input spreadsheet.

Same build as config/spreadsheet_ingestion.py (ingest -> hydrate -> enrich ->
dump), but with the input/output paths given on the command line, so you can run
it once per spreadsheet (provincial common, each region) and write the full
registry YAMLs OUTSIDE the repo (some dataset paths may be sensitive).

Enriching a BCGW (Oracle) dataset reads its metadata over a live connection, so
one BCGW connection is opened and reused across the whole build; file datasets
need none. Credentials come from BCGW_USER / BCGW_PASSWORD / BCGW_HOST, else a
prompt (password via getpass).

Examples:
    uv run python scripts/build_registry.py \\
        --xlsx "P:/.../one_status_common_datasets.xlsx" \\
        --out  "//.../workspace/.../provincial_common.yaml"

    uv run python scripts/build_registry.py \\
        --xlsx "P:/.../one_status_west_coast_specific.xlsx" \\
        --out  "//.../workspace/.../west_coast.yaml"
"""

import argparse
from pathlib import Path

from ast_engine.config.registry import enrichment, models, utils
from ast_engine.config.spreadsheet_ingestion import get_credentials
from ast_engine.core.data_adapters.oracle import OracleConnection

# Spreadsheet column -> registry field mapping (matches spreadsheet_ingestion).
# The Buffer_Distance column is read separately to set the operator block.
TEMPLATE = {
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a registry YAML from a statusing input spreadsheet.")
    parser.add_argument("--xlsx", required=True, help="Input statusing spreadsheet (.xlsx).")
    parser.add_argument("--out", required=True, help="Output registry YAML path (keep this outside the repo).")
    parser.add_argument("--version", default="0.1", help="Registry version string.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    datasets = utils.ingest_spreadsheet(TEMPLATE, args.xlsx)
    hydrated = utils.hydrate_base_datasets(datasets)
    print(f"Ingested {len(hydrated)} datasets from {args.xlsx}")

    user, password, host = get_credentials()
    enriched_datasets = []
    with OracleConnection(user, password, host) as (conn, cursor):
        for dataset in hydrated:
            try:
                enriched = enrichment.Enrich(dataset, connection=conn, cursor=cursor)
                enriched.enrich()
                enriched_datasets.append(enriched.build())
            except Exception as exc:
                # One dataset that cannot be enriched (missing table, no metadata)
                # should not stop the whole build - log and carry on.
                print(f"  SKIPPED {dataset.name}: {exc}")

    registry = models.Registry(version=args.version, datasets=enriched_datasets)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    utils.dump_yaml(registry, out_path)
    print(f"Wrote {len(enriched_datasets)} datasets to {out_path}")


if __name__ == "__main__":
    main()
