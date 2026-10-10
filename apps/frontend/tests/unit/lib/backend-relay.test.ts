import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { relayToBackend } from "@/lib/backend-relay";

type Fetcher = (
  input: URL | RequestInfo,
  init?: RequestInit,
) => Promise<Response>;

function browserRequest(
  url: string,
  init: RequestInit = {},
): Request {
  return new Request(`http://app.example.test${url}`, init);
}

function backendReturning(upstream: Response) {
  return vi.fn<Fetcher>(() => Promise.resolve(upstream));
}

function relayedCall(fetcher: ReturnType<typeof backendReturning>) {
  const [target, init] = fetcher.mock.calls[0];

  return { target: String(target), init: init ?? {} };
}

async function relayedRequestHeaders(init: RequestInit = {}): Promise<Headers> {
  const fetcher = backendReturning(new Response("{}"));
  vi.stubGlobal("fetch", fetcher);

  await relayToBackend(browserRequest("/api/v1/orders", init));

  return new Headers(relayedCall(fetcher).init.headers);
}

async function relayedResponseHeaders(upstream: Response): Promise<Headers> {
  vi.stubGlobal("fetch", backendReturning(upstream));

  return (await relayToBackend(browserRequest("/api/v1/orders"))).headers;
}

async function relayedClientAddress(
  forwardedFor: string | null,
): Promise<string | null> {
  const headers = await relayedRequestHeaders(
    forwardedFor === null ? {} : { headers: { "X-Forwarded-For": forwardedFor } },
  );

  return headers.get("x-forwarded-for");
}

async function relayedTimeoutMs(): Promise<number> {
  const timeout = vi.spyOn(AbortSignal, "timeout");
  vi.stubGlobal("fetch", backendReturning(new Response("{}")));

  await relayToBackend(browserRequest("/api/v1/roles/"));

  return timeout.mock.calls[0][0];
}

