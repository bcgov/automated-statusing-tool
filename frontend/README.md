# Frontend

This directory contains the frontend application for the Automated Statusing Tool (AST).

The frontend is organized to keep reusable UI components, application features, pages, data access, and supporting utilities separate.

## Architecture

The intended dependency direction is:

```text
pages
  ↓
features
  ↓
components
  ↓
hooks / services / utils
```

The exact dependency will vary by feature, but lower-level reusable components should not depend on AST-specific features or pages.

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and Oxlint's TypeScript related rules in your project.

## Development 
**Start with one workflow**
 Submission--> wait progress --> see job finished --> results

**Principles**
1. Build narrow function first
2. Build reusable components and paterns we can recycle
    eg. fetch("api/job/id)  --> jobApi.getJob(id)
3. Shared UX
4. Predifined organization (division of components)eg. type vs function

## Some features
**Job Submission**
User submits job for analysis
```python
class AstJob(BaseModel):
    job_id: UUID
    registries: Iterable[tuple[str, Any]]
    created_at: Optional[str] = None
    user: str
    aoi_id: str
    aoi_name: str
    aoi: dict[str, Any] #gdf.to_json()
    status: Optional [JobStatus]
```
1. Static AOI to start
2. Futre Draw AOI
3. Future Upload AOI
4. Future Validate Geometry
5. Future AOI from definition query

**User Context**  
1. jobs belong to a user or user group [fetch from api]
2. user can see all their jobs with status eg.
```python
    QUEUED = "Queued"
    PROCESSING = "Processing"
    PUBLISHING = "Publishing"
    COMPLETED = "Completed"
    FAILED = "Failed"
```
3. user can access the job results

**Results**  
Results should be dynamicly presented from the analysis results data and spatial exported to s3 from the engine; keeping results design seperated from engine. Data remains the same... the view is updated.

1. summary of job input
2. summary of outputs
3. future sharing results


**Registries**
1. Registries currently will probably be [{registry_id: registry name}] retieved from api.
2. Future registry viewer
3. Future registries editor/creator

**Maps**  
Future - maps likely needed in two spots
1. AOI input viewer
2. Results viewer (current thinking is PMTiles)


