import { describe, expect, it } from "vitest";
import { getPrimaryNavigation } from "@/lib/app-navigation";
import type { Viewer } from "@/lib/page-audience";
import { audienceFor, satisfiesAudience } from "@/lib/page-audience";
import { defaultPeriod, hasRecordAccess, pivot, winLossQuery } from "@/lib/reports";

const readOnly: Viewer = { isAuthenticated: true, roleName: "Read-only", permissions: ["dashboard.aggregated"] };
const partner: Viewer = {
  isAuthenticated: true,
  roleName: "Partner",
  permissions: ["deals.read_staffed", "dashboard.aggregated", "dashboard.firm", "fees.read"],
};

describe("hasRecordAccess", () => {
  // ROLE-01 c3: Read-only gets the aggregated dashboards and nothing else.
  it("is false for dashboard-only roles", () => {
    expect(hasRecordAccess(["dashboard.aggregated"])).toBe(false);
    expect(hasRecordAccess(["dashboard.aggregated", "dashboard.firm"])).toBe(false);
    expect(hasRecordAccess(partner.permissions)).toBe(true);
  });
});

describe("navigation for reports", () => {
  it("gives read-only the overview and dashboards only", () => {
    expect(getPrimaryNavigation(readOnly).map((item) => item.href)).toEqual(["/overview", "/analytics"]);
  });

  it("offers the fee forecast and win/loss to a partner", () => {
    const hrefs = getPrimaryNavigation(partner).map((item) => item.href);
    expect(hrefs).toContain("/analytics");
    expect(hrefs).toContain("/fee-forecast");
    expect(hrefs).toContain("/win-loss");
  });

  it("gates the report pages by permission", () => {
    expect(satisfiesAudience(audienceFor("/fee-forecast"), readOnly)).toBe(false);
    expect(satisfiesAudience(audienceFor("/win-loss"), readOnly)).toBe(false);
    expect(satisfiesAudience(audienceFor("/analytics"), readOnly)).toBe(true);
    expect(satisfiesAudience(audienceFor("/win-loss"), partner)).toBe(true);
  });
});

describe("pivot", () => {
  it("builds a stage x type grid with zeros for empty cells", () => {
    const grid = pivot([
      { stage: "preparation", type: "sell_side", count: 2 },
      { stage: "marketing", type: "buy_side", count: 1 },
    ]);
    expect(grid.stages).toEqual(["preparation", "marketing"]);
    expect(grid.types).toEqual(["buy_side", "sell_side"]);
    expect(grid.cell("preparation", "sell_side")).toBe(2);
    expect(grid.cell("preparation", "buy_side")).toBe(0);
  });
});

describe("win/loss period", () => {
  it("defaults to the calendar year and encodes the query", () => {
    expect(defaultPeriod(new Date("2026-10-10T12:00:00Z"))).toEqual({ from: "2026-01-01", to: "2026-12-31" });
    expect(winLossQuery("2026-01-01", "2026-03-31")).toBe("?from=2026-01-01&to=2026-03-31");
  });
});
