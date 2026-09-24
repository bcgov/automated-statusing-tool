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

## Guiding principles

- Keep components focused on a clear responsibility.
- Prefer reusable components over duplicated UI.
- Keep API/data-access code separate from presentation.
- Keep state as local as practical.
- Use BC Government Design System components where appropriate.
- Avoid premature abstraction; extract components when there is a clear responsibility or reuse case.
- Prefer simple, understandable code over clever abstractions.

See `docs/` for project-wide frontend conventions and architecture guidance.
