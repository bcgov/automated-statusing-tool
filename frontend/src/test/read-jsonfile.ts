async function loadJSON<T>(
  url: string,
  validate?: (data: unknown) => data is T,
): Promise<T> {
  const response = await fetch(url, { cache: 'no-store' });
  if (!response.ok) {
    throw new Error(`Failed to load ${url}: HTTP ${response.status} ${response.statusText}`);
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new Error(`Response from ${url} was not valid JSON`);
  }

  if (validate && !validate(data)) {
    throw new Error(`JSON from ${url} did not match the expected shape`);
  }
  return data as T;
}

export { loadJSON };