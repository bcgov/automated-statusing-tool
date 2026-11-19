// src/authConfig.ts
import { WebStorageStateStore, UserManagerSettings } from 'oidc-client-ts';



function getBaseUrl(): string {
  // Browser runtime: trust the Route/Ingress host
  //if (typeof window !== 'undefined' && window.location?.origin) {
  //  return window.location.origin;
  //}
  // Non-browser (tests/SSR) or local dev fallback
  //return import.meta.env.VITE_BASE_URL || 'http://localhost:8080';
  console.log(window.location.origin)
  return window.location.origin;
}



export async function fetchOidcConfig(): Promise<UserManagerSettings> {
  try {


    const baseUrl = getBaseUrl();
    //const CALLBACK_PATH = import.meta.env.VITE_AUTH_CALLBACK_PATH || '/callback';
    //const callbackUrl = `${baseUrl.replace(/\/+$/, '')}${CALLBACK_PATH}`;
    const callbackUrl = `${window.location.origin}${import.meta.env.VITE_AUTH_CALLBACK_PATH ?? '/callback'}`;


    return {
      authority: 'https://dev.loginproxy.gov.bc.ca/auth/realms/standard',
      client_id: 'automated-status-tool-6604',
      redirect_uri: callbackUrl,
      response_type: 'code',
      scope: 'openid profile email',
      post_logout_redirect_uri: baseUrl,
      userStore: new WebStorageStateStore({ store: window.localStorage }),
    };

    
  } catch (error) {
    console.error('Critical Error: Could not resolve runtime OIDC settings. Falling back to local defaults.', error);

    const baseUrl = getBaseUrl();
    const callbackUrl = `${window.location.origin}${import.meta.env.VITE_AUTH_CALLBACK_PATH ?? '/callback'}`;

    return {
      authority: 'https://dev.loginproxy.gov.bc.ca/auth/realms/standard',
      client_id: 'automated-status-tool-6604',
      redirect_uri: callbackUrl,
      response_type: 'code',
      scope: 'openid profile email',
      post_logout_redirect_uri: baseUrl,
      userStore: new WebStorageStateStore({ store: window.localStorage }),
    };
  }
}