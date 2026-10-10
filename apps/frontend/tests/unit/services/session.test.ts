import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.resetModules();
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const STATUS = {
  idle_expires_at: "2030-03-04T09:30:00Z",
  absolute_expires_at: "2030-03-04T21:00:00Z",
  warning_seconds: 120,
  mobile: true,
  mobile_read_only: true,
};

describe("session service", () => {
  it("reads the session status without bouncing, so a background check never navigates (AUTH-03 c6)", async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse(STATUS));
    vi.stubGlobal("fetch", fetcher);
    const { fetchSessionStatus } = await import("@/services/session");

    const status = await fetchSessionStatus();

    expect(status?.mobileReadOnly).toBe(true);
    expect(fetcher).toHaveBeenCalledWith("/api/v1/auth/session", expect.anything());
  });

  it("reports an ended session as null instead of redirecting", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "x" }, 401)));
    const replace = vi.fn();
    vi.stubGlobal("window", { location: { origin: "https://a.test", pathname: "/overview", search: "", replace } });
    const { fetchSessionStatus } = await import("@/services/session");

    expect(await fetchSessionStatus()).toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });

  it("Stay logged in posts the renewal with the CSRF token (AUTH-03 c2)", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ csrf_token: "csrf-1" }))
      .mockResolvedValueOnce(jsonResponse(STATUS));
    vi.stubGlobal("fetch", fetcher);
    const { renewSession } = await import("@/services/session");

    const status = await renewSession();

    expect(status?.idleExpiresAt.toISOString()).toBe("2030-03-04T09:30:00.000Z");
    const [path, init] = fetcher.mock.calls[1];
    expect(path).toBe("/api/v1/auth/session/renew");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-1");
  });

  it("Log out everywhere ends every session (AUTH-04 c3)", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ csrf_token: "csrf-1" }))
      .mockResolvedValueOnce(jsonResponse({ revoked: 3 }));
    vi.stubGlobal("fetch", fetcher);
    const { logoutEverywhere } = await import("@/services/session");

    expect(await logoutEverywhere()).toBe(3);
    expect(fetcher.mock.calls[1][0]).toBe("/api/v1/auth/logout-everywhere");
    expect(fetcher.mock.calls[1][1].method).toBe("POST");
  });

  it("an admin logs a user out on every device (AUTH-07 c3)", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ csrf_token: "csrf-1" }))
      .mockResolvedValueOnce(jsonResponse({ revoked: 2 }));
    vi.stubGlobal("fetch", fetcher);
    const { revokeUserSessions } = await import("@/services/session");

    expect(await revokeUserSessions(7)).toBe(2);
    expect(fetcher.mock.calls[1][0]).toBe("/api/v1/users/7/sessions");
    expect(fetcher.mock.calls[1][1].method).toBe("DELETE");
  });
});
