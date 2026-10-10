import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  applyForwardedIdentity,
  clearSessionIdentityCache,
  readForwardedIdentity,
  resolveSessionIdentity,
  SESSION_ROLE_HEADER,
  SESSION_PERMISSIONS_HEADER,
} from "@/lib/session-identity";

const backendOrigin = "http://backend.test";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function userResponse(
  { roleName, permissions }: { roleName: string | null; permissions: string[] | null },
): Response {
  return jsonResponse({
    id: 1,
    email: "ann@firm.be",
    role_name: roleName,
    permissions,
  });
}

const ANALYST = { roleName: "Analyst / Associate", permissions: ["deals.read_staffed"] };
const ADMIN = { roleName: "Admin", permissions: ["roles.manage", "users.manage"] };

type Fetcher = (
  input: URL | RequestInfo,
  init?: RequestInit,
) => Promise<Response>;

function backend(
  user: () => Response = () =>
    userResponse(ANALYST),
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
  it("names the role and permissions the backend reported", async () => {
    vi.stubGlobal("fetch", backend());

    await expect(resolveSessionIdentity("session-1")).resolves.toEqual({
      status: "identified",
      identity: ANALYST,
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

  // The pair below is the distinction the whole gate rests on: a body that is not a user means
  // the backend is misbehaving and nothing can be judged, while a missing role is a real answer.
  it("reports the backend unavailable on a body it cannot read", async () => {
    vi.stubGlobal(
      "fetch",
      backend(() => jsonResponse({ id: 1 })),
    );

    await expect(resolveSessionIdentity("session-1")).resolves.toEqual({
      status: "unavailable",
    });
  });

  it("identifies a user the backend gave no role, with no permissions", async () => {
    vi.stubGlobal(
      "fetch",
      backend(() => userResponse({ roleName: null, permissions: null })),
    );

    await expect(resolveSessionIdentity("session-1")).resolves.toEqual({
      status: "identified",
      identity: { roleName: null, permissions: [] },
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
    const fetcher = backend(() => userResponse({ roleName: null, permissions: null }));
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

        return Promise.resolve(userResponse(isAdmin ? ADMIN : ANALYST));
      }),
    );

    await expect(resolveSessionIdentity("session-admin")).resolves.toEqual({
      status: "identified",
      identity: ADMIN,
    });
    await expect(resolveSessionIdentity("session-plain")).resolves.toEqual({
      status: "identified",
      identity: ANALYST,
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
      [SESSION_ROLE_HEADER]: "Admin",
      [SESSION_PERMISSIONS_HEADER]: "roles.manage",
    });

    applyForwardedIdentity(headers, ANALYST);

    expect(readForwardedIdentity(headers)).toEqual(ANALYST);
  });

  it("blanks a forged claim for a visitor with no identity", () => {
    const headers = new Headers({
      [SESSION_ROLE_HEADER]: "Admin",
      [SESSION_PERMISSIONS_HEADER]: "users.manage",
    });

    applyForwardedIdentity(headers, null);

    expect(readForwardedIdentity(headers)).toEqual({ roleName: null, permissions: [] });
  });

  it("round-trips several permissions", () => {
    const headers = new Headers();

    applyForwardedIdentity(headers, ADMIN);

    expect(readForwardedIdentity(headers)).toEqual(ADMIN);
  });

  it("reads nothing out of headers that were never set", () => {
    expect(readForwardedIdentity(new Headers())).toEqual({ roleName: null, permissions: [] });
  });
});
