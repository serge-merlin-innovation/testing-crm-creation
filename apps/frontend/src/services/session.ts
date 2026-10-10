import { parseSessionStatus, type SessionStatus } from "../lib/session-timer";
import { apiFetch } from "./api";

async function statusFrom(response: Response): Promise<SessionStatus | null> {
  if (!response.ok) {
    return null;
  }
  return parseSessionStatus(await response.json().catch(() => null));
}

async function revokedCount(response: Response): Promise<number> {
  if (!response.ok) {
    throw new Error("We could not end the sessions.");
  }
  const payload: unknown = await response.json().catch(() => null);
  const revoked = typeof payload === "object" && payload !== null ? (payload as { revoked?: unknown }).revoked : 0;
  return typeof revoked === "number" ? revoked : 0;
}

/** Reading the status is not activity on the server, and an ended session is reported, not followed. */
export async function fetchSessionStatus(): Promise<SessionStatus | null> {
  return statusFrom(await apiFetch("/api/v1/auth/session", { bounce: false }));
}

export async function renewSession(): Promise<SessionStatus | null> {
  return statusFrom(await apiFetch("/api/v1/auth/session/renew", { method: "POST", bounce: false }));
}

export async function logoutEverywhere(): Promise<number> {
  return revokedCount(await apiFetch("/api/v1/auth/logout-everywhere", { method: "POST", bounce: false }));
}

export async function revokeUserSessions(userId: number): Promise<number> {
  return revokedCount(await apiFetch(`/api/v1/users/${userId}/sessions`, { method: "DELETE" }));
}
