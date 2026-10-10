import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import {
  DEFAULT_AUTHENTICATED_PATH,
  LOGIN_PATH,
  sanitizeReturnTo,
  SESSION_COOKIE,
} from "./lib/auth-routing";
import {
  audienceFor,
  normalizePagePath,
  satisfiesAudience,
  type SessionIdentity,
} from "./lib/page-audience";
import {
  applyForwardedIdentity,
  resolveSessionIdentity,
} from "./lib/session-identity";

/**
 * The page gate. Three tiers, cheapest first:
 *
 *   1. is this page public at all?  — the audience manifest, free
 *   2. is there a session cookie?   — free, but cannot tell a live session from a dead one
 *   3. whose session is it?         — one backend resolve, cached for a minute
 *
 * FastAPI is still the security boundary and authorizes every data call. These tiers exist so a
 * visitor never renders a page they cannot use.
 */
function allow(request: NextRequest, identity: SessionIdentity | null) {
  const headers = new Headers(request.headers);

  applyForwardedIdentity(headers, identity);

  return NextResponse.next({ request: { headers } });
}

function sendToLogin(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const loginUrl = new URL(LOGIN_PATH, request.url);

  loginUrl.searchParams.set("next", sanitizeReturnTo(`${pathname}${search}`));

  return NextResponse.redirect(loginUrl);
}

/**
 * Signed in but not entitled goes to the landing page, not to login — bouncing an authenticated
 * visitor back to sign in reads as a broken session. Gating the landing page itself above someone's
 * audience would loop, so that case is refused outright.
 */
function refuse(request: NextRequest) {
  if (normalizePagePath(request.nextUrl.pathname) === DEFAULT_AUTHENTICATED_PATH) {
    return new NextResponse("Forbidden", { status: 403 });
  }

  return NextResponse.redirect(new URL(DEFAULT_AUTHENTICATED_PATH, request.url));
}

/** A signed-in page must not live in the browser cache, or Back after Log out would show it again. */
function uncached(response: NextResponse) {
  response.headers.set("Cache-Control", "private, no-store");
  return response;
}

export async function proxy(request: NextRequest) {
  const audience = audienceFor(request.nextUrl.pathname);

  // Tier 1. Public pages return before the resolve, so they never pay for it.
  if (audience.kind === "public") {
    return allow(request, null);
  }

  return uncached(await gate(request, audience));
}

async function gate(request: NextRequest, audience: ReturnType<typeof audienceFor>) {

  // Tier 2. Presence only — an expired cookie looks exactly like a live one from here.
  const sessionId = request.cookies.get(SESSION_COOKIE)?.value;

  if (!sessionId) {
    return sendToLogin(request);
  }

  // Tier 3. Every gated page needs this: the navbar is fed from the identity headers it writes.
  const resolved = await resolveSessionIdentity(sessionId);

  if (resolved.status === "rejected") {
    return sendToLogin(request);
  }

  // The backend could not answer, so the session stands and only the pages that needed a
  // permission are refused. Treating this as a rejection would sign everyone out on a hiccup.
  if (resolved.status === "unavailable") {
    return audience.kind === "authenticated" ? allow(request, null) : refuse(request);
  }

  const { identity } = resolved;

  if (!satisfiesAudience(audience, { isAuthenticated: true, ...identity })) {
    return refuse(request);
  }

  return allow(request, identity);
}

/**
 * Default-deny: everything except the API, the framework's own assets, a short root-file list, and
 * anything with a file extension. A new route is gated the moment it exists.
 */
export const config = {
  matcher: [
    "/((?!api(?:/|$)|_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml|manifest.webmanifest|.*\\.[^/]+$).*)",
  ],
};
