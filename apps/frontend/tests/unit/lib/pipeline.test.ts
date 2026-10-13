import { describe, expect, it } from "vitest";
import {
  BOARD_STAGES,
  blockedReasons,
  dealsQuery,
  groupByStage,
  isBackward,
  NO_FILTERS,
  partnerOptions,
  sortDeals,
  stageLabel,
  toggleSort,
  type DealListItem,
} from "@/lib/pipeline";

const deal = (id: number, overrides: Partial<DealListItem> = {}): DealListItem => ({
  id,
  code_name: `Deal ${id}`,
  type: "sell_side",
  stage: "conflict_review",
  lead_partner_id: 1,
  lead_partner_name: "Paula",
  sector_id: 1,
  estimated_ev: "1000.00",
  stage_changed_at: null,
  closed_at: null,
  ...overrides,
});

// DEAL-02 c3: filters go to the backend, which returns only accessible deals.
describe("deal filters", () => {
  it("sends only the chosen filters", () => {
    expect(dealsQuery(NO_FILTERS)).toBe("");
    expect(dealsQuery({ ...NO_FILTERS, type: "buy_side", stage: "marketing" }, "fal")).toBe(
      "?q=fal&type=buy_side&stage=marketing",
    );
  });

  it("offers the partners of the visible deals", () => {
    const options = partnerOptions([deal(1), deal(2, { lead_partner_id: 2, lead_partner_name: "Bert" }), deal(3)]);
    expect(options).toEqual([
      { value: "2", label: "Bert" },
      { value: "1", label: "Paula" },
    ]);
  });
});

// DEAL-02 c1 + c4: board columns follow the stage order; a move to an earlier column is backward.
describe("the board", () => {
  it("groups deals by stage and keeps closed stages off the board", () => {
    const columns = groupByStage([deal(1), deal(2, { stage: "marketing" })]);
    expect(columns.marketing.map((d) => d.id)).toEqual([2]);
    expect(BOARD_STAGES).not.toContain("aborted");
    expect(BOARD_STAGES[0]).toBe("conflict_review");
  });

  it("knows a backward move", () => {
    expect(isBackward("marketing", "preparation")).toBe(true);
    expect(isBackward("preparation", "marketing")).toBe(false);
  });

  it("labels a stage for people", () => {
    expect(stageLabel("due_diligence")).toBe("Due diligence");
  });

  it("reads the reasons of a blocked move", () => {
    expect(blockedReasons({ detail: { reasons: ["Add a document link labelled “VDR”."] } })).toEqual([
      "Add a document link labelled “VDR”.",
    ]);
    expect(blockedReasons({ detail: "nope" })).toBeNull();
  });
});

// DEAL-02 c5: the list view is a sortable table of the same deals.
describe("the list view", () => {
  const deals = [
    deal(1, { code_name: "Heron", stage: "marketing", estimated_ev: "900" }),
    deal(2, { code_name: "falcon", stage: "preparation", estimated_ev: "12000" }),
  ];

  it("sorts by any column, both ways", () => {
    expect(sortDeals(deals, { key: "code_name", descending: false }).map((d) => d.id)).toEqual([2, 1]);
    expect(sortDeals(deals, { key: "stage", descending: false }).map((d) => d.id)).toEqual([2, 1]);
    expect(sortDeals(deals, { key: "estimated_ev", descending: true }).map((d) => d.id)).toEqual([2, 1]);
    expect(sortDeals(deals, { key: "estimated_ev", descending: false }).map((d) => d.id)).toEqual([1, 2]);
  });

  it("flips direction on the same column", () => {
    expect(toggleSort({ key: "stage", descending: false }, "stage")).toEqual({ key: "stage", descending: true });
    expect(toggleSort({ key: "stage", descending: true }, "code_name")).toEqual({ key: "code_name", descending: false });
  });
});
