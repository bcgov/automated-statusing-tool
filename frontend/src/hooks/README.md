# `hooks`

Contains reusable React hooks.

Hooks are appropriate when logic needs to be reused across components and that logic depends on React functionality such as state, effects, refs, or context.

Examples:

```text
useApi.js
useDebounce.js
useFileUpload.js
```

## Guidelines

A custom hook should have a clear purpose.

Prefer:

```javascript
const { data, loading, error } = useApi(url);
```

over creating a hook that combines many unrelated responsibilities.

If logic does not need React features, consider putting it in `utils/` instead.
