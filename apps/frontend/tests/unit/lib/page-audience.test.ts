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

const anonymous: Viewer = { isAuthenticated: false, roleName: null, permissions: [] };
const analyst: Viewer = {
  isAuthenticated: true,
  roleName: "Analyst / Associate",
  permissions: ["deals.read_staffed", "deals.edit_staffed"],
};
const readOnly: Viewer = {
  isAuthenticated: true,
  roleName: "Read-only",
  permissions: ["dashboard.aggregated"],
};
const admin: Viewer = {
  isAuthenticated: true,
  roleName: "Admin",
  permissions: ["users.manage", "roles.manage", "settings.manage", "audit.read"],
};

describe("audienceFor", () => {
  // AUTH-08/AUTH-10: the emailed links open before the person can sign in.
  it("opens the invitation and reset pages to anonymous visitors", () => {
    for (const path of ["/accept-invitation", "/reset-password"]) {
      expect(satisfiesAudience(audienceFor(path), anonymous)).toBe(true);
    }
  });

  it("reads a listed page straight off the manifest", () => {
    expect(audienceFor("/users")).toEqual({ kind: "permission", permission: "users.manage" });
    expect(audienceFor("/permissions")).toEqual({ kind: "permission", permission: "roles.manage" });
  });

  it("gives a nested page its closest listed ancestor's audience", () => {
    expect(audienceFor("/users/42/role")).toEqual({ kind: "permission", permission: "users.manage" });
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
  });

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
    { kind: "permission", permission: "users.manage" } as const,
  ])("refuses a signed-out visitor the %o page", (audience) => {
    expect(satisfiesAudience(audience, anonymous)).toBe(false);
  });

  it("opens a permission page only to a role holding that permission", () => {
    const audience = { kind: "permission", permission: "roles.manage" } as const;

    expect(satisfiesAudience(audience, admin)).toBe(true);
    expect(satisfiesAudience(audience, analyst)).toBe(false);
    expect(satisfiesAudience(audience, readOnly)).toBe(false);
  });

  it("gives no role a bypass: Admin is refused a page it lacks the permission for", () => {
    expect(
      satisfiesAudience({ kind: "permission", permission: "dashboard.aggregated" }, admin),
    ).toBe(false);
  });
});

// The forgery regressions in proxy.test.ts are never deleted. They are the only cases proving a
// client-supplied header or cookie cannot grant a reader a permission. Guarded from a different
// file so deleting proxy.test.ts outright still fails.
describe("the gate keeps its forgery regressions", () => {
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

  it.each(["x-session-permissions", "session_is_superuser"])(
    "still proves a forged %s gains nothing",
    (forgery) => {
      expect(unitTests).toContain(forgery);
    },
  );
});
