import { describe, expect, it } from "vitest";
import { canSearch, searchQuery, splitName } from "@/lib/search";

// CON-03 c1: three characters, or a saved filter / criterion, before a search runs.
describe("canSearch", () => {
  it("waits for three characters", () => {
    expect(canSearch({ q: "ze" })).toBe(false);
    expect(canSearch({ q: " zen " })).toBe(true);
  });

  it("runs a saved filter or criteria without text", () => {
    expect(canSearch({}, 4)).toBe(true);
    expect(canSearch({ company_types: ["financial_investor"] })).toBe(true);
    expect(canSearch({ ev_min: "10000" })).toBe(true);
  });
});

describe("searchQuery", () => {
  it("repeats list criteria and drops empty ones", () => {
    expect(searchQuery({ q: "pe", company_types: ["lender", "advisor"], country_ids: [3], ev_max: "" }, 9)).toBe(
      "q=pe&filter_id=9&company_type=lender&company_type=advisor&country_id=3",
    );
  });
});

// CON-03 c3: create from the search box.
describe("splitName", () => {
  it("splits the typed text into first and last name", () => {
    expect(splitName("Jan  van Damme")).toEqual({ first_name: "Jan", last_name: "van Damme" });
    expect(splitName("Peeters")).toEqual({ first_name: "", last_name: "Peeters" });
  });
});
