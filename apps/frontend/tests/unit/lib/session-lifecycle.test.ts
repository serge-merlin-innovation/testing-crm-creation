import { describe, expect, it } from "vitest";
import {
  MOBILE_BREAKPOINT_PX,
  editActionClassName,
  hidesEditActions,
} from "@/lib/mobile-access";
import {
  clearDraft,
  loadDraft,
  saveDraft,
  type DraftStorage,
} from "@/lib/form-drafts";
import {
  parseSessionStatus,
  sessionPhase,
  shouldRenewOnActivity,
  laterStatus,
} from "@/lib/session-timer";
import { createUnsavedChanges } from "@/lib/unsaved-changes";

const status = (idle: string, absolute: string | null = null) =>
  parseSessionStatus({
    idle_expires_at: idle,
    absolute_expires_at: absolute,
    warning_seconds: 120,
    mobile: false,
    mobile_read_only: false,
  })!;

describe("session timer (AUTH-03)", () => {
  const live = status("2030-03-04T09:30:00Z", "2030-03-04T21:00:00Z");

  it("stays active until two minutes before the idle timeout", () => {
    expect(sessionPhase(live, new Date("2030-03-04T09:27:59Z"))).toBe("active");
  });

  it("warns two minutes before the timeout so the user can stay logged in", () => {
    expect(sessionPhase(live, new Date("2030-03-04T09:28:00Z"))).toBe("warning");
  });

  it("expires at the idle timeout", () => {
    expect(sessionPhase(live, new Date("2030-03-04T09:30:00Z"))).toBe("expired");
  });

  it("expires at the absolute lifetime even when the idle window is still open", () => {
    const old = status("2030-03-04T21:20:00Z", "2030-03-04T21:00:00Z");
    expect(sessionPhase(old, new Date("2030-03-04T20:58:30Z"))).toBe("warning");
    expect(sessionPhase(old, new Date("2030-03-04T21:00:00Z"))).toBe("expired");
  });

  it("takes the later expiry another tab reports, so an active tab keeps this one alive", () => {
    const other = status("2030-03-04T09:50:00Z", "2030-03-04T21:00:00Z");
    expect(laterStatus(live, other)).toBe(other);
    expect(laterStatus(other, live)).toBe(other);
    expect(sessionPhase(laterStatus(live, other), new Date("2030-03-04T09:29:00Z"))).toBe("active");
  });

  it("renews silently on activity at most once a minute", () => {
    const now = new Date("2030-03-04T09:10:00Z");
    expect(shouldRenewOnActivity(null, now)).toBe(true);
    expect(shouldRenewOnActivity(new Date("2030-03-04T09:09:30Z"), now)).toBe(false);
    expect(shouldRenewOnActivity(new Date("2030-03-04T09:09:00Z"), now)).toBe(true);
  });

  it("rejects a malformed status", () => {
    expect(parseSessionStatus({ idle_expires_at: 3 })).toBeNull();
  });
});

function memoryStorage(): DraftStorage & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => void data.set(key, value),
    removeItem: (key) => void data.delete(key),
  };
}

describe("form drafts (AUTH-03 c1)", () => {
  it("keeps unsaved form data locally across re-authentication", () => {
    const storage = memoryStorage();
    saveDraft(storage, "/companies/new", { name: "Acme" });
    expect(loadDraft(storage, "/companies/new")).toEqual({ name: "Acme" });
    clearDraft(storage, "/companies/new");
    expect(loadDraft(storage, "/companies/new")).toBeNull();
  });

  it("ignores a corrupt draft", () => {
    const storage = memoryStorage();
    storage.setItem("crm.draft:/x", "{not json");
    expect(loadDraft(storage, "/x")).toBeNull();
  });
});

describe("unsaved changes (AUTH-04 c4)", () => {
  it("reports unsaved changes until every form is clean", () => {
    const unsaved = createUnsavedChanges();
    expect(unsaved.any()).toBe(false);
    unsaved.mark("company", true);
    unsaved.mark("contact", true);
    unsaved.mark("company", false);
    expect(unsaved.any()).toBe(true);
    unsaved.mark("contact", false);
    expect(unsaved.any()).toBe(false);
  });

  it("collects every dirty form's draft so it survives the sign-in", () => {
    const unsaved = createUnsavedChanges();
    unsaved.mark("company", true, () => ({ name: "Acme" }));
    expect(unsaved.drafts()).toEqual({ company: { name: "Acme" } });
  });
});

describe("mobile access (AUTH-07 c2)", () => {
  it("uses the 768 px breakpoint", () => {
    expect(MOBILE_BREAKPOINT_PX).toBe(768);
  });

  it("hides edit and export actions under 768 px only when mobile is read-only", () => {
    expect(hidesEditActions(true, 767)).toBe(true);
    expect(hidesEditActions(true, 768)).toBe(false);
    expect(hidesEditActions(false, 375)).toBe(false);
  });

  it("hides with the md breakpoint so it applies before any script runs", () => {
    expect(editActionClassName(true)).toBe("hidden md:contents");
    expect(editActionClassName(false)).toBe("contents");
  });
});
