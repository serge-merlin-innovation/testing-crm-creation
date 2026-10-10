import { getBackendUrl } from "./backend-url";

// Server-only: relays one browser request to FastAPI and its response back, so the backend can
// sit on a private network and session cookies bind to the origin serving the app.

// Hop-by-hop headers, plus ones the next hop must derive itself: `host` and `content-length` are
// recomputed for the target, `accept-encoding` is undici's own negotiation, and the forwarding /
// identity headers are the proxy's to write, never the client's.
const WITHHELD_FROM_BACKEND = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "expect",
  "host",
  "content-length",
  "accept-encoding",
  "forwarded",
  "x-forwarded-for",
  "x-forwarded-host",
  "x-forwarded-port",
  "x-forwarded-proto",
  "x-session-role",
  "x-session-superuser",
]);

// undici decodes the body but leaves `content-encoding`/`content-length` describing the
// compressed bytes; relaying either hands the browser something it cannot read.
const WITHHELD_FROM_BROWSER = new Set([
  "content-encoding",
  "content-length",
  "transfer-encoding",
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "te",
  "trailer",
  "upgrade",
  "strict-transport-security",
]);

const METHODS_WITHOUT_BODY = new Set(["GET", "HEAD"]);
const STATUSES_WITHOUT_BODY = new Set([204, 205, 304]);
const DEFAULT_TIMEOUT_MS = 30_000;

function getBackendTimeoutMs(): number {
  const configured = Number(process.env.BACKEND_TIMEOUT_MS ?? "");

  return Number.isInteger(configured) && configured > 0
    ? configured
    : DEFAULT_TIMEOUT_MS;
}

// The backend keys its login lockout on the client address, and every request reaches it from
// this server, so `x-forwarded-for` must be trusted only for as many hops as are actually in
// front of Next.js (BFF_TRUSTED_PROXY_HOPS) - otherwise a forged header is believed. Mirrors
// crudauth's `get_client_ip` (`parts[-min(hops, len)]`) so both ends read the chain the same way.
const UNTRUSTED = 0;

function getTrustedProxyHops(): number {
  // Number, not parseInt: a malformed value must fall back to trusting nothing, not to
  // whatever prefix parses.
  const configured = Number(process.env.BFF_TRUSTED_PROXY_HOPS ?? "");

  return Number.isInteger(configured) && configured > 0 ? configured : UNTRUSTED;
}

function resolveClientAddress(
  forwardedFor: string | null,
  trustedHops: number,
): string | null {
  if (trustedHops <= 0 || !forwardedFor) {
    return null;
  }

  const chain = forwardedFor
    .split(",")
    .map((address) => address.trim())
    .filter(Boolean);

  if (chain.length === 0) {
    return null;
  }

  // Count in from the right: the trusted proxies appended themselves last.
  return chain[chain.length - Math.min(trustedHops, chain.length)] ?? null;
}

function forwardedRequestHeaders(request: Request): Headers {
  const headers = new Headers();

  for (const [name, value] of request.headers) {
    if (!WITHHELD_FROM_BACKEND.has(name)) {
      headers.set(name, value);
    }
  }

  const clientAddress = resolveClientAddress(
    request.headers.get("x-forwarded-for"),
    getTrustedProxyHops(),
  );

  // Replace rather than append, so the backend sees only the address this server vouched for.
  if (clientAddress) {
    headers.set("x-forwarded-for", clientAddress);
  }

  return headers;
}

function relayedResponseHeaders(upstream: Response): Headers {
  const headers = new Headers();

  for (const [name, value] of upstream.headers) {
    if (name !== "set-cookie" && !WITHHELD_FROM_BROWSER.has(name)) {
      headers.append(name, value);
    }
  }

  // Every cookie needs its own line. Reading them back with `get` would join them on ", ", which
  // an `Expires` date also contains, so the join could never be undone.
  for (const cookie of upstream.headers.getSetCookie()) {
    headers.append("set-cookie", cookie);
  }

  return headers;
}

function gatewayFailure(detail: string, status: number): Response {
  return Response.json({ detail }, { status, headers: { "cache-control": "no-store" } });
}

export async function relayToBackend(request: Request): Promise<Response> {
  const { pathname, search } = new URL(request.url);
  const method = request.method.toUpperCase();

  // Node rejects a GET carrying a body at all, including an empty one.
  const body = METHODS_WITHOUT_BODY.has(method)
    ? undefined
    : await request.arrayBuffer();

  let upstream: Response;

  try {
    upstream = await fetch(getBackendUrl(pathname, search), {
      method,
      headers: forwardedRequestHeaders(request),
      body,
      // The OAuth callback's redirect belongs to the browser: the session is minted on it, and
      // following it here would swallow both the Location and the cookies.
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.timeout(getBackendTimeoutMs()),
    });
  } catch (error) {
    // Neither is a 401, so apiFetch will not read an outage as a dead session and eject the
    // visitor to the login page.
    return error instanceof Error && error.name === "TimeoutError"
      ? gatewayFailure("The backend took too long to answer.", 504)
      : gatewayFailure("We could not reach the backend.", 502);
  }

  return new Response(
    STATUSES_WITHOUT_BODY.has(upstream.status) ? null : upstream.body,
    {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: relayedResponseHeaders(upstream),
    },
  );
}
