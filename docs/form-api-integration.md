# Form and API changes

This note explains the changes made to connect the AST form to the job API.

## Request flow

The form keeps its own UI-oriented values, such as `fileNumber`, `dispositionId`,
`parcelId`, `maps`, and `overlaps`. Those names do not need to be the same as
the database columns or the API model. The frontend maps them to the API field
names when it creates a `FormData` request:

| Form state | Multipart request field |
| --- | --- |
| `name` | `name` |
| `email` | `email` |
| `region` | `region` |
| source radio selection | `source` (`"1"` for TANTALIS, `"2"` for Upload) |
| `fileNumber` | `crown_file_number` |
| `dispositionId` | `disposition_number` |
| `parcelId` | `parcel_number` |
| `maps` | `generate_maps` |
| `overlaps` | `export_overlap_results` |
| `uploadFile` | `upload_file` (only when selected) |

The browser sends `FormData` as `multipart/form-data`. The frontend deliberately
does not set the `Content-Type` header: the browser must add the multipart
boundary. This lets text values and the selected file travel in one request.

## Backend model and database

`CreateJob` in `shared_models/models.py` describes the job metadata stored by
the API. The browser `File` object is not part of this Pydantic model. FastAPI
receives the uploaded file separately as `UploadFile`; this is the appropriate
boundary because a browser file is not a JSON value.

The `/api/jobs` route in `ast_api/main.py`:

1. Receives the multipart fields and optional upload.
2. Requires the three TANTALIS identifiers when `source` is `"1"`, or a file
   when `source` is `"2"`.
3. Creates a `CreateJob` from the form fields, inserts that job into SQLite,
   and adds a summary item to Redis.

The `jobs` table and its insert/query code in `ast_api/database.py` use the
same job fields. Startup adds the `source` column to an existing table if it
does not already exist. The table does not store `area_of_interest`; that field
was removed because the uploaded file is an input used to create an AOI, not a
text-valued AOI itself.

## Important limitation

The route currently reads the uploaded file into memory only to return its
filename and byte count. It does **not** save the file, validate its spatial
contents, or build an AOI from it. Likewise, the TANTALIS path currently checks
that identifiers were provided but does not look up or build the AOI. Those
processing steps still need to be implemented before a submitted job can run
an AOI analysis.

Also, `frontend/src/components/ast-form.tsx` still calls
`http://localhost:8000/api/jobs` directly. `frontend/vite.config.js` already
defines a development proxy for `/api`; changing the request to `/api/jobs`
would use that proxy and avoid hard-coding the local backend address in the
browser. Production deployments need their own API routing configuration.

## Validation performed

The focused API test suite passed with seven tests, including multipart upload
receipt and the missing-file validation case. The frontend production build
and lint command also succeeded. The build reported a large JavaScript chunk
warning; it did not fail.
