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

    await login("serge", "password");

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/auth/login",
      expect.objectContaining({
        credentials: "same-origin",
        method: "POST",
      }),
    );
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

describe("getMicrosoftAuthorizeUrl", () => {
  it("asks the backend to start the flow, forwarding the return path", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
        url: "https://login.microsoftonline.com/tenant/oauth2/v2.0/authorize?x=1",
      }),
    );
    vi.stubGlobal("fetch", fetcher);
    const { getMicrosoftAuthorizeUrl } = await import("@/services/auth");

    const url = await getMicrosoftAuthorizeUrl("/analytics?range=week");

    expect(url).toBe(
      "https://login.microsoftonline.com/tenant/oauth2/v2.0/authorize?x=1",
    );
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/auth/oauth/microsoft?redirect_uri=%2Fanalytics%3Frange%3Dweek",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("rejects an authorize URL that is not on login.microsoftonline.com", async () => {
    // A misconfigured or compromised backend must not be able to turn the login
    // page into an open redirect, since the caller navigates to whatever we return.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ url: "https://evil.example/steal" })),
    );
    const { getMicrosoftAuthorizeUrl } = await import("@/services/auth");

    await expect(getMicrosoftAuthorizeUrl("/")).rejects.toThrow(
      "We could not start Microsoft sign-in.",
    );
  });

  it("rejects a payload with no usable url", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "nope" })),
    );
    const { getMicrosoftAuthorizeUrl } = await import("@/services/auth");

    await expect(getMicrosoftAuthorizeUrl("/")).rejects.toThrow(
      "We could not start Microsoft sign-in.",
    );
  });

  it("surfaces a non-ok response as an authentication error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "boom" }, 500)),
    );
    const { getMicrosoftAuthorizeUrl } = await import("@/services/auth");

    await expect(getMicrosoftAuthorizeUrl("/")).rejects.toThrow(
      "We could not start Microsoft sign-in.",
    );
  });

  it("reports an unreachable backend", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network")));
    const { getMicrosoftAuthorizeUrl } = await import("@/services/auth");

    await expect(getMicrosoftAuthorizeUrl("/")).rejects.toThrow(
      "We could not reach the backend.",
    );
  });
});

describe("describeOAuthError", () => {
  it("explains that an unlinked account needs an administrator", async () => {
    const { describeOAuthError } = await import("@/services/auth");

    expect(describeOAuthError("not_provisioned", "microsoft")).toBe(
      "This Microsoft account is not linked to a workspace account. Ask an administrator to link it.",
    );
  });

  it.each([
    ["invalid_state", "That sign-in link expired. Please try again."],
    ["provider_mismatch", "That sign-in attempt did not match. Please try again."],
  ])("maps %s to actionable copy", async (reason, expected) => {
    const { describeOAuthError } = await import("@/services/auth");

    expect(describeOAuthError(reason, "microsoft")).toBe(expected);
  });

  it("falls back for an unknown reason", async () => {
    const { describeOAuthError } = await import("@/services/auth");

    expect(describeOAuthError("something_new", "microsoft")).toBe(
      "We could not complete Microsoft sign-in. Please try again.",
    );
  });
});
