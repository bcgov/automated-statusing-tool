# Frontend Testing Guide

Testing should give us confidence that the application behaves correctly and that important reusable pieces can be changed safely.

## 1. Test behaviour, not implementation

Prefer tests that describe what a user or consumer can observe.

Good:

```text
Selecting a file displays the selected filename.
Submitting a valid form starts the status process.
An API error displays an error message.
```

Avoid tests that depend heavily on internal implementation details.

## 2. Component tests

Reusable components should be good candidates for component-level tests.

For example:

```text
FileUpload/
├── FileUpload.jsx
└── FileUpload.test.jsx
```

Potential tests:

- Renders correctly.
- Accepts the expected file type.
- Calls `onFileSelected`.
- Handles disabled state.
- Displays validation errors.

## 3. Utility tests

Pure utility functions are usually straightforward to test.

For:

```javascript
formatDate(date)
```

test important inputs and outputs directly.

## 4. Feature/integration tests

Use broader tests when multiple pieces need to work together.

For example:

```text
User
 ↓
StatusForm
 ↓
API service
 ↓
Result
```

These tests can provide confidence that the pieces are connected correctly.

## 5. Don't test everything equally

Prioritize tests around:

- Important business behaviour.
- User workflows.
- Reusable components.
- Complex logic.
- Areas that have previously caused bugs.

A simple static layout may not need extensive tests.

## 6. Tests should be maintainable

If a small UI change causes dozens of tests to fail because they depend on implementation details, the tests may be too tightly coupled to the code.

Prefer tests that remain useful while the implementation evolves.

## 7. Testing is part of design

Writing a test can reveal that a component has too many responsibilities.

If a component is extremely difficult to test, ask:

> Is the component doing too much?

Testing isn't just a final verification step. It can help us design better code.
