import { apiFetch, clearApiCsrfToken } from "./api";
import { readString, readStringArray } from "../lib/json-field";

export class AuthenticationError extends Error {}

const SERVER_ERROR = "Something went wrong. Please try again.";

async function refusalDetail(
  response: Response,
  fallback: string,
): Promise<string> {
  // A 5xx detail may carry internals; only 4xx refusals are written for people.
  if (response.status >= 500) {
    return SERVER_ERROR;
  }

  const payload: unknown = await response.json().catch(() => null);

  // `??`, not `||`: a backend that sends an empty detail is reported as-is rather than overwritten.
  return readString(payload, "detail") ?? fallback;
}

export type LoginStep =
  | { step: "done"; recoveryCodes?: string[] }
  | { step: "code"; challenge: string }
  | { step: "enrol"; challenge: string; otpauthUri: string; qrSvg: string };

function readStep(payload: unknown): LoginStep {
  const step = readString(payload, "step");
  const challenge = readString(payload, "challenge") ?? "";

  if (step === "code") {
    return { step, challenge };
  }

  if (step === "enrol") {
    return {
      step,
      challenge,
      otpauthUri: readString(payload, "otpauth_uri") ?? "",
      qrSvg: readString(payload, "qr_svg") ?? "",
    };
  }

  const recoveryCodes = readStringArray(payload, "recovery_codes");
  return recoveryCodes ? { step: "done", recoveryCodes } : { step: "done" };
}

async function postLoginStep(path: string, init: RequestInit): Promise<LoginStep> {
  let response: Response;

  try {
    response = await apiFetch(path, {
      method: "POST",
      csrf: false,
      // A rejected password or code is a 401 the form renders inline, not a dead session.
      bounce: false,
      ...init,
    });
  } catch {
    throw new AuthenticationError("We could not reach the backend.");
  }

  if (!response.ok) {
    throw new AuthenticationError(
      await refusalDetail(response, "Check your details and try again."),
    );
  }

  return readStep(await response.json().catch(() => null));
}

export function login(email: string, password: string): Promise<LoginStep> {
  return postLoginStep("/api/v1/auth/login", {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ email, password }),
  });
}

export function submitSecondFactor(
  challenge: string,
  code: string,
  trustDevice: boolean,
): Promise<LoginStep> {
  return postLoginStep("/api/v1/auth/login/second-factor", {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ challenge, code, trust_device: trustDevice }),
  });
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
