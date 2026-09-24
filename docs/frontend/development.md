# Frontend Development Guide

This document describes the development practices for the AST frontend.

These are guidelines intended to help the team build consistent code while developing frontend skills.

## 1. Before writing code

Before creating a new component or utility, look for existing functionality.

Check:

1. BC Government Design System components.
2. Existing AST components.
3. Existing feature components.
4. Existing hooks.
5. Existing utilities.

Do not create a second version of something that already exists without a reason.

## 2. Start simple

When implementing functionality:

1. Make the simplest working version.
2. Confirm the behaviour.
3. Identify repeated or complicated logic.
4. Refactor where there is a clear benefit.
5. Add tests where appropriate.

Do not try to predict every future use case.

## 3. Keep responsibilities separate

A useful mental model is:

```text
UI
 ↓
Feature logic
 ↓
Services
 ↓
External systems
```

For example:

```text
StatusForm.jsx
    ↓
useStatus.js
    ↓
statusApi.js
    ↓
Backend API
```

The exact structure can vary, but the responsibilities should remain understandable.

## 4. Naming

Names should describe what something does.

Prefer:

```text
FileUpload
StatusResults
getStatus
formatDate
useStatus
```

Avoid vague names:

```text
Helper
Manager
Thing
DataHandler
Utils2
NewComponent
```

If naming something is difficult, that may indicate that its responsibility is unclear.

## 5. State

Start with local state.

Move state upward only when another component needs it.

Use shared/global state only when there is a demonstrated need.

Avoid creating global state as a default pattern.

## 6. Effects

Do not automatically reach for `useEffect`.

Ask first:

> Is this actually a side effect?

Calculating a value from existing state generally does not require an effect.

For example, prefer:

```javascript
const visibleItems = items.filter(item => item.visible);
```

over storing `visibleItems` separately and synchronizing it with `useEffect`.

## 7. Pull complicated logic out of JSX

Avoid deeply nested logic directly inside JSX.

Instead of:

```jsx
{items.filter(...).map(...).filter(...).map(...)}
```

consider giving the operation a meaningful name.

```javascript
const visibleItems = getVisibleItems(items);
```

Then:

```jsx
{visibleItems.map(...)}
```

This improves readability and makes logic easier to test.

## 8. Git and pull requests

Keep changes focused.

A PR should ideally answer:

> What problem does this change solve?

Avoid combining unrelated refactoring, feature work, and formatting changes unless there is a reason.

PRs are also a learning tool.

Reviewers should explain why a change is recommended, not simply say that something is "wrong."

## 9. Refactoring is expected

It is normal for the first implementation not to be perfect.

A healthy workflow is:

```text
Build
 ↓
Review
 ↓
Learn
 ↓
Refactor
 ↓
Document
```

Do not optimize for never having to change code.

Optimize for being able to change it safely.

## 10. When you are unsure

Ask the team.

Architectural questions are worth discussing before a pattern spreads.

Useful questions include:

- Where should this code live?
- Is this a component or a feature?
- Should this state be shared?
- Is this abstraction actually reusable?
- Is there an existing component we should use?
- Does this API call belong in a service?

A short discussion early can prevent a lot of cleanup later.
