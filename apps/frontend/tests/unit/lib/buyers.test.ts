import { describe, expect, it } from "vitest";
import { BUYER_STATUSES, blockedReason, SETTABLE_STATUSES, suggestionsPath, toggle } from "@/lib/buyers";

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

describe("statuses", () => {
  it("are the twelve Epic 7 statuses in spec order", () => {
    expect(BUYER_STATUSES).toEqual([
      "long_list",
      "client_approved",
      "contacted",
      "teaser_sent",
      "nda_sent",
      "nda_signed",
      "im_sent",
      "indicative_offer",
      "data_room_access",
      "binding_offer",
      "preferred_bidder",
      "declined",
    ]);
  });

  it("never sets Client approved by hand and gates the data room on the NDA", () => {
    expect(SETTABLE_STATUSES).not.toContain("client_approved");
    expect(blockedReason({ approval: "approved", nda: null }, "data_room_access")).toBe("buyers.blocked.needsNda");
    expect(blockedReason({ approval: "approved", nda: null }, "preferred_bidder")).toBe("buyers.blocked.needsNda");
  });
});

describe("toggle", () => {
  it("adds and removes ids", () => {
    expect(toggle([1, 2], 3)).toEqual([1, 2, 3]);
    expect(toggle([1, 2], 1)).toEqual([2]);
  });
});

describe("suggestionsPath", () => {
  it("adds the EV/EBITDA and stake filters only when set", () => {
    expect(suggestionsPath(7, { evEbitda: "", stake: "any" })).toBe("/api/v1/mandates/7/buyers/suggestions");
    expect(suggestionsPath(7, { evEbitda: " 8.5 ", stake: "minority" })).toBe(
      "/api/v1/mandates/7/buyers/suggestions?ev_ebitda=8.5&stake=minority",
    );
  });
});
