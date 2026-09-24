# `public`

Contains static files that are served directly by the application without being processed as JavaScript or imported through the normal source pipeline.

Use this directory sparingly.

## Appropriate uses

Examples include:

- Browser favicons.
- Static files that need a stable public URL.
- Files required by external tooling that cannot be imported through the application bundle.

## Prefer `src/assets/` when

An asset is part of the application and can be imported by a component or module.

Keeping application assets in `src/assets/` allows the build system to process and fingerprint them appropriately.
