import { apiFetch, clearApiCsrfToken } from "./api";
import { readString } from "../lib/json-field";

export class AuthenticationError extends Error {}

async function refusalDetail(
  response: Response,
  fallback: string,
): Promise<string> {
  const payload: unknown = await response.json().catch(() => null);

  // `??`, not `||`: a backend that sends an empty detail is reported as-is rather than overwritten.
  return readString(payload, "detail") ?? fallback;
}

export async function login(email: string, password: string): Promise<void> {
  let response: Response;

  try {
    response = await apiFetch("/api/v1/auth/login", {
      method: "POST",
      csrf: false,
      // A rejected password is a 401 the form renders inline, not a dead session.
      bounce: false,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ email, password }),
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