beforeEach(() => {
  vi.stubEnv("BACKEND_URL", "http://backend.test:8000");
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("the relayed target", () => {
  it("keeps the path and query the browser asked for", async () => {
    const fetcher = backendReturning(new Response("{}"));
    vi.stubGlobal("fetch", fetcher);

    await relayToBackend(browserRequest("/api/v1/roles/?page=1&per=100"));

    expect(relayedCall(fetcher).target).toBe(
      "http://backend.test:8000/api/v1/roles/?page=1&per=100",
    );
  });

  it("keeps percent-encoding intact rather than decoding it into new path segments", async () => {
    const fetcher = backendReturning(new Response("{}"));
    vi.stubGlobal("fetch", fetcher);

    await relayToBackend(browserRequest("/api/v1/items/a%2Fb?q=x%20y"));

    expect(relayedCall(fetcher).target).toBe(
      "http://backend.test:8000/api/v1/items/a%2Fb?q=x%20y",
    );
  });

  it("cannot be walked out of the backend origin with dot segments", async () => {
    const fetcher = backendReturning(new Response("{}"));
    vi.stubGlobal("fetch", fetcher);

    await relayToBackend(browserRequest("/api/v1/../../etc/passwd"));

    expect(relayedCall(fetcher).target.startsWith("http://backend.test:8000/")).toBe(
      true,
    );
  });
});

describe("the headers the backend receives", () => {
  it("carries the headers the backend authorizes and identifies on", async () => {
    const headers = await relayedRequestHeaders({
      headers: {
        Cookie: "session_id=session-1; csrf_token=abc",
        "X-CSRF-Token": "abc",
        Authorization: "Bearer key-1",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
        Accept: "application/json",
      },
    });

    expect(headers.get("cookie")).toBe("session_id=session-1; csrf_token=abc");
    expect(headers.get("x-csrf-token")).toBe("abc");
    expect(headers.get("authorization")).toBe("Bearer key-1");
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("user-agent")).toBe("Mozilla/5.0");
    expect(headers.get("accept")).toBe("application/json");
  });

  it("drops the headers the next hop must compute for itself", async () => {
    const headers = await relayedRequestHeaders({
      method: "POST",
      body: "{}",
      headers: {
        Host: "app.example.test",
        "Accept-Encoding": "br, zstd",
        Connection: "keep-alive",
      },
    });

    for (const dropped of ["host", "accept-encoding", "connection", "content-length"]) {
      expect(headers.get(dropped)).toBeNull();
    }
  });

  it("refuses a forged identity header rather than passing it to the backend", async () => {
    const headers = await relayedRequestHeaders({
      headers: {
        "x-session-role": "admin",
        "x-session-superuser": "true",
      },
    });

    expect(headers.get("x-session-role")).toBeNull();
    expect(headers.get("x-session-superuser")).toBeNull();
  });

  it("drops the other forwarding headers so only ours reaches the backend", async () => {
    const headers = await relayedRequestHeaders({
      headers: {
        Forwarded: "for=9.9.9.9",
        "X-Forwarded-Host": "evil.test",
        "X-Forwarded-Proto": "https",
      },
    });

    expect(headers.get("forwarded")).toBeNull();
    expect(headers.get("x-forwarded-host")).toBeNull();
    expect(headers.get("x-forwarded-proto")).toBeNull();
  });
});

describe("the client address the relay vouches for", () => {
  it("sends none by default, because an unfronted Next.js cannot vouch for the header", async () => {
    await expect(relayedClientAddress("203.0.113.7")).resolves.toBeNull();
  });

  it("replaces a spoofed chain with the one address it vouches for", async () => {
    vi.stubEnv("BFF_TRUSTED_PROXY_HOPS", "1");

    await expect(
      relayedClientAddress("9.9.9.9, 203.0.113.7"),
    ).resolves.toBe("203.0.113.7");
  });

  it("takes the address the single trusted proxy appended", async () => {
    vi.stubEnv("BFF_TRUSTED_PROXY_HOPS", "1");

    await expect(relayedClientAddress("203.0.113.7")).resolves.toBe(
      "203.0.113.7",
    );
  });

  it.each([
    ["1", "10.0.0.2"],
    ["2", "10.0.0.1"],
    ["3", "203.0.113.7"],
  ])("skips past the %s proxies it trusts to reach the client", async (hops, expected) => {
    vi.stubEnv("BFF_TRUSTED_PROXY_HOPS", hops);

    await expect(
      relayedClientAddress("203.0.113.7, 10.0.0.1, 10.0.0.2"),
    ).resolves.toBe(expected);
  });

  it("clamps to the leftmost entry when the chain is shorter than the hop count", async () => {
    vi.stubEnv("BFF_TRUSTED_PROXY_HOPS", "5");

    await expect(relayedClientAddress("203.0.113.7")).resolves.toBe(
      "203.0.113.7",
    );
  });

  it("ignores the whitespace around each entry", async () => {
    vi.stubEnv("BFF_TRUSTED_PROXY_HOPS", "1");

    await expect(
      relayedClientAddress("  203.0.113.7 ,  10.0.0.1  "),
    ).resolves.toBe("10.0.0.1");
  });

  it.each(["", "not-a-number", "-1", "1.5"])(
    "trusts nothing when the hop count is %o",
    async (configured) => {
      vi.stubEnv("BFF_TRUSTED_PROXY_HOPS", configured);

      await expect(
        relayedClientAddress("9.9.9.9, 203.0.113.7"),
      ).resolves.toBeNull();
    },
  );

  it.each([null, "", ",", " , , "])(
    "vouches for nothing given %o",
    async (forwardedFor) => {
      vi.stubEnv("BFF_TRUSTED_PROXY_HOPS", "1");

      await expect(relayedClientAddress(forwardedFor)).resolves.toBeNull();
    },
  );
});

describe("the relayed request", () => {
  it("asks the backend not to follow redirects on our behalf", async () => {
    const fetcher = backendReturning(new Response("{}"));
    vi.stubGlobal("fetch", fetcher);

    await relayToBackend(browserRequest("/api/v1/roles/"));

    const { init } = relayedCall(fetcher);

    expect(init.redirect).toBe("manual");
    expect(init.cache).toBe("no-store");
  });

  it("sends no body on a GET, which Node rejects outright", async () => {
    const fetcher = backendReturning(new Response("{}"));
    vi.stubGlobal("fetch", fetcher);

    await relayToBackend(browserRequest("/api/v1/roles/"));

    expect(relayedCall(fetcher).init.body).toBeUndefined();
  });

  it("carries a write's body through byte for byte", async () => {
    const fetcher = backendReturning(new Response("{}"));
    vi.stubGlobal("fetch", fetcher);

    await relayToBackend(
      browserRequest("/api/v1/auth/login", {
        method: "POST",
        body: "username=userson&password=hunter2",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      }),
    );

    const { init } = relayedCall(fetcher);

    expect(init.method).toBe("POST");
    expect(new TextDecoder().decode(init.body as ArrayBuffer)).toBe(
      "username=userson&password=hunter2",
    );
  });

  it("bounds the exchange by default so a hung backend cannot pin a handler", async () => {
    await expect(relayedTimeoutMs()).resolves.toBe(30_000);
  });

  it("reads the configured timeout", async () => {
    vi.stubEnv("BACKEND_TIMEOUT_MS", "5000");

    await expect(relayedTimeoutMs()).resolves.toBe(5_000);
  });

  it.each(["0", "-1", "soon"])("falls back to the default timeout for %o", async (configured) => {
    vi.stubEnv("BACKEND_TIMEOUT_MS", configured);

    await expect(relayedTimeoutMs()).resolves.toBe(30_000);
  });
});

describe("the relayed response", () => {
  it("hands the browser the status and body the backend produced", async () => {
    vi.stubGlobal(
      "fetch",
      backendReturning(
        new Response('{"detail":"Not authenticated"}', { status: 401 }),
      ),
    );

    const relayed = await relayToBackend(browserRequest("/api/v1/users/me"));

    expect(relayed.status).toBe(401);
    await expect(relayed.json()).resolves.toEqual({
      detail: "Not authenticated",
    });
  });

  it("drops the framing undici already resolved", async () => {
    // undici decodes the body but leaves both headers behind, and the length is the
    // compressed one — relaying either hands the browser something it cannot read.
    const headers = await relayedResponseHeaders(
      new Response("a decoded body", {
        headers: {
          "Content-Encoding": "gzip",
          "Content-Length": "60",
          "Content-Type": "application/json",
        },
      }),
    );

    expect(headers.get("content-encoding")).toBeNull();
    expect(headers.get("content-length")).toBeNull();
    expect(headers.get("content-type")).toBe("application/json");
  });

  it("keeps the backend's caching and custom headers", async () => {
    const headers = await relayedResponseHeaders(
      new Response("{}", {
        headers: {
          "Cache-Control": "private, no-cache, no-store, must-revalidate",
          "X-Request-Id": "req-123",
        },
      }),
    );

    expect(headers.get("cache-control")).toBe(
      "private, no-cache, no-store, must-revalidate",
    );
    expect(headers.get("x-request-id")).toBe("req-123");
  });

  it("lets the frontend origin own its own transport security", async () => {
    const headers = await relayedResponseHeaders(
      new Response("{}", {
        headers: { "Strict-Transport-Security": "max-age=31536000" },
      }),
    );

    expect(headers.get("strict-transport-security")).toBeNull();
  });

  it("passes a redirect to the browser with each cookie on its own line", async () => {
    // This is the OAuth callback: the session is minted on the 302, and following it
    // here would swallow both the Location and the cookies. Folding them into one
    // comma-joined value is unrecoverable, because an Expires date contains a comma.
    const upstream = new Response(null, {
      status: 302,
      headers: { Location: "http://app.example.test/overview" },
    });
    upstream.headers.append(
      "Set-Cookie",
      "session_id=abc; Path=/; HttpOnly; SameSite=lax; Expires=Wed, 21 Oct 2026 07:28:00 GMT",
    );
    upstream.headers.append("Set-Cookie", "csrf_token=xyz; Path=/; SameSite=lax");
    vi.stubGlobal("fetch", backendReturning(upstream));

    const relayed = await relayToBackend(
      browserRequest("/api/v1/auth/oauth/callback/microsoft?code=1&state=2"),
    );

    expect(relayed.status).toBe(302);
    expect(relayed.headers.get("location")).toBe(
      "http://app.example.test/overview",
    );
    expect(relayed.headers.getSetCookie()).toEqual([
      "session_id=abc; Path=/; HttpOnly; SameSite=lax; Expires=Wed, 21 Oct 2026 07:28:00 GMT",
      "csrf_token=xyz; Path=/; SameSite=lax",
    ]);
  });

  it("relays an empty response without trying to give it a body", async () => {
    vi.stubGlobal("fetch", backendReturning(new Response(null, { status: 204 })));

    const relayed = await relayToBackend(
      browserRequest("/api/v1/orders/1", { method: "DELETE" }),
    );

    expect(relayed.status).toBe(204);
    expect(relayed.body).toBeNull();
  });
});

describe("when the backend does not answer", () => {
  it("reports it as a gateway failure the sign-in form can render", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("fetch failed"))),
    );

    const relayed = await relayToBackend(browserRequest("/api/v1/users/me"));

    expect(relayed.status).toBe(502);
    await expect(relayed.json()).resolves.toEqual({
      detail: "We could not reach the backend.",
    });
  });

  it("reports a timeout separately from an outright failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.reject(new DOMException("The operation timed out.", "TimeoutError")),
      ),
    );

    const relayed = await relayToBackend(browserRequest("/api/v1/users/me"));

    expect(relayed.status).toBe(504);
    await expect(relayed.json()).resolves.toEqual({
      detail: "The backend took too long to answer.",
    });
  });

  it("never bounces the visitor to login for an outage", async () => {
    // apiFetch bounces on 401 only, so a gateway failure must not wear that status.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("fetch failed"))),
    );

    const relayed = await relayToBackend(browserRequest("/api/v1/users/me"));

    expect(relayed.status).not.toBe(401);
  });
});
