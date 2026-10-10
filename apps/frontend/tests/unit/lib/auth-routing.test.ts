import { describe, expect, it } from "vitest";
import { DEFAULT_AUTHENTICATED_PATH, sanitizeReturnTo } from "@/lib/auth-routing";

describe("sanitizeReturnTo", () => {
  it("keeps local absolute paths and query strings", () => {
    expect(sanitizeReturnTo("/analytics?range=week")).toBe(
      "/analytics?range=week",
    );
  });

  it.each([
    undefined,
    null,
    "",
    "https://attacker.test",
    "//attacker.test/path",
    "/\\attacker.test/path",
    "/login",
    "/login?next=/analytics",
  ])("falls back for unsafe target %s", (target) => {
    expect(sanitizeReturnTo(target)).toBe(DEFAULT_AUTHENTICATED_PATH);
  });
});
