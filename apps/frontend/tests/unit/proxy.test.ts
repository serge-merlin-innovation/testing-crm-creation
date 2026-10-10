import { NextRequest } from "next/server";
import {
  getRedirectUrl,
  unstable_doesMiddlewareMatch,
} from "next/experimental/testing/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearSessionIdentityCache } from "@/lib/session-identity";
import { config, proxy } from "@/proxy";

const frontendOrigin = "https://app.example.test";

function request(
  pathname: string,
  init: ConstructorParameters<typeof NextRequest>[1] = {},
) {
  return new NextRequest(`${frontendOrigin}${pathname}`, init);
}

function signedIn(pathname: string, headers: Record<string, string> = {}) {
  return request(pathname, {
    headers: { Cookie: "session_id=session-1", ...headers },
  });
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type Fetcher = (
  input: URL | RequestInfo,
  init?: RequestInit,
) => Promise<Response>;

function backendAnswering(
  user: { roleName: string | null; permissions: string[] } | number,
) {
  return vi.fn<Fetcher>(() =>
    Promise.resolve(
      typeof user === "number"
        ? jsonResponse({ detail: "nope" }, user)
        : jsonResponse({
            id: 1,
            email: "ann@firm.be",
            role_name: user.roleName,
            permissions: user.roleName ? user.permissions : null,
          }),
    ),
  );
}

function forwardedIdentity(response: Response) {
  return {
    role: response.headers.get("x-middleware-request-x-session-role"),
    permissions: response.headers.get("x-middleware-request-x-session-permissions"),
  };
}

beforeEach(() => {
  // The identity cache lives at module scope; without this one test's session leaks into the next.
  clearSessionIdentityCache();
  vi.stubEnv("BACKEND_URL", "http://backend.test");
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("the matcher", () => {
  it.each([
    ["/overview", true],
    ["/users", true],
    ["/api/v1/auth/login", false],
    ["/_next/static/chunk.js", false],
    ["/favicon.ico", false],
    ["/logo.svg", false],
  ])("matches %s → %s", (url, matches) => {
    expect(unstable_doesMiddlewareMatch({ config, nextConfig: {}, url })).toBe(
      matches,
    );
  });
});

describe("tier 1: public pages", () => {
  it.each(["/", "/login"])("lets %s through without calling the backend", async (path) => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);

    const response = await proxy(request(path));

    expect(response.headers.get("x-middleware-next")).toBe("1");
    expect(getRedirectUrl(response)).toBeNull();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("lets a stale session sit on the login page rather than looping", async () => {
    vi.stubGlobal("fetch", backendAnswering(401));

    const response = await proxy(signedIn("/login"));

    expect(getRedirectUrl(response)).toBeNull();
  });
});

describe("tier 2: no session", () => {
  it("sends a signed-out visitor to login, keeping where they were going", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);

    const redirectUrl = new URL(
      getRedirectUrl(await proxy(request("/analytics?range=week")))!,
    );

    expect(redirectUrl.pathname).toBe("/login");
    expect(redirectUrl.searchParams.get("next")).toBe("/analytics?range=week");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("gates a path nobody listed", async () => {
    vi.stubGlobal("fetch", vi.fn());

    expect(
      new URL(getRedirectUrl(await proxy(request("/reports")))!).pathname,
    ).toBe("/login");
  });
});

describe("tier 3: who the session belongs to", () => {
  const admin = { roleName: "Admin", permissions: ["users.manage", "roles.manage", "settings.manage", "audit.read"] };
  const analyst = { roleName: "Analyst / Associate", permissions: ["deals.read_staffed", "deals.edit_staffed"] };
  const readOnly = { roleName: "Read-only", permissions: ["dashboard.aggregated"] };
  const roleless = { roleName: null, permissions: [] };

  it.each([
    ["/overview", admin, true],
    ["/overview", analyst, true],
    ["/overview", roleless, true],
    ["/users", admin, true],
    ["/users", analyst, false],
    ["/users", roleless, false],
    ["/users/42", analyst, false],
    ["/permissions", admin, true],
    ["/permissions", readOnly, false],
    ["/analytics", readOnly, true],
    ["/analytics", analyst, false],
    ["/analytics", admin, false],
  ])("%s for %o → allowed: %s", async (path, viewer, allowed) => {
    vi.stubGlobal("fetch", backendAnswering(viewer));

    const response = await proxy(signedIn(path));

    expect(getRedirectUrl(response)).toBe(allowed ? null : `${frontendOrigin}/overview`);
  });

  it("signs out a session the backend no longer recognises", async () => {
    vi.stubGlobal("fetch", backendAnswering(401));

    const redirectUrl = new URL(getRedirectUrl(await proxy(signedIn("/users")))!);

    expect(redirectUrl.pathname).toBe("/login");
    expect(redirectUrl.searchParams.get("next")).toBe("/users");
  });
});

describe("when the backend cannot answer", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("ECONNREFUSED"))),
    );
  });

  it("keeps the session on the pages the cookie alone earns", async () => {
    const response = await proxy(signedIn("/overview"));

    expect(response.headers.get("x-middleware-next")).toBe("1");
    expect(getRedirectUrl(response)).toBeNull();
  });

  it("refuses only what needed a role", async () => {
    expect(getRedirectUrl(await proxy(signedIn("/users")))).toBe(
      `${frontendOrigin}/overview`,
    );
  });

  it("does not claim an identity it could not resolve", async () => {
    expect(forwardedIdentity(await proxy(signedIn("/overview")))).toEqual({
      role: "",
      permissions: "",
    });
  });
});

