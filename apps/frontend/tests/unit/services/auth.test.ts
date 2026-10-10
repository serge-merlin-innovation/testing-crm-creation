import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.resetModules();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("browser authentication requests", () => {
  it("sends login to this app's own origin, which relays it on", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(jsonResponse({ csrf_token: "csrf-1" }));
    vi.stubGlobal("fetch", fetcher);
    const { login } = await import("@/services/auth");

    await login("serge@firm.be", "password");

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/auth/login",
      expect.objectContaining({
        credentials: "same-origin",
        method: "POST",
      }),
    );
    const body = fetcher.mock.calls[0][1].body as URLSearchParams;
    expect(body.get("email")).toBe("serge@firm.be");
    expect(body.has("username")).toBe(false);
  });

  it("surfaces the backend's rejection detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "Account locked." }, 401)),
    );
    const { login } = await import("@/services/auth");

    await expect(login("serge", "wrong")).rejects.toThrow("Account locked.");
  });

  it("falls back when the rejection carries no detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ error: "nope" }, 401)),
    );
    const { login } = await import("@/services/auth");

    await expect(login("serge", "wrong")).rejects.toThrow(
      "Check your details and try again.",
    );
  });

  it("uses the shared CSRF client for logout", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ csrf_token: "csrf-refreshed" }))
      .mockResolvedValueOnce(new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", fetcher);
    const { logout } = await import("@/services/auth");

    await logout();

    expect(fetcher).toHaveBeenNthCalledWith(
      1,
      "/api/v1/auth/refresh-csrf",
      expect.objectContaining({ credentials: "same-origin", method: "POST" }),
    );
    expect(fetcher).toHaveBeenNthCalledWith(
      2,
      "/api/v1/auth/logout",
      expect.objectContaining({
        credentials: "same-origin",
        method: "POST",
      }),
    );

    const logoutInit = fetcher.mock.calls[1]?.[1] as RequestInit;
    expect(new Headers(logoutInit.headers).get("X-CSRF-Token")).toBe(
      "csrf-refreshed",
    );
  });
});
