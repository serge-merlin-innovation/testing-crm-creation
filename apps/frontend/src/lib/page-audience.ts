/**
 * Who may reach each page `src/app/` serves. A page and its entry are one change: an unlisted path
 * falls through to gated below, so a forgotten entry silently demands a login.
 *
 * Pure — no cookies, no fetch — so both the proxy and the navbar can read it.
 */
export type PageAudience =
  | { kind: "public" }
  | { kind: "authenticated" }
  | { kind: "permission"; permission: string };

/** What the proxy resolved about the reader: their single role and that role's permissions. */
export type SessionIdentity = {
  roleName: string | null;
  permissions: string[];
};

export type Viewer = SessionIdentity & {
  isAuthenticated: boolean;
};

export const PAGE_AUDIENCE: Record<string, PageAudience> = {
  "/": { kind: "public" },
  "/login": { kind: "public" },
  "/overview": { kind: "authenticated" },
  "/profile": { kind: "authenticated" },
  "/settings": { kind: "permission", permission: "settings.manage" },
  "/users": { kind: "permission", permission: "users.manage" },
  "/permissions": { kind: "permission", permission: "roles.manage" },
  "/analytics": { kind: "permission", permission: "dashboard.aggregated" },
  // Signed-in only: the backend's 404 decides, so a hidden deal reads Not found for every role
  // instead of a redirect that would differ between "no permission" and "not staffed".
  "/deals": { kind: "authenticated" },
  "/companies": { kind: "authenticated" },
  "/contacts": { kind: "authenticated" },
  "/picklists": { kind: "permission", permission: "settings.manage" },
  "/stage-criteria": { kind: "permission", permission: "settings.manage" },
};

const GATED_BY_DEFAULT: PageAudience = { kind: "authenticated" };

export function normalizePagePath(pathname: string): string {
  const trimmed = pathname.replace(/\/+$/, "");
  return trimmed === "" ? "/" : trimmed;
}

/**
 * Longest listed prefix wins, so a nested page inherits its parent's audience. An unlisted path
 * with no listed ancestor is gated, never public. `/` is deliberately not an ancestor of anything.
 */
export function audienceFor(pathname: string): PageAudience {
  const path = normalizePagePath(pathname);
  const exact = PAGE_AUDIENCE[path];

  if (exact) {
    return exact;
  }

  let matched: { prefix: string; audience: PageAudience } | null = null;

  for (const [prefix, audience] of Object.entries(PAGE_AUDIENCE)) {
    if (prefix === "/" || !path.startsWith(`${prefix}/`)) {
      continue;
    }

    if (!matched || prefix.length > matched.prefix.length) {
      matched = { prefix, audience };
    }
  }

  return matched?.audience ?? GATED_BY_DEFAULT;
}

/** No role bypasses this, Admin included: the backend checks the same permission on every call. */
export function satisfiesAudience(audience: PageAudience, viewer: Viewer): boolean {
  if (audience.kind === "public") {
    return true;
  }

  if (!viewer.isAuthenticated) {
    return false;
  }

  if (audience.kind === "authenticated") {
    return true;
  }

  return viewer.permissions.includes(audience.permission);
}
