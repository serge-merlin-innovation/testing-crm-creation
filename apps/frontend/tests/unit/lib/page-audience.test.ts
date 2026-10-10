import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { DEFAULT_AUTHENTICATED_PATH } from "@/lib/auth-routing";
import {
  audienceFor,
  normalizePagePath,
  satisfiesAudience,
  type Viewer,
} from "@/lib/page-audience";

const anonymous: Viewer = {
  isAuthenticated: false,
  roleName: null,
  isSuperuser: false,
};
const noRole: Viewer = {
  isAuthenticated: true,
  roleName: null,
  isSuperuser: false,
};
const user: Viewer = {
  isAuthenticated: true,
  roleName: "user",
  isSuperuser: false,
};
const reviewer: Viewer = {
  isAuthenticated: true,
  roleName: "reviewer",
  isSuperuser: false,
};
const superuser: Viewer = {
  isAuthenticated: true,
  roleName: "user",
  isSuperuser: true,
};

describe("audienceFor", () => {
  it("reads a listed page straight off the manifest", () => {
    expect(audienceFor("/users")).toEqual({ kind: "admin" });
    expect(audienceFor("/analytics")).toEqual({ kind: "role", role: "user" });
  });

  it("gives a nested page its closest listed ancestor's audience", () => {
    expect(audienceFor("/users/42/permissions")).toEqual({ kind: "admin" });
  });

  it("gates an unlisted path rather than exposing it", () => {
    expect(audienceFor("/reports")).toEqual({ kind: "authenticated" });
  });

  it("does not let the home page make the whole site public", () => {
    expect(audienceFor("/")).toEqual({ kind: "public" });
    expect(audienceFor("/settings")).not.toEqual({ kind: "public" });
  });

  it("ignores a trailing slash", () => {
    expect(normalizePagePath("/users/")).toBe("/users");
    expect(audienceFor("/users/")).toEqual({ kind: "admin" });
  });

  // Every visitor the proxy turns away lands here. A role or admin audience would bounce anyone
  // without it straight back out, and gating the landing page above someone's audience loops.
  it("keeps the landing path reachable by every signed-in visitor", () => {
    expect(audienceFor(DEFAULT_AUTHENTICATED_PATH)).toEqual({ kind: "authenticated" });
  });
});

describe("satisfiesAudience", () => {
  it("lets anyone reach a public page", () => {
    expect(satisfiesAudience({ kind: "public" }, anonymous)).toBe(true);
  });

  it.each([
    { kind: "authenticated" } as const,
    { kind: "admin" } as const,
    { kind: "role", role: "user" } as const,
  ])("refuses a signed-out visitor the %o page", (audience) => {
    expect(satisfiesAudience(audience, anonymous)).toBe(false);
  });

  it("lets every signed-in visitor reach an authenticated page", () => {
    expect(satisfiesAudience({ kind: "authenticated" }, noRole)).toBe(true);
  });

  it("keeps an admin page for superusers", () => {
    expect(satisfiesAudience({ kind: "admin" }, superuser)).toBe(true);
    expect(satisfiesAudience({ kind: "admin" }, user)).toBe(false);
  });

  it("matches a role page on the role name alone", () => {
    const audience = { kind: "role", role: "user" } as const;

    expect(satisfiesAudience(audience, user)).toBe(true);
    expect(satisfiesAudience(audience, reviewer)).toBe(false);
    expect(satisfiesAudience(audience, noRole)).toBe(false);
  });

  it("lets a superuser through a role page they do not hold", () => {
    expect(
      satisfiesAudience({ kind: "role", role: "reviewer" }, superuser),
    ).toBe(true);
  });
});

// The two forgery regressions in proxy.test.ts are never deleted. They are the only cases proving
// a client-supplied header or cookie cannot promote a reader to superuser, and nothing else in the
// suite would notice their absence. Guarded from a different file so deleting proxy.test.ts
// outright still fails.
describe("the gate keeps its forgery regressions", () => {
  // Every unit test but this one, so a rename of the file holding these cases does not break the
  // guard - and so the guard cannot satisfy itself with the literals in its own `it.each` below.
  const unitTests = readdirSync(resolve(process.cwd(), "tests/unit"), {
    recursive: true,
    withFileTypes: true,
  })
    .filter(
      (entry) =>
        entry.isFile() &&
        entry.name.endsWith(".test.ts") &&
        resolve(entry.parentPath, entry.name) !== import.meta.filename,
    )
    .map((entry) => readFileSync(resolve(entry.parentPath, entry.name), "utf8"))
    .join("\n");

  it.each(["x-session-superuser", "session_is_superuser"])(
    "still proves a forged %s gains nothing",
    (forgery) => {
      expect(unitTests).toContain(forgery);
    },
  );
});
