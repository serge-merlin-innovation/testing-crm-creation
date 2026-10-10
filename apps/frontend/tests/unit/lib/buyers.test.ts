import { describe, expect, it } from "vitest";
import { blockedReason, SETTABLE_STATUSES, toggle } from "@/lib/buyers";

const signed = { sent_date: "2026-10-01", signed_date: "2026-10-05" } as never;

describe("blockedReason", () => {
  it("lets any buyer go back to the long list or decline", () => {
    expect(blockedReason({ approval: "pending", nda: null }, "long_list")).toBeNull();
    expect(blockedReason({ approval: "excluded", nda: null }, "declined")).toBeNull();
  });

  it("only lets approved buyers be contacted", () => {
    expect(blockedReason({ approval: "pending", nda: null }, "contacted")).toBe("buyers.blocked.notApproved");
    expect(blockedReason({ approval: "excluded", nda: null }, "teaser_sent")).toBe("buyers.blocked.notApproved");
    expect(blockedReason({ approval: "approved", nda: null }, "contacted")).toBeNull();
  });

  it("needs a signed NDA before the IM", () => {
    expect(blockedReason({ approval: "approved", nda: null }, "im_sent")).toBe("buyers.blocked.needsNda");
    expect(blockedReason({ approval: "approved", nda: signed }, "im_sent")).toBeNull();
  });

  it("never sets NDA signed by hand", () => {
    expect(blockedReason({ approval: "approved", nda: signed }, "nda_signed")).toBe("buyers.blocked.ndaSigned");
    expect(SETTABLE_STATUSES).not.toContain("nda_signed");
  });
});

describe("toggle", () => {
  it("adds and removes ids", () => {
    expect(toggle([1, 2], 3)).toEqual([1, 2, 3]);
    expect(toggle([1, 2], 1)).toEqual([2]);
  });
});
