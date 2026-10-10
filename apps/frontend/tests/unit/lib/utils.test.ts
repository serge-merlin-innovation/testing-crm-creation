import { describe, expect, it } from "vitest";
import { cn } from "@/lib/utils";

describe("cn", () => {
  it("joins truthy class names and drops falsy ones", () => {
    expect(cn("flex", false && "hidden", undefined, "gap-2")).toBe("flex gap-2");
  });

  it("lets a later Tailwind utility override a conflicting earlier one", () => {
    expect(cn("p-4 text-sm", "p-2")).toBe("text-sm p-2");
  });

  it("merges utilities that resolve to the project's custom colour tokens", () => {
    expect(cn("bg-primary", "bg-destructive")).toBe("bg-destructive");
  });
});
