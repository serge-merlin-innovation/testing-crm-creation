import { apiFetch, clearApiCsrfToken } from "./api";
import { readString } from "../lib/json-field";

export class AuthenticationError extends Error {}

// The only host we will send a user to for Microsoft sign-in - pins the origin so a
// misconfigured or compromised backend can't turn this into an open redirect.
const MICROSOFT_AUTHORIZE_ORIGIN = "https://login.microsoftonline.com";

async function refusalDetail(
  response: Response,
  fallback: string,
): Promise<string> {
  const payload: unknown = await response.json().catch(() => null);

  // `??`, not `||`: a backend that sends an empty detail is reported as-is rather than overwritten.
  return readString(payload, "detail") ?? fallback;
}

export async function login(
  username: string,
  password: string,
): Promise<void> {
  let response: Response;

  try {
    response = await apiFetch("/api/v1/auth/login", {
      method: "POST",
      csrf: false,
      // A rejected password is a 401 the form renders inline, not a dead session.
      bounce: false,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username, password }),
    });
  } catch {
    throw new AuthenticationError("We could not reach the backend.");
  }

  if (!response.ok) {
    throw new AuthenticationError(
      await refusalDetail(response, "Check your details and try again."),
    );
  }
}

export async function logout(): Promise<void> {
  let response: Response;

  try {
    response = await apiFetch("/api/v1/auth/logout", {
      method: "POST",
      // The caller navigates to the login page once the session is gone.
      bounce: false,
    });
  } catch {
    throw new AuthenticationError("We could not reach the backend.");
  }

  // An expired or already-revoked session has the same end state for the client.
  if (response.status === 401) {
    clearApiCsrfToken();
    return;
  }

  if (!response.ok) {
    throw new AuthenticationError(
      await refusalDetail(response, "We could not log you out."),
    );
  }

  clearApiCsrfToken();
}

// The endpoint returns JSON so the browser, not fetch, performs the cross-origin navigation.
export async function getMicrosoftAuthorizeUrl(
  returnTo: string,
): Promise<string> {
  let response: Response;

  try {
    response = await apiFetch(
      `/api/v1/auth/oauth/microsoft?redirect_uri=${encodeURIComponent(returnTo)}`,
      {
        // An unauthenticated GET that renders its own error inline.
        csrf: false,
        bounce: false,
      },
    );
  } catch {
    throw new AuthenticationError("We could not reach the backend.");
  }

  if (!response.ok) {
    throw new AuthenticationError("We could not start Microsoft sign-in.");
  }

  const authorizeUrl = readString(
    await response.json().catch(() => null),
    "url",
  );

  if (!authorizeUrl) {
    throw new AuthenticationError("We could not start Microsoft sign-in.");
  }

  let parsed: URL;

  try {
    parsed = new URL(authorizeUrl);
  } catch {
    throw new AuthenticationError("We could not start Microsoft sign-in.");
  }

  if (parsed.origin !== MICROSOFT_AUTHORIZE_ORIGIN) {
    throw new AuthenticationError("We could not start Microsoft sign-in.");
  }

  return authorizeUrl;
}

export function describeOAuthError(
  reason: string | undefined,
  provider: string | undefined,
): string {
  const providerName = provider === "microsoft" ? "Microsoft" : "provider";

  switch (reason) {
    case "not_provisioned":
      return `This ${providerName} account is not linked to a workspace account. Ask an administrator to link it.`;
    case "invalid_state":
      return "That sign-in link expired. Please try again.";
    case "provider_mismatch":
      return "That sign-in attempt did not match. Please try again.";
    default:
      return `We could not complete ${providerName} sign-in. Please try again.`;
  }
}
