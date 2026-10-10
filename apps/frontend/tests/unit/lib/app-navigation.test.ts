import { describe, expect, it } from "vitest";
import {
  getAccountNavigation,
  getActiveNavigationLabel,
  getPrimaryNavigation,
} from "@/lib/app-navigation";
import type { Viewer } from "@/lib/page-audience";

const analyst: Viewer = {
  isAuthenticated: true,
  roleName: "Analyst / Associate",
  permissions: ["deals.read_staffed", "deals.edit_staffed"],
};
const readOnly: Viewer = { isAuthenticated: true, roleName: "Read-only", permissions: ["dashboard.aggregated"] };
const admin: Viewer = {
  isAuthenticated: true,
  roleName: "Admin",
  permissions: ["users.manage", "roles.manage", "settings.manage", "audit.read"],
};

function hrefs(items: { href: string }[]) {
  return items.map((item) => item.href);
}

// AUTHZ-01: the UI hides a control the role's permissions do not grant.
describe("getPrimaryNavigation", () => {
  it("offers an admin user and permission administration", () => {
    expect(hrefs(getPrimaryNavigation(admin))).toEqual(["/overview", "/users", "/permissions"]);
  });

  it("hides administration from an analyst", () => {
    expect(hrefs(getPrimaryNavigation(analyst))).toEqual(["/overview"]);
  });

  it("offers read-only only the dashboards", () => {
    expect(hrefs(getPrimaryNavigation(readOnly))).toEqual(["/overview", "/analytics"]);
  });
});

describe("getAccountNavigation", () => {
  it("gives every signed-in visitor their own profile, settings only to whoever manages them", () => {
    expect(hrefs(getAccountNavigation(analyst))).toEqual(["/profile"]);
    expect(hrefs(getAccountNavigation(admin))).toEqual(["/profile", "/settings"]);
  });
});

describe("getActiveNavigationLabel", () => {
  const items = getPrimaryNavigation(admin);

  it("keeps a nested page marked against its section", () => {
    expect(getActiveNavigationLabel("/users/42", items)).toBe("nav.users");
  });

  it("marks nothing on a page outside the catalog", () => {
    expect(getActiveNavigationLabel("/profile", items)).toBeUndefined();
  });
});
