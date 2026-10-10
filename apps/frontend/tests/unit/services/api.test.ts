import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.resetModules();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("apiFetch", () => {
  it("calls this app's own origin with credentials for safe requests", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(null));
    vi.stubGlobal("fetch", fetcher);
    const { apiFetch } = await import("@/services/api");

    await apiFetch("/api/v1/orders?status=open");

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/orders?status=open",
      expect.objectContaining({
        credentials: "same-origin",
        headers: expect.any(Headers),
      }),
    );
  });

  it("gets a CSRF token before the first unsafe request", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ csrf_token: "csrf-1" }), {
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 201 }));
    vi.stubGlobal("fetch", fetcher);
    const { apiFetch } = await import("@/services/api");

    const response = await apiFetch("/api/v1/orders", {
      method: "POST",
      body: JSON.stringify({ item: "parcel" }),
    });

    expect(response.status).toBe(201);
    expect(fetcher).toHaveBeenNthCalledWith(
      1,
      "/api/v1/auth/refresh-csrf",
      expect.objectContaining({
        credentials: "same-origin",
        method: "POST",
      }),
    );
    const mutationInit = fetcher.mock.calls[1]?.[1] as RequestInit;
    expect(new Headers(mutationInit.headers).get("X-CSRF-Token")).toBe(
      "csrf-1",
    );
  });

  it("remembers a token returned by an endpoint such as login", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ csrf_token: "csrf-login" }), {
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(new Response(null));
    vi.stubGlobal("fetch", fetcher);
    const { apiFetch } = await import("@/services/api");

    await apiFetch("/api/v1/auth/login", {
      method: "POST",
      csrf: false,
    });
    await apiFetch("/api/v1/orders/1", { method: "DELETE" });

    expect(fetcher).toHaveBeenCalledTimes(2);
    const mutationInit = fetcher.mock.calls[1]?.[1] as RequestInit;
    expect(new Headers(mutationInit.headers).get("X-CSRF-Token")).toBe(
      "csrf-login",
    );
  });

  it("sends the browser back to login after a 401", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 401 })),
    );
    const replace = vi.fn();
    vi.stubGlobal("window", {
      location: {
        origin: "https://app.example.test",
        pathname: "/analytics",
        search: "?range=week",
        replace,
      },
    });
    const { apiFetch } = await import("@/services/api");

    const response = await apiFetch("/api/v1/orders");

    expect(response.status).toBe(401);
    expect(replace).toHaveBeenCalledWith(
      "https://app.example.test/login?next=%2Fanalytics%3Frange%3Dweek",
    );
  });

  it("leaves a 401 to the caller when bouncing is off", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 401 })),
    );
    const replace = vi.fn();
    vi.stubGlobal("window", {
      location: {
        origin: "https://app.example.test",
        pathname: "/login",
        search: "",
        replace,
      },
    });
    const { apiFetch } = await import("@/services/api");

    await apiFetch("/api/v1/auth/login", {
      method: "POST",
      csrf: false,
      bounce: false,
    });

    expect(replace).not.toHaveBeenCalled();
  });

  it("refreshes and retries an unsafe request once after 403", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ csrf_token: "csrf-old" }), {
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 403 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ csrf_token: "csrf-new" }), {
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetcher);
    const { apiFetch } = await import("@/services/api");

    await apiFetch("/api/v1/auth/login", {
      method: "POST",
      csrf: false,
    });
    const response = await apiFetch("/api/v1/orders/1", {
      method: "PATCH",
    });

    expect(response.status).toBe(204);
    expect(fetcher).toHaveBeenCalledTimes(4);
    const retriedInit = fetcher.mock.calls[3]?.[1] as RequestInit;
    expect(new Headers(retriedInit.headers).get("X-CSRF-Token")).toBe(
      "csrf-new",
    );
  });
});
