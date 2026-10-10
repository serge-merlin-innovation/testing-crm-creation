import { describe, expect, it } from "vitest";
import {
  getAccountNavigation,
  getActiveNavigationLabel,
  getPrimaryNavigation,
} from "@/lib/app-navigation";
import type { Viewer } from "@/lib/page-audience";

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
const superuser: Viewer = {
  isAuthenticated: true,
  roleName: "user",
  isSuperuser: true,
};

function hrefs(items: { href: string }[]) {
  return items.map((item) => item.href);
}

describe("getPrimaryNavigation", () => {
  it("offers a superuser every page", () => {
    expect(hrefs(getPrimaryNavigation(superuser))).toEqual([
      "/overview",
      "/analytics",
      "/users",
    ]);
  });

  it("hides the admin page from a plain user", () => {
    expect(hrefs(getPrimaryNavigation(user))).toEqual([
      "/overview",
      "/analytics",
    ]);
  });

  it("hides the role page from a signed-in user with no role", () => {
    expect(hrefs(getPrimaryNavigation(noRole))).toEqual(["/overview"]);
  });
});

describe("getAccountNavigation", () => {
  it("gives every signed-in visitor their own account pages", () => {
    expect(hrefs(getAccountNavigation(noRole))).toEqual([
      "/profile",
      "/settings",
    ]);
  });
});

describe("getActiveNavigationLabel", () => {
  const items = getPrimaryNavigation(superuser);

  it("marks the open page", () => {
    expect(getActiveNavigationLabel("/analytics", items)).toBe("Analytics");
  });

  it("keeps a nested page marked against its section", () => {
    expect(getActiveNavigationLabel("/users/42", items)).toBe("Users");
  });

  it("marks nothing on a page outside the catalog", () => {
    expect(getActiveNavigationLabel("/profile", items)).toBeUndefined();
  });
});
