# Data Storage Policies

## Purpose and Scope
This policy governs where the data registries and other sensitive configurations are stored, and how to reference them.

>These recommmendations more generally apply to any situation where datasets,\
> paths, configurations, or other sensitive information is referenced.

spreadsheet_ingestion has been updated to accept run arguments so actual pathing does not have to be hardcoded in.

## Policies

Any internal data pathing should not be committed to the repo. Anything containing pathing should be placed int the GSS Project folder.

## Locations

| Resource                 | Location             |
|--------------------------|----------------------|
| Legacy spreadsheets      | <tbd>                |
| Registries               | GSS Project Folder   |
| Project configurations   | GSS Project Folder   |
|

## Outputs

Outputs or results should not be saved to the repo.
