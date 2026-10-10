import { describe, expect, it } from "vitest";
import {
  earlierVersions,
  localToIso,
  structureAddsUp,
  unknownFields,
  type Offer,
} from "@/lib/process";

describe("unknownFields", () => {
  it("lists merge fields the server would refuse", () => {
    expect(
      unknownFields(
        "{{salutation}} {{ last_name }}, {{fee}} {{fee}} {{code_name}}",
      ),
    ).toEqual(["fee"]);
    expect(unknownFields("{{funnel}} {{next_steps}}")).toEqual([]);
  });
});

describe("structureAddsUp", () => {
  it("needs the four parts to make 100%", () => {
    expect(structureAddsUp(["80", "10", "5", "5"])).toBe(true);
    expect(structureAddsUp(["90", "0", "0", "0"])).toBe(false);
    expect(structureAddsUp(["", "100", "", ""])).toBe(true);
  });
});

describe("earlierVersions", () => {
  it("keeps the same buyer and round below the shown version", () => {
    const offer = (
      id: number,
      buyer_id: number,
      round: "indicative" | "binding",
      version: number,
    ) => ({ id, buyer_id, round, version }) as Offer;
    const history = [
      offer(3, 1, "indicative", 2),
      offer(2, 1, "indicative", 1),
      offer(4, 1, "binding", 1),
      offer(5, 2, "indicative", 1),
    ];
    expect(earlierVersions(history, history[0]).map((item) => item.id)).toEqual(
      [2],
    );
  });
});

describe("localToIso", () => {
  it("returns null for an empty field", () => {
    expect(localToIso("")).toBeNull();
    expect(localToIso("2026-11-01T12:00")).toMatch(/^2026-11-01T/);
  });
});
