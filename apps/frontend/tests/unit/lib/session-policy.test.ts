import { describe, expect, it } from "vitest";
import { parseSessionPolicy, sessionPolicyBody } from "@/lib/session-policy";

describe("session policy (AUTH-03 c5, AUTH-07 c2)", () => {
  const wire = { desktop_idle_minutes: 30, mobile_idle_minutes: 15, absolute_hours: 12, mobile_read_only: true };

  it("round-trips the admin's values to the API body", () => {
    const policy = parseSessionPolicy(wire);
    expect(policy).toEqual({ desktopIdleMinutes: 30, mobileIdleMinutes: 15, absoluteHours: 12, mobileReadOnly: true });
    expect(sessionPolicyBody(policy!)).toEqual(wire);
  });

  it("rejects a partial payload", () => {
    expect(parseSessionPolicy({ desktop_idle_minutes: 30 })).toBeNull();
  });
});
