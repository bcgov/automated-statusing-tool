# `assets`

Contains source assets used by the frontend.

Examples include:

- Images.
- Icons.
- SVG files.
- Fonts that are explicitly required by the application.
- Other static resources imported by source code.

## Guidelines

Give assets descriptive names.

Avoid storing assets here that are only used as deployment-time static files; those may belong in `public/` instead.

When an asset is associated with a specific component and does not need to be shared, consider keeping it with that component.
