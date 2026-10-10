import { cookies } from "next/headers";
import { SESSION_COOKIE } from "./auth-routing";
import { getBackendUrl } from "./backend-url";

// Server-only: asks FastAPI on behalf of the signed-in reader, forwarding only their session
// cookie. FastAPI still authorizes the call, so a hidden deal comes back 404 here too.
export async function fetchAsReader(path: string): Promise<Response | null> {
  const sessionId = (await cookies()).get(SESSION_COOKIE)?.value;
  const url = new URL(path, "http://backend.internal");

  try {
    return await fetch(getBackendUrl(url.pathname, url.search), {
      headers: sessionId ? { Cookie: `${SESSION_COOKIE}=${sessionId}`, Accept: "application/json" } : {},
      cache: "no-store",
    });
  } catch {
    return null;
  }
}
