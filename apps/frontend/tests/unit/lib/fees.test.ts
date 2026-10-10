import { describe, expect, it } from "vitest";
import { getPrimaryNavigation } from "@/lib/app-navigation";
import {
  canRecordInvoices,
  canSeeFees,
  feePayload,
  feesQuery,
  formFromTerms,
  formatTiers,
  needsAmendment,
  parseTiers,
  type FeeTerms,
} from "@/lib/fees";
import type { Viewer } from "@/lib/page-audience";

const terms = (overrides: Partial<FeeTerms> = {}): FeeTerms => ({
  mandate_id: 1,
  code_name: "Falcon",
  retainer_monthly: "10000.00",
  success_fee_kind: "percent",
  success_fee_percent: "2.000",
  success_fee_fixed: null,
  minimum_fee: "0.00",
  lehman_tiers: [],
  retainers_creditable: false,
  retainers_paid: "0.00",
  expected_fee: "500000.00",
  final_fee: null,
  engaged: false,
  can_edit: true,
  ...overrides,
});

const viewer = (permissions: string[]): Viewer => ({ isAuthenticated: true, roleName: "x", permissions });

// AUTHZ-06 c1 + c3: no fee field, fee page or fee filter for a role without fees.read.
describe("fee visibility", () => {
  it("hides fees from an analyst and shows them to partner and back-office", () => {
    expect(canSeeFees(["deals.read_staffed", "deals.edit_staffed"])).toBe(false);
    expect(canSeeFees(["fees.read", "fees.edit_own_deals"])).toBe(true);
    expect(canRecordInvoices(["fees.read", "fees.edit_own_deals"])).toBe(false);
    expect(canRecordInvoices(["fees.read", "invoices.manage"])).toBe(true);
  });

  it("offers the Fees page (with its fee filter) only to fee readers", () => {
    const hrefs = (permissions: string[]) => getPrimaryNavigation(viewer(permissions)).map((item) => item.href);
    expect(hrefs(["deals.read_staffed"])).not.toContain("/fees");
    expect(hrefs(["deals.read_staffed", "fees.read"])).toContain("/fees");
  });

  it("sends the fee filter only when set", () => {
    expect(feesQuery("")).toBe("");
    expect(feesQuery(" 100000 ")).toBe("?min_expected_fee=100000");
  });
});

// DEAL-05 c1: Lehman tiers round-trip through the one-line editor; the payload carries the chosen kind.
describe("fee form", () => {
  it("parses and formats Lehman tiers with an open last band", () => {
    const tiers = parseTiers("10000:3, 20000:2, :1");
    expect(tiers).toEqual([
      { up_to: "10000", percent: "3" },
      { up_to: "20000", percent: "2" },
      { up_to: null, percent: "1" },
    ]);
    expect(formatTiers(tiers)).toBe("10000:3, 20000:2, :1");
  });

  it("sends only the value of the chosen success-fee kind", () => {
    const form = { ...formFromTerms(terms()), success_fee_kind: "fixed" as const, success_fee_fixed: "250000" };
    const payload = feePayload(form);
    expect(payload.success_fee_fixed).toBe("250000");
    expect(payload).not.toHaveProperty("success_fee_percent");
    expect(payload).not.toHaveProperty("change_reason");
  });
});

// DEAL-05 c3: the reason and amended letter are asked for only on a real change after engagement.
describe("needsAmendment", () => {
  it("is false before engagement and for an unchanged form", () => {
    expect(needsAmendment(terms(), { ...formFromTerms(terms()), success_fee_percent: "3" })).toBe(false);
    const engaged = terms({ engaged: true });
    expect(needsAmendment(engaged, { ...formFromTerms(engaged), success_fee_percent: "2" })).toBe(false);
  });

  it("is true when an engaged deal's terms change", () => {
    const engaged = terms({ engaged: true });
    expect(needsAmendment(engaged, { ...formFromTerms(engaged), success_fee_percent: "3" })).toBe(true);
    expect(needsAmendment(engaged, { ...formFromTerms(engaged), retainers_creditable: true })).toBe(true);
  });
});
