# `app`

Contains application-level configuration and setup.

Examples include:

- Application entry points.
- Routing configuration.
- React providers.
- Global application context.
- Application-wide initialization.

## What belongs here?

Code that configures or composes the application as a whole.

## What does not belong here?

Feature-specific UI or business logic should generally live under `features/`.

Reusable UI should generally live under `components/`.

Avoid turning this folder into a catch-all for code that does not have an obvious home.
