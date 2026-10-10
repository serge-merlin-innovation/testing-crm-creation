export const DEFAULT_AUTHENTICATED_PATH = "/overview";
export const LOGIN_PATH = "/login";

/** The session cookie crudauth sets on login. It is httpOnly, so nothing in the browser
 *  can read it — only the proxy and Server Components see it. */
export const SESSION_COOKIE = "session_id";

export function sanitizeReturnTo(value: string | null | undefined): string {
  if (
    !value ||
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.includes("\\")
  ) {
    return DEFAULT_AUTHENTICATED_PATH;
  }

  try {
    // The guard above accepted a site-relative path, which `new URL` cannot parse alone.
    // The base is a throwaway origin: only pathname and search are ever read back out.
    const parsed = new URL(value, "http://relative.invalid");

    if (
      parsed.pathname === LOGIN_PATH
    ) {
      return DEFAULT_AUTHENTICATED_PATH;
    }

    return `${parsed.pathname}${parsed.search}`;
  } catch {
    return DEFAULT_AUTHENTICATED_PATH;
  }
}
