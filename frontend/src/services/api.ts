// Calls to the AST API, made as the signed-in user.
//
// The API only answers a request that carries the access token the user was
// given when they signed in. Every call goes through apiFetch, which adds it.
import { getUserManager } from "../auth/authService";

/**
 * The signed-in user's access token, or null when nobody is signed in.
 * @returns the token to send to the API, or null
 */
async function currentAccessToken(): Promise<string | null> {
  try {
    const user = await getUserManager().getUser();
    return user && !user.expired ? user.access_token : null;
  } catch {
    // Sign-in has not been set up yet, so there is no user to ask about.
    return null;
  }
}

/**
 * fetch() for the AST API: the same call, with the user's access token added.
 * With nobody signed in the request is sent without one, and the API answers 401.
 * @param path the API path, for example "/api/jobs"
 * @param init the usual fetch options
 * @returns the API's response
 */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = await currentAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return fetch(path, { ...init, headers });
}

// How long a fetched file is kept in memory after it is handed to the browser.
const FILE_URL_LIFETIME_MS = 60_000;

/**
 * Fetch a file from the API and hand it to the browser.
 *
 * A plain link cannot do this: the browser follows a link without the access
 * token, and the API refuses it. So the file is fetched here and then opened
 * from memory.
 * @param path the API path of the file
 * @param downloadName save the file under this name. Leave out to open the
 *   file in a new tab instead.
 * @returns nothing; throws when the file could not be fetched
 */
export async function openApiFile(path: string, downloadName?: string): Promise<void> {
  // The tab is opened now, while the click is still being handled. A tab
  // opened after waiting for the file is treated as a pop-up and blocked.
  const tab = downloadName ? null : window.open("", "_blank");
  if (tab) {
    // The new page gets no handle on this one.
    tab.opener = null;
  }
  try {
    const response = await apiFetch(path);
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }
    const url = URL.createObjectURL(await response.blob());
    if (tab) {
      tab.location.href = url;
    } else {
      const link = document.createElement("a");
      link.href = url;
      link.download = downloadName ?? "";
      link.click();
    }
    window.setTimeout(() => URL.revokeObjectURL(url), FILE_URL_LIFETIME_MS);
  } catch (error) {
    tab?.close();
    throw error;
  }
}
