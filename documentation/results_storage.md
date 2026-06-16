# Results Storage
S3 like storage written by ast-engine
Environment storage will be divided by environment DEV/TEST/PROD
Job storage lifecycle should be predetermined

## Proposed Data Structure
```
ast-results/
  env=dev|test|prod/
    date=YYYY-MM-DD/
      job_id=<job-id>/
        manifest.yaml
        status.json

        metadata/
          job-metadata.yaml

        request/
          request-parameters.yaml
          original/
            submitted-aoi.zip
          area-of-interest/
            aoi.gpkg
            aoi.geojson
            aoi-metadata.yaml
            aoi.gpkg.sha256
            aoi.geojson.sha256

        provenance/
          input-parameters.yaml
          config.yaml
          source-datasets.yaml
          software-bom.json

        results/
          results.raw.json
          results.summary.json
          validation-report.json

        data/
          geopackage/
            extracted.gpkg
            layers.yaml
            extracted.gpkg.sha256
          pmtiles/
            extracted.pmtiles
            tilejson.json
            extracted.pmtiles.sha256

        logs/
          job.log
```
## The Request
User request is serialized in ```request/request-parameteres.yaml``` with spatial sidecar ```request/area-of-interest/aoi.geojson```  
Draft ``` request-parameters.yaml ```
```yaml
schema_version: 1

job_id: 01JY2ABCDEF123456789
submitted_at: "2026-06-16T16:40:00Z"

request:
  request_type: ast_statusing | query-driven
  submitted_by:
    user_id: "<idir-or-service-identifier>"
    organization: "<optional>"
  purpose: "<optional business purpose or request description>"

parameters:
  source: user_submitted | bcgw-derived
  geom: "request/area-of-interest/aoi.geojson"
  source_definition: ""
  source_database: "BCGW"
  source_table: ""
  reporting_columns:
      - "FILE_NUMBER"

```

### The Request AOI
Draft contents of ```aoi-metadata.yaml```
```
Schema_version: 1

aoi:
  source: user_submitted
  original_filename: "<optional>"
  normalized_outputs:
    geopackage: aoi.gpkg
    geojson: aoi.geojson

spatial:
  original_crs: EPSG:4326
  storage_crs: EPSG:3005
  geometry_type: Polygon
  feature_count: 1
  part_count: 1
  bbox: [xmin, ymin, xmax, ymax]
  area_sq_m: 123456.78

validation:
  is_valid_geometry: true
  was_repaired: false
  repair_method: null
  has_z_values: false
  has_m_values: false
  multipart: false

lineage:
  submitted_at: "2026-06-16T16:40:00Z"
  normalized_at: "2026-06-16T16:40:05Z"
  normalized_by: ast-engine

```

## Job Manifest
The job manifest will catalog the metadata of the job, including its ID, creation and completion times, engine version, input parameters, configuration object, and source datasets. Job manifest is stored in ```job-id=<job-id>/manifest.yaml```
```yaml
schema_version: 1
job_id: 01JY2ABCDEF123456789
created_at: "2026-06-16T15:43:00Z"
completed_at: "2026-06-16T15:47:32Z"
status: succeeded

engine:
  name: ast-engine
  version: "1.4.2"

inputs:
  request_id: "..."
  request: "s3://bucket/.../request/request.yaml"
  config_object: "s3://bucket/.../provenance/config.yaml"
  source_datasets_object: "s3://bucket/.../provenance/source-datasets.yaml"
  aoi_request: 

artifacts:
  job_metadata:
    key: job-metadata.yaml
    content_type: application/yaml
  expanded_metadata:
    key: expanded-metadata.yaml
    content_type: application/yaml
  raw_results:
    key: results/results.raw.json
    content_type: application/json
    sha256: "..."
  geopackage:
    key: data/geopackage/extracted.gpkg
    content_type: application/geopackage+sqlite3
    sha256: "..."
  pmtiles:
    key: data/pmtiles/extracted.pmtiles
    content_type: application/vnd.pmtiles
    sha256: "..."

spatial:
  crs: EPSG:3005
  bbox: [xmin, ymin, xmax, ymax]
  feature_count: 1234
  geometry_types:
    - Polygon
```

## PMTiles
PMTiles are a compressed format for vector tiles that can be efficiently served over the web. They are commonly used in applications like OpenStreetMap and Mapbox. Spatial data outputs from ast-engine will be stored as PMTiles for display in results viewer. '''pmtiles.meta.yaml'' will contain eg...
- min/max zoom
- tile format: MVT/raster
- vector layer names
- bounds
- attribution

## Results
Results from the ast-engine are recorded to be consumed by a results viewer. Results are stored in raw json, summary json. Accompaning spatial results are stored in ```/data``` as PMTiles, and geopackage. Geopackage will be accompanied with a file to describe the contained layers.

```
  results/
    results.raw.json -- serialized results of ast-engine execution
    results.summary.json -- summary of raw
    validation-report.json -- unimplemented
```

