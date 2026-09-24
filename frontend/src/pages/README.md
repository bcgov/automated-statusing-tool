# `pages`

Contains page-level components.

Pages should primarily compose the application rather than contain every detail of its implementation.

A page might look conceptually like:

```jsx
function LandingPage() {
    return (
        <>
            <Header />
            <PageHeader />
            <StatusForm />
            <RecentRuns />
        </>
    );
}
```

## Responsibilities

Pages are appropriate for:

- Combining feature components.
- Establishing page-level layout.
- Handling page-specific concerns.
- Connecting routing to application views.

## Avoid

Avoid large pages containing:

- Hundreds of lines of UI.
- All API calls.
- Complex data transformations.
- Reusable controls.
- Large amounts of business logic.

When a page becomes difficult to understand, look for logical components or features that can be extracted.
