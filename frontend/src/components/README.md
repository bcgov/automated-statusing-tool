# `components`

Contains reusable UI components.

Components in this folder should be as independent from AST-specific business logic as practical.

## Good candidates

Examples include:

- Buttons and controls.
- File upload controls.
- Loading indicators.
- Error messages.
- Empty states.
- Status badges.
- Form elements.
- Reusable layout components.

## Component design

A reusable component should communicate through props and callbacks rather than reaching directly into feature-specific state.

For example:

```jsx
<FileUpload
    accept=".csv"
    onFileSelected={handleFile}
/>
```

The component should not need to know that the file is being uploaded for AST.

## Folder convention

For components with multiple files:

```text
ComponentName/
├── ComponentName.jsx
├── ComponentName.scss
├── ComponentName.test.jsx
└── index.js
```

Do not create a component solely to avoid writing a few lines of JSX. Extract components when they have a clear responsibility, are reused, or make a parent component substantially easier to understand.
