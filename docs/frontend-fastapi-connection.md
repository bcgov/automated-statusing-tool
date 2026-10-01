# Frontend to FastAPI Submission

## What changed

The AST form now submits to FastAPI when the user selects **Submit**. The implementation is in [ast-form.tsx](../frontend/src/components/ast-form.tsx):

- The form fields are wrapped in a `<form>` with an `onSubmit` handler. The handler prevents the browser's default page reload and sends a JSON `POST` request to `/api/jobs`.
- The request maps the form values to the field names expected by the API's `CreateJob` model. Region option IDs are converted to region labels, and the Generate Maps switch is sent as `suppress_map_creation`.
- While the request is running, Submit is disabled and displays “Submitting...”. On success, the form shows the queued job ID; on failure, it shows an error message.
- Clear Form is now a button rather than a submit button, so it only clears the form.

The request URL is relative so the browser sends it to the Vite development server. [vite.config.js](../frontend/vite.config.js) proxies requests beginning with `/api` to `http://localhost:8000`, where FastAPI is expected to be running.

The backend route is `POST /api/jobs` in [main.py](../ast_api/main.py). It validates the JSON using [CreateJob](../shared_models/models.py), writes the job to the database, adds it to the Redis queue, and returns a response containing the queued item and its `job_id`.

## Run locally

Start Redis so the API can enqueue the submitted job:

```bash
redis-server
```

From the repository root, start FastAPI in an environment with the backend dependencies installed:

```bash
uvicorn ast_api.main:app --reload --port 8000
```

In a separate terminal, start the frontend:

```bash
cd frontend
npm run dev
```

Open the Vite URL printed in the terminal and submit the form. In the browser's Network panel, the request should appear as `POST /api/jobs` with a `201` response. The form should display `Job queued: <job_id>`.

## Current limitations

The connection is wired, but some values are placeholders because the form does not collect them yet. `area_of_interest`, `output_directory`, `aoi_name`, and `aoi` are currently sent as empty values (with `aoi` as an empty object). The selected disposition ID is used for `aoi_id`; it is not the AOI geometry.

The selected upload file, email, and Export Overlap Results switch are not included in the JSON request because the current API model/route does not define a contract for them. File uploads would need a multipart upload endpoint or a separate upload flow. The payload should be completed before using this to submit real processing jobs.

## Validation

`npm run build` succeeds after these changes. The API's pytest suite was not run in this environment because `pytest` is not installed in the active Python environment.
