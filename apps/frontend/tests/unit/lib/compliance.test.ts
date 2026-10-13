import { describe, expect, it } from "vitest";
import { fillTemplate, kycOutcome } from "@/lib/compliance";

const none = { ubo_check: false, id_check: false, pep_sanctions_screening: false, sanctions_hit: false };

describe("kycOutcome (ORI-05 c2, c4)", () => {
  it("approves only when UBO, ID and PEP/sanctions checks are all done", () => {
    expect(kycOutcome(none)).toBe("pending");
    expect(kycOutcome({ ...none, ubo_check: true, id_check: true })).toBe("pending");
    expect(kycOutcome({ ...none, ubo_check: true, id_check: true, pep_sanctions_screening: true })).toBe("approved");
  });

  it("freezes on a sanctions hit, whatever else is ticked", () => {
    expect(kycOutcome({ ubo_check: true, id_check: true, pep_sanctions_screening: true, sanctions_hit: true })).toBe("frozen");
  });
});

describe("fillTemplate", () => {
  it("fills named placeholders and leaves unknown ones", () => {
    expect(fillTemplate("On {date} by {name} {x}", { date: "09/10/2026", name: "Cora" })).toBe("On 09/10/2026 by Cora {x}");
  });
});
