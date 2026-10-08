# `utils`

Contains small, reusable helper functions that do not depend on React or a particular UI component.

Examples include:

- Date formatting.
- String manipulation.
- Data transformation.
- Validation helpers.
- Pure calculation functions.

A utility should generally be easy to test independently.

## What does not belong here?

Do not use this folder as a dumping ground for code that has no obvious home.

If a function is specific to a feature, keep it with that feature.

If it is a React hook, put it in `hooks/`.

If it communicates with an API, put it in `services/`.
