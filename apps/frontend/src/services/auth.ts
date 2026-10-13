import { apiFetch, clearApiCsrfToken } from "./api";
import { readString, readStringArray } from "../lib/json-field";

export class AuthenticationError extends Error {
  /** A service fault or an unreachable backend: the same submission may work a moment later. */
  constructor(
    message: string,
    readonly retryable = false,
  ) {
    super(message);
  }
}

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
    throw new AuthenticationError("We could not reach the backend.", true);
  }

  if (!response.ok) {
    throw new AuthenticationError(
      await passwordRefusal(response, "Check your details and try again."),
      response.status >= 500,
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

export type Invitation = { email: string; firstName: string | null };

/** A 410 is the backend's own "expired or already used" sentence, shown as is. */
export async function readInvitation(token: string): Promise<Invitation> {
  let response: Response;
  try {
    response = await apiFetch(`/api/v1/auth/invitations?token=${encodeURIComponent(token)}`, { bounce: false });
  } catch {
    throw new AuthenticationError("We could not reach the backend.");
  }
  if (!response.ok) {
    throw new AuthenticationError(await refusalDetail(response, "This invitation link is not valid."));
  }
  const payload: unknown = await response.json().catch(() => null);
  return { email: readString(payload, "email") ?? "", firstName: readString(payload, "first_name") ?? null };
}

/** Sets the password, then hands back the enrolment step that the login form finishes. */
export function acceptInvitation(token: string, password: string): Promise<LoginStep> {
  return postLoginStep("/api/v1/auth/invitations/accept", {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, password }),
  });
}

async function postAccountForm(path: string, body: unknown, fallback: string): Promise<void> {
  let response: Response;
  try {
    response = await apiFetch(path, {
      method: "POST",
      csrf: false,
      bounce: false,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new AuthenticationError("We could not reach the backend.");
  }
  if (!response.ok) {
    throw new AuthenticationError(await passwordRefusal(response, fallback));
  }
}

/** A policy refusal arrives as `errors[{field: "password", message}]`; other refusals as `detail`. */
async function passwordRefusal(response: Response, fallback: string): Promise<string> {
  if (response.status >= 500) {
    return SERVER_ERROR;
  }
  const payload: unknown = await response.json().catch(() => null);
  const errors = typeof payload === "object" && payload !== null ? (payload as { errors?: unknown }).errors : null;
  if (Array.isArray(errors)) {
    const message = errors.map((error) => readString(error, "message")).find((text) => text);
    if (message) return message;
  }
  return readString(payload, "detail") ?? fallback;
}

export function requestPasswordReset(email: string): Promise<void> {
  return postAccountForm("/api/v1/auth/password/forgot", { email }, "We could not send the link.");
}

export function resetPassword(token: string, password: string): Promise<void> {
  return postAccountForm("/api/v1/auth/password/reset", { token, password }, "We could not change the password.");
}
