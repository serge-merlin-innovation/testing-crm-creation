import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  applyForwardedIdentity,
  clearSessionIdentityCache,
  readForwardedIdentity,
  resolveSessionIdentity,
  SESSION_ROLE_HEADER,
  SESSION_SUPERUSER_HEADER,
} from "@/lib/session-identity";

const backendOrigin = "http://backend.test";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function userResponse(
  { roleName, isSuperuser }: { roleName: string | null; isSuperuser: boolean },
): Response {
  return jsonResponse({
    id: 1,
    username: "userson",
    role_name: roleName,
    is_superuser: isSuperuser,
  });
}

type Fetcher = (
  input: URL | RequestInfo,
  init?: RequestInit,
) => Promise<Response>;

function backend(
  user: () => Response = () =>
    userResponse({ roleName: "user", isSuperuser: false }),
) {
  return vi.fn<Fetcher>(() => Promise.resolve(user()));
}

beforeEach(() => {
  clearSessionIdentityCache();
  vi.stubEnv("BACKEND_URL", backendOrigin);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("resolveSessionIdentity", () => {
  it("names the role the backend reported", async () => {
    vi.stubGlobal("fetch", backend());

    await expect(resolveSessionIdentity("session-1")).resolves.toEqual({
      status: "identified",
      identity: { roleName: "user", isSuperuser: false },
    });
  });

  it("reports a superuser with no role row", async () => {
    vi.stubGlobal(
      "fetch",
      backend(() => userResponse({ roleName: null, isSuperuser: true })),
    );

    await expect(resolveSessionIdentity("session-1")).resolves.toEqual({
      status: "identified",
      identity: { roleName: null, isSuperuser: true },
    });
  });

  it("asks the backend exactly once — the role name rides along with the profile", async () => {
    const fetcher = backend();
    vi.stubGlobal("fetch", fetcher);

    await resolveSessionIdentity("session-1");

    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("forwards only the session cookie to the backend", async () => {
    const fetcher = backend();
    vi.stubGlobal("fetch", fetcher);

    await resolveSessionIdentity("session-1");

    const [, init] = fetcher.mock.calls[0];

    expect(new Headers(init?.headers).get("Cookie")).toBe(
      "session_id=session-1",
    );
  });

  it.each([401, 403])("rejects a session the backend refuses (%i)", async (status) => {
    vi.stubGlobal(
      "fetch",
      backend(() => jsonResponse({ detail: "no" }, status)),
    );

    await expect(resolveSessionIdentity("session-1")).resolves.toEqual({
      status: "rejected",
    });
  });

  it("reports the backend unavailable on a server error", async () => {
    vi.stubGlobal(
      "fetch",
      backend(() => jsonResponse({ detail: "boom" }, 500)),
    );

    await expect(resolveSessionIdentity("session-1")).resolves.toEqual({
      status: "unavailable",
    });
  });

  it("reports the backend unavailable when the request throws", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("ECONNREFUSED"))),
    );

    await expect(resolveSessionIdentity("session-1")).resolves.toEqual({
      status: "unavailable",
    });
  });

  // The pair below is the distinction the whole gate rests on: a body missing `is_superuser` means
  // the backend is misbehaving and nothing can be judged, while a missing role name is a real
  // answer about a real user.
  it("reports the backend unavailable on a body it cannot read", async () => {
    vi.stubGlobal(
      "fetch",
      backend(() => jsonResponse({ id: 1 })),
    );

    await expect(resolveSessionIdentity("session-1")).resolves.toEqual({
      status: "unavailable",
    });
  });

  it("identifies a user the backend gave no role name, superuser flag intact", async () => {
    vi.stubGlobal(
      "fetch",
      backend(() => jsonResponse({ id: 1, is_superuser: false })),
    );

    await expect(resolveSessionIdentity("session-1")).resolves.toEqual({
      status: "identified",
      identity: { roleName: null, isSuperuser: false },
    });
  });
});

describe("the identity cache", () => {
  it("answers a repeat lookup without calling the backend again", async () => {
    const fetcher = backend();
    vi.stubGlobal("fetch", fetcher);

    await resolveSessionIdentity("session-1");
    await resolveSessionIdentity("session-1");

    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("caches a user with no role, since the backend said there is none", async () => {
    // Every OAuth signup starts roleless. Re-resolving them on every page load would undo the
    // point of the cache.
    const fetcher = backend(() =>
      jsonResponse({ id: 1, role_name: null, is_superuser: false }),
    );
    vi.stubGlobal("fetch", fetcher);

    await resolveSessionIdentity("session-1");
    await resolveSessionIdentity("session-1");

    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("keeps one session's identity out of another's", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<Fetcher>((_input, init) => {
        const isAdmin = new Headers(init?.headers).get("Cookie")?.includes(
          "admin",
        );

        return Promise.resolve(
          userResponse({ roleName: "user", isSuperuser: Boolean(isAdmin) }),
        );
      }),
    );

    await expect(resolveSessionIdentity("session-admin")).resolves.toEqual({
      status: "identified",
      identity: { roleName: "user", isSuperuser: true },
    });
    await expect(resolveSessionIdentity("session-plain")).resolves.toEqual({
      status: "identified",
      identity: { roleName: "user", isSuperuser: false },
    });
  });

  it("re-resolves once the sixty-second window closes", async () => {
    vi.useFakeTimers();
    const fetcher = backend();
    vi.stubGlobal("fetch", fetcher);

    await resolveSessionIdentity("session-1");

    vi.advanceTimersByTime(59_000);
    await resolveSessionIdentity("session-1");
    expect(fetcher).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(2_000);
    await resolveSessionIdentity("session-1");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
});

describe("the forwarded identity headers", () => {
  it("overwrites whatever the client sent", () => {
    const headers = new Headers({
      [SESSION_ROLE_HEADER]: "admin",
      [SESSION_SUPERUSER_HEADER]: "true",
    });

    applyForwardedIdentity(headers, { roleName: "user", isSuperuser: false });

    expect(readForwardedIdentity(headers)).toEqual({
      roleName: "user",
      isSuperuser: false,
    });
  });

  it("blanks a forged claim for a visitor with no identity", () => {
    const headers = new Headers({
      [SESSION_ROLE_HEADER]: "reviewer",
      [SESSION_SUPERUSER_HEADER]: "true",
    });

    applyForwardedIdentity(headers, null);

    expect(readForwardedIdentity(headers)).toEqual({
      roleName: null,
      isSuperuser: false,
    });
  });

  it("round-trips a superuser with no role", () => {
    const headers = new Headers();

    applyForwardedIdentity(headers, { roleName: null, isSuperuser: true });

    expect(readForwardedIdentity(headers)).toEqual({
      roleName: null,
      isSuperuser: true,
    });
  });

  it("reads nothing out of headers that were never set", () => {
    expect(readForwardedIdentity(new Headers())).toEqual({
      roleName: null,
      isSuperuser: false,
    });
  });
});
