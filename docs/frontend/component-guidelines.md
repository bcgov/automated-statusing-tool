# Component Guidelines

Components are one of the main building blocks of the AST frontend.

The goal is to create components that are understandable, appropriately reusable, and easy to test.

## 1. Give every component a clear responsibility

A component should have a simple answer to:

> What does this component do?

Good:

```text
FileUpload
StatusBadge
LoadingIndicator
StatusForm
```

Less clear:

```text
ApplicationManager
DataHandler
EverythingForm
```

If a component is doing several unrelated things, consider breaking it apart.

## 2. Design components around inputs and outputs

Think of a component like a function.

Inputs are props.

Outputs are events/callbacks.

For example:

```jsx
<FileUpload
    accept=".csv"
    onFileSelected={handleFile}
/>
```

The component should not need to know what the parent intends to do with the file.

This makes it easier to reuse.

## 3. Prefer controlled behaviour where appropriate

A reusable component should generally let its parent control important application decisions.

For example:

```jsx
<StatusBadge status="complete" />
```

is more reusable than:

```jsx
<StatusBadge />
```

where the component secretly reads the application's current status from global state.

## 4. Avoid AST-specific dependencies in reusable components

This is one of the most important rules.

A component in:

```text
components/
```

should generally be usable without knowing anything about a particular AST feature.

If a component needs AST-specific knowledge, it may belong under:

```text
features/
```

instead.

## 5. Component size

There is no magic number of lines that determines whether a component is too large.

Instead, look for multiple responsibilities.

A component might be a good candidate for splitting when it contains:

- Several independent sections.
- Complex data transformations.
- Multiple unrelated pieces of state.
- Large blocks of conditional rendering.
- API calls mixed with UI rendering.
- Logic that clearly has a meaningful name.

## 6. Avoid excessive componentization

This is also important.

Do not turn this:

```jsx
<div>
    <label>Name</label>
    <input />
</div>
```

into four components unless there is a reason.

A component is useful when it creates a meaningful boundary.

## 7. Component folders

For components with multiple related files, use a folder:

```text
FileUpload/
├── FileUpload.jsx
├── FileUpload.scss
├── FileUpload.test.jsx
└── index.js
```

This keeps implementation, styling, and tests together.

## 8. Styling

Prefer component-specific SCSS for component-specific styling:

```text
FileUpload/
├── FileUpload.jsx
└── FileUpload.scss
```

Use shared/global styles only when the style is genuinely shared.

Use BC Government Design System components when an appropriate component already exists rather than recreating it.

## 9. API calls

Avoid putting raw API calls directly into reusable UI components.

Prefer:

```text
Feature
  ↓
Service
  ↓
API
```

rather than:

```text
Button
  ↓
fetch(...)
```

## 10. Questions to ask during review

When reviewing a component, ask:

- Is its purpose obvious?
- Does it have a clear API?
- Does it have too many responsibilities?
- Is it coupled to AST unnecessarily?
- Could another project use it?
- Is state located at the right level?
- Is there an existing BC Design System component that should be used?
- Would extracting something make this easier to understand?
- Conversely, would extracting something make it harder to understand?

The goal is not maximum reuse.

The goal is **useful boundaries**.
