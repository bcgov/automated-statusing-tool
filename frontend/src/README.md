# `src`

Contains the application source code.

Code in this directory should be organized according to its responsibility rather than simply growing as a collection of files.

## Main areas

- `app/` — application-level setup, routing, and providers.
- `components/` — reusable UI components.
- `features/` — AST-specific functionality grouped by feature.
- `pages/` — page-level composition.
- `hooks/` — reusable React hooks.
- `services/` — API and external-service access.
- `utils/` — reusable, framework-independent helper functions.
- `styles/` — global styles, variables, and shared styling.
- `assets/` — images, icons, and other source assets.

## Rule of thumb

If you are adding a new file, first ask:

> What responsibility does this file have?

The answer should determine where it belongs.
