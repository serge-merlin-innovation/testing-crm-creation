"use client";

import { LOGIN_PATH, sanitizeReturnTo } from "../lib/auth-routing";
import { readString } from "../lib/json-field";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);
const CSRF_HEADER = "X-CSRF-Token";
const CSRF_REFRESH_PATH = "/api/v1/auth/refresh-csrf";

export type ApiRequestInit = RequestInit & {
  /**
   * Set to false only for deliberately unauthenticated endpoints such as
   * login. Unsafe session-authenticated requests are protected by default.
   */
  csrf?: boolean;
  /**
   * Set to false for calls that present their own 401 (login rejecting
   * credentials) or that navigate themselves afterwards (logout).
   */
  bounce?: boolean;
};

let csrfToken: string | null = null;
let csrfRefresh: Promise<string | null> | null = null;

function browserFetch(
  path: string,
  init: RequestInit = {},
  includeCsrf = false,
): Promise<Response> {
  // Backend paths are served by this app's own origin and relayed on from there, so the request
  // stays same-origin. Reducing to path and query first means a caller passing an absolute URL
  // cannot send the session cookie somewhere else.
  const requestedUrl = new URL(path, "http://frontend.internal");
  const headers = new Headers(init.headers);

  if (includeCsrf && csrfToken) {
    headers.set(CSRF_HEADER, csrfToken);
  }

  return fetch(`${requestedUrl.pathname}${requestedUrl.search}`, {
    ...init,
    credentials: "same-origin",
    headers,
  });
}

async function csrfTokenIn(response: Response): Promise<string | null> {
  return readString(await response.clone().json().catch(() => null), "csrf_token");
}

async function refreshCsrfToken(): Promise<string | null> {
  const response = await browserFetch(CSRF_REFRESH_PATH, {
    method: "POST",
  });

  if (!response.ok) {
    csrfToken = null;
    return null;
  }

  csrfToken = await csrfTokenIn(response);
  return csrfToken;
}

function getFreshCsrfToken(): Promise<string | null> {
  if (!csrfRefresh) {
    csrfRefresh = refreshCsrfToken().finally(() => {
      csrfRefresh = null;
    });
  }

  return csrfRefresh;
}

// Only FastAPI can reject a stale session. Gateway failures stay distinct so an outage does not
// eject the visitor to login while the session cookie still exists.
function bounceToLogin(): void {
  if (typeof window === "undefined") {
    return;
  }

  const { origin, pathname, search } = window.location;

  if (pathname === LOGIN_PATH) {
    return;
  }

  csrfToken = null;

  const loginUrl = new URL(LOGIN_PATH, origin);
  loginUrl.searchParams.set("next", sanitizeReturnTo(`${pathname}${search}`));
  window.location.replace(loginUrl.toString());
}

// The browser's only API path: same-origin sessions, automatic CSRF refresh, and stale-session handling.
export async function apiFetch(
  path: string,
  { csrf = true, bounce = true, ...init }: ApiRequestInit = {},
): Promise<Response> {
  const protectWithCsrf =
    csrf && !SAFE_METHODS.has((init.method ?? "GET").toUpperCase());

  if (protectWithCsrf && !csrfToken) {
    await getFreshCsrfToken();
  }

  let response = await browserFetch(path, init, protectWithCsrf);

  if (protectWithCsrf && response.status === 403) {
    const refreshedToken = await getFreshCsrfToken();

    if (refreshedToken) {
      response = await browserFetch(path, init, protectWithCsrf);
    }
  }

  const returnedToken = await csrfTokenIn(response);

  if (returnedToken) {
    csrfToken = returnedToken;
  }

  if (bounce && response.status === 401) {
    bounceToLogin();
  }

  return response;
}

export function clearApiCsrfToken(): void {
  csrfToken = null;
}
