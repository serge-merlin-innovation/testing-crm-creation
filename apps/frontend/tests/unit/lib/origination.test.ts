import { describe, expect, it } from "vitest";
import {
  credentialQuery,
  groupByStage,
  isClosed,
  MOVABLE_STAGES,
  OPPORTUNITY_STAGES,
  stagePayload,
  weightedEv,
  type Opportunity,
} from "@/lib/origination";

const opportunity = (overrides: Partial<Opportunity> = {}): Opportunity => ({
  id: 1,
  company_id: 1,
  company_name: "Acme",
  owner_id: 1,
  owner_name: "Paula",
  type: "sell_side",
  trigger: "succession",
  estimated_ev: "40000.00",
  probability: 50,
  sector_id: null,
  stage: "lead",
  lost_reason: null,
  competitor_advisor: null,
  revisit_date: null,
  mandate_id: null,
  conflict_warning: false,
  is_owner: true,
  ...overrides,
});

describe("origination", () => {
  it("has the eight ORI-01 stages, and Won is not a plain move", () => {
    expect(OPPORTUNITY_STAGES).toEqual([
      "lead",
      "contacted",
      "meeting_held",
      "pitch",
      "engagement_letter_sent",
      "won",
      "lost",
      "on_hold",
    ]);
    expect(MOVABLE_STAGES).not.toContain("won");
  });

  it("groups the pipeline by stage", () => {
    const columns = groupByStage([opportunity({ id: 1 }), opportunity({ id: 2, stage: "pitch" })]);
    expect(columns.lead.map((row) => row.id)).toEqual([1]);
    expect(columns.pitch.map((row) => row.id)).toEqual([2]);
    expect(columns.won).toEqual([]);
  });

  it("sends only what the stage needs", () => {
    expect(stagePayload("lost", { lostReason: "competitor", competitor: "  Rival CF ", revisitDate: "2026-11-01" })).toEqual({
      stage: "lost",
      lost_reason: "competitor",
      competitor_advisor: "Rival CF",
    });
    expect(stagePayload("on_hold", { revisitDate: "2026-11-01", lostReason: "fee" })).toEqual({
      stage: "on_hold",
      revisit_date: "2026-11-01",
    });
    expect(stagePayload("pitch", { lostReason: "fee" })).toEqual({ stage: "pitch" });
  });

  it("builds the credential search query", () => {
    expect(credentialQuery({})).toBe("");
    expect(credentialQuery({ sectorId: "3", evMin: " 10000 ", evMax: "" })).toBe("?sector_id=3&ev_min=10000");
  });

  it("weights open opportunities by probability", () => {
    expect(isClosed(opportunity({ stage: "lost" }))).toBe(true);
    expect(
      weightedEv([opportunity(), opportunity({ estimated_ev: "10000", probability: 10 }), opportunity({ stage: "won" })]),
    ).toBe(21000);
  });
});
