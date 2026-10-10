/**
 * Who may reach each page `src/app/` serves. A page and its entry are one change: an unlisted path
 * falls through to gated below, so a forgotten entry silently demands a login. Nothing checks it.
 *
 * Pure — no cookies, no fetch — so both the proxy and the navbar can read it.
 */
export type PageAudience =
  | { kind: "public" }
  | { kind: "authenticated" }
  | { kind: "admin" }
  | { kind: "role"; role: string };

/**
 * What the proxy resolved about the reader. `roleName` is null for a user with no role row, which
 * is a user an administrator created without assigning one.
 *
 * It lives here rather than beside the resolve because this module is pure: a client component can
 * take an identity as props without reaching into the server-only module that produces one.
 */
export type SessionIdentity = {
  roleName: string | null;
  isSuperuser: boolean;
};

export type Viewer = SessionIdentity & {
  isAuthenticated: boolean;
};

export const PAGE_AUDIENCE: Record<string, PageAudience> = {
  "/": { kind: "public" },
  "/login": { kind: "public" },
  "/overview": { kind: "authenticated" },
  "/profile": { kind: "authenticated" },
  "/settings": { kind: "authenticated" },
  "/users": { kind: "admin" },
  "/analytics": { kind: "role", role: "user" },
};

const GATED_BY_DEFAULT: PageAudience = { kind: "authenticated" };

export function normalizePagePath(pathname: string): string {
  const trimmed = pathname.replace(/\/+$/, "");
  return trimmed === "" ? "/" : trimmed;
}

/**
 * Longest listed prefix wins, so a nested page inherits its parent's audience — `/users/42` is as
 * admin-only as `/users`. An unlisted path with no listed ancestor is gated, never public: a
 * forgotten entry then costs a redirect instead of leaking a page.
 *
 * `/` is deliberately not an ancestor of anything. As a prefix it would cover the whole site and
 * make every page public.
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

/**
 * A superuser satisfies every audience, matching the backend, where `is_superuser` bypasses role
 * checks. Anyone else must hold exactly the role the page names — roles are mutually exclusive
 * (`user.role_id` is a single nullable column), so there is no hierarchy to walk.
 */
export function satisfiesAudience(
  audience: PageAudience,
  viewer: Viewer,
): boolean {
  if (audience.kind === "public") {
    return true;
  }

  if (!viewer.isAuthenticated) {
    return false;
  }

  if (viewer.isSuperuser || audience.kind === "authenticated") {
    return true;
  }

  return audience.kind === "role" && viewer.roleName === audience.role;
}
