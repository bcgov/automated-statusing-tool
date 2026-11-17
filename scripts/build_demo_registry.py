"""
Build the demo registry - file-based, no database.

Writes a common-datasets registry over the sample datasets in
ast_engine/tests/data, so the whole application (form -> API -> queue -> worker
-> results) can be run on a machine with no BCGW login. docker-compose.yml points
the worker at this registry by default.

The dataset paths are written relative to the repo root, which is where the
worker runs from - both in a working copy and in its container. Re-run this
after changing the sample data, and commit the result.

Run from the repo root:
    uv run python scripts/build_demo_registry.py
"""

from pathlib import Path

from ast_engine.config.logging_config import setup_logging
from ast_engine.config.registry import enrichment, utils
from ast_engine.config.registry.models import BaseDataset
from ast_engine.entry.job_builder import COMMON_REGISTRY

DATA_DIR = Path("ast_engine") / "tests" / "data"
OUTPUT_DIR = Path("ast_engine") / "tests" / "registry" / "demo"

# A demo registry is always written for Linux/macOS path rules ("posix"): that
# is what the worker's container runs, and the paths below use forward slashes.
REGISTRY_OS = "posix"


def demo_datasets() -> list[BaseDataset]:
    """One dataset per kind of analysis the sample data can show."""
    parcels = DATA_DIR / "Test_Data_PMBC_PARCEL_FABRIC.gdb" / "WHSE_CADASTRE_PMBC_PARCEL_FABRIC_POLY_FA_SVW"
    roads = DATA_DIR / "Test_Data_FOREST_TENURE_ROAD_shp" / "WHSE_FOREST_TENURE_FTEN_ROAD_SECTION_LINES_SVW.shp"
    return [
        BaseDataset(
            name="Parcel Fabric",
            datasource=parcels.as_posix(),
            aggregate_columns=["OWNER_TYPE"],
            operator={"type": "overlay"},
        ),
        BaseDataset(
            name="Private Parcels",
            datasource=parcels.as_posix(),
            definition_query="OWNER_TYPE = 'Private'",
            aggregate_columns=["OWNER_TYPE"],
            operator={"type": "overlay"},
        ),
        BaseDataset(
            name="Forest Tenure Roads",
            datasource=roads.as_posix(),
            operator={"type": "overlay"},
        ),
        BaseDataset(
            name="Forest Tenure Roads within 100 m",
            datasource=roads.as_posix(),
            operator={"type": "within_distance", "distance_m": 100},
        ),
    ]


def main() -> None:
    setup_logging()
    datasets = []
    for dataset in demo_datasets():
        enriched = enrichment.Enrich(dataset)
        enriched.enrich()
        datasets.append(enriched.build())

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    registry = utils.RegistryBuilder(datasets, os_type=REGISTRY_OS).build()
    utils.dump_yaml(registry, OUTPUT_DIR / f"{COMMON_REGISTRY}.yaml")
    print(f"Wrote {OUTPUT_DIR / (COMMON_REGISTRY + '.yaml')}: {len(datasets)} datasets")


if __name__ == "__main__":
    main()