describe("the forwarded identity", () => {
  it("carries the resolved role and permissions to the page", async () => {
    vi.stubGlobal("fetch", backendAnswering({ roleName: "Read-only", permissions: ["dashboard.aggregated"] }));

    expect(forwardedIdentity(await proxy(signedIn("/overview")))).toEqual({
      role: "Read-only",
      permissions: "dashboard.aggregated",
    });
  });

  it("blanks the headers for an anonymous visitor to a public page", async () => {
    vi.stubGlobal("fetch", vi.fn());

    expect(
      forwardedIdentity(
        await proxy(
          request("/", { headers: { "x-session-permissions": "users.manage" } }),
        ),
      ),
    ).toEqual({ role: "", permissions: "" });
  });

  it("overwrites a hand-written permissions header instead of trusting it", async () => {
    vi.stubGlobal("fetch", backendAnswering({ roleName: "Read-only", permissions: ["dashboard.aggregated"] }));

    const response = await proxy(
      signedIn("/users", {
        "x-session-permissions": "users.manage",
        "x-session-role": "Admin",
      }),
    );

    expect(getRedirectUrl(response)).toBe(`${frontendOrigin}/overview`);
  });

  it("gains nothing from a forged superuser cookie", async () => {
    vi.stubGlobal("fetch", backendAnswering({ roleName: "Read-only", permissions: ["dashboard.aggregated"] }));

    const response = await proxy(
      request("/users", {
        headers: {
          Cookie: "session_id=session-1; session_is_superuser=true; session_role_id=1",
        },
      }),
    );

    expect(getRedirectUrl(response)).toBe(`${frontendOrigin}/overview`);
  });

  it("sends the backend the session cookie and nothing else", async () => {
    const fetcher = backendAnswering({ roleName: "Read-only", permissions: ["dashboard.aggregated"] });
    vi.stubGlobal("fetch", fetcher);

    await proxy(
      request("/overview", {
        headers: {
          Cookie: "session_id=session-1; tracking_id=abc; session_is_superuser=true",
        },
      }),
    );

    const [, init] = fetcher.mock.calls[0];

    expect(new Headers(init?.headers).get("Cookie")).toBe(
      "session_id=session-1",
    );
  });
});

describe("signed-in pages are never cached (AUTH-04 c2)", () => {
  it("marks a gated page no-store so Back after Log out asks the server again", async () => {
    vi.stubGlobal("fetch", backendAnswering({ roleName: "Partner", permissions: [] }));

    const response = await proxy(signedIn("/overview"));

    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
  });

  it("sends a revoked session's Back navigation to login instead of the page", async () => {
    vi.stubGlobal("fetch", backendAnswering(401));

    const response = await proxy(signedIn("/overview"));

    expect(getRedirectUrl(response)).toContain("/login");
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
  });
});

describe("the user's language follows them to every device (NFR-04 c1)", () => {
  function backendWithLanguage(language: string) {
    return vi.fn<Fetcher>(() =>
      Promise.resolve(
        jsonResponse({ id: 1, email: "ann@firm.be", role_name: "Partner", permissions: ["deals.read_staffed"], language }),
      ),
    );
  }

  it("renders the page in the saved language and keeps it in the lang cookie", async () => {
    vi.stubGlobal("fetch", backendWithLanguage("nl"));

    const response = await proxy(signedIn("/overview"));

    expect(response.headers.get("x-middleware-request-cookie")).toContain("lang=nl");
    expect(response.cookies.get("lang")?.value).toBe("nl");
  });

  it("leaves the cookie alone when it already matches", async () => {
    vi.stubGlobal("fetch", backendWithLanguage("fr"));

    const response = await proxy(signedIn("/overview", { Cookie: "session_id=session-1; lang=fr" }));

    expect(response.cookies.get("lang")).toBeUndefined();
  });
});
