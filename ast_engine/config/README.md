# Spreadsheet Ingestion

## Purpose

Spreadsheet Ingestion is designed to take the legacy one_status_xxxxx.xlsx spreadsheets from the existing Automated Status Tool (AST) and convert them to a data registry model enforeced by pydantic.
This allows representations to be stored externally in .yaml files and loaded into memory quickly at runtime.

The Ingestion process has several phases:
* Ingestion: ingests the spreadsheets into a simple list[dict] format
* Hydration: Loads the simple data into list[BaseDataset] where BaseDataset is a pydantic model.
* Enrichment: Add additional parameters not present in the legacy tables. This will include inferring operation type, applying a unique ID, getting the crs, and recording data type
* Model Dump: Dumps the generated model to yaml.
