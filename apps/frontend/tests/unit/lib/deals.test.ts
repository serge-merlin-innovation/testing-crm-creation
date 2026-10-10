import { describe, expect, it } from "vitest";
import {
  DEAL_STAGES,
  documentLinkProps,
  fieldErrors,
  historyRows,
  isHttpsUrl,
  readStaleConflict,
} from "@/lib/deals";

// DEAL-07 c1: any https URL opens in a new tab; nothing else is accepted as a link.
describe("document links", () => {
  it.each([
    ["https://vdr.example.com/rooms/falcon", true],
    ["https://fileserver.firm.local/deals/falcon", true],
    ["http://files.example.com/im.pdf", false],
    ["javascript:alert(1)", false],
    ["ftp://files.example.com", false],
    ["not a url", false],
  ])("%s is accepted: %s", (url, accepted) => {
    expect(isHttpsUrl(url)).toBe(accepted);
  });

  it("opens in a new tab without handing the opener to the target", () => {
    expect(documentLinkProps("https://vdr.example.com/x")).toEqual({
      href: "https://vdr.example.com/x",
      target: "_blank",
      rel: "noopener noreferrer",
    });
  });

  it("refuses to render a stored non-https link as clickable", () => {
    expect(documentLinkProps("javascript:alert(1)")).toBeNull();
  });
});

// DEAL-03 c2: a stale save surfaces the conflict message and the newer version.
describe("readStaleConflict", () => {
  it("returns the message and the newer deal from a 409", () => {
    const body = {
      detail: { message: "Someone changed this deal", current: { id: 3, version: 4, code_name: "Heron" } },
    };
    expect(readStaleConflict(409, body)).toEqual({
      message: "Someone changed this deal",
      current: { id: 3, version: 4, code_name: "Heron" },
    });
  });

  it("ignores other errors", () => {
    expect(readStaleConflict(409, { detail: "This code name is already in use." })).toBeNull();
    expect(readStaleConflict(422, { detail: { message: "x", current: {} } })).toBeNull();
  });
});

// DEAL-03 c3: the history tab shows who, when, old and new value.
describe("historyRows", () => {
  it("keeps who, when, field, old and new", () => {
    const rows = historyRows([
      {
        action: "mandate.updated",
        at: "2026-10-11T14:30:00Z",
        user_id: 1,
        user_name: "paula",
        field: "estimated_ev",
        old_value: "25000.00",
        new_value: "30000.00",
      },
      { action: "mandate.created", at: "2026-10-10T09:00:00Z", user_id: 1, user_name: null, field: null, old_value: null, new_value: null },
    ]);
    expect(rows).toEqual([
      { who: "paula", when: "2026-10-11T14:30:00Z", what: "estimated_ev", old: "25000.00", new: "30000.00" },
      { who: "", when: "2026-10-10T09:00:00Z", what: "mandate.created", old: "", new: "" },
    ]);
  });
});

describe("fieldErrors", () => {
  it("maps the backend's 422 errors to fields", () => {
    expect(
      fieldErrors({ errors: [{ field: "code_name", message: "The code name must not contain the client or target name" }] }),
    ).toEqual({ code_name: "The code name must not contain the client or target name" });
    expect(fieldErrors({ detail: "x" })).toEqual({});
  });
});

// DEAL-01 c5 (derived): one stage list, the sell-side one.
describe("DEAL_STAGES", () => {
  it("is the sell-side list, from conflict review to aborted", () => {
    expect(DEAL_STAGES[0]).toBe("conflict_review");
    expect(DEAL_STAGES.at(-1)).toBe("aborted");
    expect(DEAL_STAGES).toHaveLength(12);
  });
});
