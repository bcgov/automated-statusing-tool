# Frontend Architecture

This document describes the architectural approach for the Automated Statusing Tool (AST) frontend.

The goal is not to create a complicated architecture. The goal is to make the code easy to understand, change, test, and reuse.

## 1. Think in layers

The frontend is organized approximately like this:

```text
Pages
  ↓
Features
  ↓
Reusable Components
  ↓
Hooks / Services / Utilities
```

Not every piece of code will fit perfectly into this model. Use it as a guide for deciding where new code belongs.

### Pages

Pages represent complete application views.

They should primarily compose other pieces:

```jsx
function LandingPage() {
    return (
        <>
            <PageHeader />
            <StatusForm />
            <RecentRuns />
        </>
    );
}
```

A page should not become the place where every piece of application logic lives.

### Features

Features contain AST-specific functionality.

For example:

```text
features/
└── status/
    ├── StatusForm.jsx
    ├── StatusResults.jsx
    ├── statusApi.js
    └── statusUtils.js
```

A feature can contain components, hooks, API calls, and utilities that are specific to that feature.

### Components

Components are reusable pieces of UI.

A component should be designed around a clear responsibility and communicate through props and callbacks.

```jsx
<FileUpload
    accept=".csv"
    onFileSelected={handleFile}
/>
```

The component should not need to know why AST is using the file.

### Services

Services communicate with APIs or other external systems.

Keep HTTP requests and service-specific implementation out of presentational components whenever practical.

### Hooks

Hooks contain reusable React logic.

If logic needs React state, effects, refs, or context and is used in multiple places, a custom hook may be appropriate.

### Utilities

Utilities contain framework-independent helper functions.

A pure function such as:

```javascript
formatDate(date)
```

usually belongs in `utils/`, not in a React component.

## 2. Dependency direction

Prefer dependencies to flow downward:

```text
Page
 ↓
Feature
 ↓
Component
 ↓
Utility
```

A reusable component should not import an AST-specific feature.

For example, this is a warning sign:

```javascript
// components/FileUpload/FileUpload.jsx

import { uploadASTFile } from "../../features/status/statusApi";
```

Instead, the feature should tell the component what to do:

```jsx
<FileUpload onFileSelected={handleFile} />
```

This keeps the component portable.

## 3. Reuse without premature abstraction

Do not create an abstraction simply because two pieces of code look vaguely similar.

Ask:

1. Does this have a clear responsibility?
2. Is it actually reused?
3. Is the API between the component and its consumers clear?
4. Would extracting it make the code easier to understand?

A little duplication is often preferable to an abstraction that is difficult to understand.

## 4. State

Keep state as close as practical to where it is used.

Use local component state for local UI concerns:

```javascript
const [isOpen, setIsOpen] = useState(false);
```

Do not make state global simply because it might someday be useful elsewhere.

Before introducing global state, ask:

> Who actually needs this information?

## 5. Data flow

Prefer explicit data flow:

```text
API
 ↓
Feature
 ↓
Component
 ↓
User
 ↓
Event
 ↓
Feature
 ↓
API
```

Avoid components secretly reaching into unrelated application state or performing unrelated API operations.

## 6. Composition

Prefer composing smaller pieces:

```jsx
<StatusForm>
    <FileUpload />
    <StatusOptions />
    <Button />
</StatusForm>
```

over creating a single component responsible for every part of the workflow.

At the same time, avoid excessive fragmentation. Not every `<div>` needs to become a component.

## 7. The most important question

When unsure where code belongs, ask:

> What is this code responsible for?

The answer should point toward its location.

If the answer is "displaying a reusable UI element", consider `components/`.

If it is "doing something specific to AST", consider `features/`.

If it is "talking to an API", consider `services/`.

If it is "reusable React behaviour", consider `hooks/`.

If it is "a pure helper function", consider `utils/`.
