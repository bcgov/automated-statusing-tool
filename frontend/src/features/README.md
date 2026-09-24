# `features`

Contains functionality that is specific to the Automated Statusing Tool.

Features should be organized around user-facing or domain-specific functionality rather than generic technical concerns.

Example:

```text
features/
└── status/
    ├── StatusForm.jsx
    ├── StatusResults.jsx
    ├── statusApi.js
    └── statusUtils.js
```

## Responsibilities

A feature may contain:

- Feature-specific components.
- Feature-specific API calls.
- Feature-specific hooks.
- Feature-specific utilities.
- Feature-specific tests.

## Dependency rule

Features may use reusable components, but reusable components should not depend on features.

```text
feature → component
```

is generally appropriate.

```text
component → feature
```

is a design smell and should be questioned during review.
