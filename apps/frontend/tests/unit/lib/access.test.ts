import { describe, expect, it } from "vitest";
import { addDays, downloadWithStepUp, endOfDay, isOverdue, stepUpHeaders } from "@/lib/access";

describe("stepUpHeaders (AUTH-02 c5)", () => {
  it("sends the code without spaces in X-Step-Up-Code", () => {
    expect(stepUpHeaders(" 123 456 ")).toEqual({ "X-Step-Up-Code": "123456" });
  });
});

describe("wall-crossing expiry (AUTHZ-04 c2)", () => {
  it("defaults to 30 days and lasts to the end of that day", () => {
    expect(addDays(new Date("2026-10-09T09:00:00Z"), 30)).toBe("2026-11-08");
    expect(endOfDay("2026-11-08")).toBe("2026-11-08T23:59:59Z");
  });
});

describe("isOverdue (ADM-05 c2)", () => {
  it("is overdue once due and unanswered", () => {
    const due = { due_at: "2027-01-15T06:00:00Z", completed_at: null };
    expect(isOverdue(due, new Date("2027-01-14T06:00:00Z"))).toBe(false);
    expect(isOverdue(due, new Date("2027-01-15T06:00:00Z"))).toBe(true);
    expect(isOverdue({ ...due, completed_at: "2027-01-10T00:00:00Z" }, new Date("2027-02-01T00:00:00Z"))).toBe(false);
  });
});

describe("downloadWithStepUp (AUTH-02 c5)", () => {
  function fetcher(response: Response) {
    const calls: { path: string; headers: Record<string, string> }[] = [];
    const fn = (path: string, init: { headers: Record<string, string> }) => {
      calls.push({ path, headers: init.headers });
      return Promise.resolve(response);
    };
    return { fn, calls };
  }

  it("sends the code with the mass export and returns the file", async () => {
    const { fn, calls } = fetcher(new Response("a,b", { status: 200 }));
    const result = await downloadWithStepUp(fn, "/api/v1/fees/export", " 123 456 ");
    expect(calls).toEqual([{ path: "/api/v1/fees/export", headers: { "X-Step-Up-Code": "123456" } }]);
    expect(result.kind).toBe("file");
  });

  it("asks for the code again when the backend refuses it", async () => {
    const refused = new Response(JSON.stringify({ detail: "Enter your authentication code" }), {
      status: 401,
      headers: { "X-Step-Up": "required" },
    });
    const result = await downloadWithStepUp(fetcher(refused).fn, "/api/v1/exports/contacts", "000000");
    expect(result).toEqual({ kind: "code" });
  });

  it("passes any other refusal on as a message", async () => {
    const refused = new Response(JSON.stringify({ detail: "Partner approval required" }), { status: 403 });
    const result = await downloadWithStepUp(fetcher(refused).fn, "/api/v1/exports/contacts", "123456");
    expect(result).toEqual({ kind: "error", message: "Partner approval required" });
  });
});
