const DEFAULT_BACKEND_URL = "http://localhost:8000";

// Server-only and read at runtime: the private backend origin must never enter the browser bundle.
export function getBackendUrl(pathname: string, search = ""): URL {
  const target = new URL(process.env.BACKEND_URL ?? DEFAULT_BACKEND_URL);

  target.pathname = pathname;
  target.search = search;
  target.hash = "";
  return target;
}
