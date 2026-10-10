import { SESSION_COOKIE } from "./auth-routing";
import { getBackendUrl } from "./backend-url";
import { readString, readStringArray } from "./json-field";
import type { SessionIdentity } from "./page-audience";

// Server-only. `session_id` is httpOnly and opaque, so the only way to tell an admin from a
// analyst is to ask the backend. Calls FastAPI directly rather than through `backend-relay.ts`:
// that relay forwards a browser's own request, whereas this asks its own question, forwarding
// only the session cookie.
export type SessionIdentityResult =
  | { status: "identified"; identity: SessionIdentity }
  | { status: "rejected" } // the backend rejected the session: it is dead, so sign the visitor out
  | { status: "unavailable" }; // backend didn't answer; only privileged pages are refused

export const SESSION_ROLE_HEADER = "x-session-role";
export const SESSION_PERMISSIONS_HEADER = "x-session-permissions";

// A revoked session keeps its cached identity for up to a minute - safe only because FastAPI
// authorizes every data call regardless; this cache is UX, not the security boundary.
const IDENTITY_TTL_MS = 60_000;

type CachedIdentity = { identity: SessionIdentity; expiresAt: number };

const identities = new Map<string, CachedIdentity>();

export function clearSessionIdentityCache(): void {
  identities.clear();
}

export async function resolveSessionIdentity(
  sessionId: string,
): Promise<SessionIdentityResult> {
  const cached = identities.get(sessionId);

  if (cached && cached.expiresAt > Date.now()) {
    return { status: "identified", identity: cached.identity };
  }

  let response: Response;

  try {
    response = await fetch(getBackendUrl("/api/v1/users/me"), {
      // Only the session cookie is forwarded, nothing else the browser sent.
      headers: {
        Cookie: `${SESSION_COOKIE}=${sessionId}`,
        Accept: "application/json",
      },
      cache: "no-store",
    });
  } catch {
    return { status: "unavailable" };
  }

  if (response.status === 401 || response.status === 403) {
    identities.delete(sessionId);
    return { status: "rejected" };
  }

  if (!response.ok) {
    return { status: "unavailable" };
  }

  const payload: unknown = await response.json().catch(() => null);

  // A body we cannot read says the backend is misbehaving, not that the session died.
  if (readString(payload, "email") === null) {
    return { status: "unavailable" };
  }

  // Null permissions are a real answer (no role assigned), not a failure - cache it like any other.
  const identity: SessionIdentity = {
    roleName: readString(payload, "role_name"),
    permissions: readStringArray(payload, "permissions") ?? [],
  };

  identities.set(sessionId, {
    identity,
    expiresAt: Date.now() + IDENTITY_TTL_MS,
  });

  return { status: "identified", identity };
}

// Written on every allowed request, including anonymous ones: overwriting is what stops a
// hand-written `x-session-permissions` from being believed downstream.
export function applyForwardedIdentity(
  headers: Headers,
  identity: SessionIdentity | null,
): void {
  headers.set(SESSION_ROLE_HEADER, identity?.roleName ?? "");
  headers.set(SESSION_PERMISSIONS_HEADER, (identity?.permissions ?? []).join(","));
}

/** How a Server Component learns who is reading it — nothing about the session is readable from
 *  the browser, so there is no other source. */
export function readForwardedIdentity(headers: {
  get(name: string): string | null;
}): SessionIdentity {
  const roleName = headers.get(SESSION_ROLE_HEADER);
  const permissions = headers.get(SESSION_PERMISSIONS_HEADER);

  return {
    roleName: roleName ? roleName : null,
    permissions: permissions ? permissions.split(",") : [],
  };
}
