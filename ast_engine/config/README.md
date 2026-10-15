# Spreadsheet Ingestion

## Purpose

Spreadsheet Ingestion is designed to take the legacy one_status_xxxxx.xlsx spreadsheets from the existing Automated Status Tool (AST) and convert them to a data registry model enforeced by pydantic.
This allows representations to be stored externally in .yaml files and loaded into memory quickly at runtime.

## File Reference

```
ast_engine/config
├── registry/ ──────────────── Utilities and functional components
│   ├── enrichment.py ──────── Used to derive additional parameters
│   ├── models.py ──────────── pydantic models for RegistryDataset
│   ├── query.py ───────────── Translates 'Definition Queries' and creates a where model
│   └── utils.py ───────────── Utilities for loading/dumping/translating data
├── README.md ──────────────── This file
├── drive_map.conf ─────────── NOT PROVIDED: a drive map for windows network shares in linux
├── drive_mapper.sh ────────── Maps windows shares to linux
├── logging_config.py ──────── Helper to set logging parameters
├── registry_load_demo.py ──── Shows how to load generated registries
├── settings.py ──────────────
├── spreadsheet_ingestion.py ─ Shows how to translate legacy spreadsheets to registries
└── startup.py ─────────────── App initialization
```

## How to run

Registry builds are OS specific. filesystem pathing will not work across OS types. Use the instructions below to build test registries for your OS.

### Linux
```
You must provide your own `drive_map.conf`.
```
Be sure to run `drive_mapper.sh` first to ensure the network drives are correctly mapped.
If you do not, then enrichment will not work correctly.

### Windows and Linux
run `spreadsheet_ingestion.py`. This will run through the test spreadsheets and generate data registries appropriate for your operating system.

## How it works

### Configuration
* `drive_map.conf` contains the drive mappings required for linux

### Inputs
`spreadsheet_io`: key:value pairs of input spreadsheets and output yamls


### Processing overview
The Ingestion process has several phases:
* Ingestion: ingests the spreadsheets into a simple list[dict] format
* Hydration: Loads the simple data into list[BaseDataset] where BaseDataset is a pydantic model.
* Enrichment: Add additional parameters not present in the legacy tables. This will include inferring operation type, applying a unique ID, getting the crs, and recording data type
* Model Dump: Dumps the generated model to yaml.

### Outputs

Registry .yaml files as indicated in the spreadsheet_io variable
These can then be used to test later stages.