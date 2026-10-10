import { describe, expect, it } from "vitest";
import { approvalNotice, canConfirm, ownerCandidates, type OffboardingPreview } from "@/lib/offboarding";

const preview = (overrides: Partial<OffboardingPreview> = {}): OffboardingPreview => ({
  user_id: 1,
  name: "anna",
  contacts: [],
  tasks: [],
  deals: [],
  deal_memberships: 0,
  needs_new_owner: true,
  new_owner_must_be_partner: false,
  ...overrides,
});

const users = [
  { id: 1, name: "anna", role_name: "Analyst / Associate", status: "active" },
  { id: 2, name: "paula", role_name: "Partner", status: "active" },
  { id: 3, name: "dirk", role_name: "Director / Manager", status: "active" },
  { id: 4, name: "ivo", role_name: "Partner", status: "invited" },
];

describe("offboarding (ADM-03)", () => {
  it("never offers the leaver or an invited user as the new owner", () => {
    expect(ownerCandidates(preview(), users).map((user) => user.id)).toEqual([2, 3]);
  });

  it("offers only Partners when deals are handed over", () => {
    expect(ownerCandidates(preview({ new_owner_must_be_partner: true }), users).map((user) => user.id)).toEqual([2]);
  });

  it("blocks confirming until a new owner is chosen for owned records", () => {
    expect(canConfirm(preview(), null)).toBe(false);
    expect(canConfirm(preview(), 2)).toBe(true);
    expect(canConfirm(preview({ needs_new_owner: false }), null)).toBe(true);
    expect(canConfirm(null, 2)).toBe(false);
  });

  it("fills the approval limit into the notice", () => {
    expect(approvalNotice("More than {limit} contacts", 500)).toBe("More than 500 contacts");
  });
});
