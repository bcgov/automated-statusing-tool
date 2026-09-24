# `services`

Contains code responsible for communicating with external systems.

Typical examples include:

- REST API calls.
- Backend service clients.
- ArcGIS service access.
- Authentication-related service calls.
- External data retrieval.

## Separation of concerns

UI components should generally not contain raw API implementation.

Prefer:

```text
Component
    ↓
Feature logic
    ↓
Service/API function
    ↓
Backend
```

For example:

```javascript
export async function getStatus(id) {
    const response = await fetch(`/api/status/${id}`);

    if (!response.ok) {
        throw new Error("Failed to retrieve status");
    }

    return response.json();
}
```

Keep API-specific details here so they can be changed without rewriting UI components.
