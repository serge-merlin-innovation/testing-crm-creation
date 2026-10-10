import { getBackendUrl } from "./backend-url";

/**
 * What the uptime probe (infra/uptime-monitor.bicep, NFR-03) calls on the public origin: this app
 * answers, and so do the backend and its database behind it. Never cached.
 */
export async function readiness(fetcher: typeof fetch = fetch): Promise<Response> {
  const headers = { "cache-control": "no-store" };
  try {
    const backend = await fetcher(getBackendUrl("/health/ready"), { cache: "no-store", signal: AbortSignal.timeout(10_000) });
    if (backend.ok) {
      return Response.json({ status: "ready", frontend: "ok", backend: "ok" }, { headers });
    }
  } catch {
    // Falls through to unavailable.
  }
  return Response.json({ status: "unavailable", frontend: "ok", backend: "unavailable" }, { status: 503, headers });
}
