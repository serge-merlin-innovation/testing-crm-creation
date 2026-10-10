import { relayToBackend } from "@/lib/backend-relay";

/**
 * The one door to FastAPI. Every browser call arrives on this origin and is relayed on, so the
 * backend never appears in a URL the browser sees and the session cookies bind here.
 *
 * `[...path]` exists only to make every `/api/v1/...` path match — the upstream path is read off
 * the request URL, never rebuilt from `params`, which hands back *decoded* segments that would let
 * a request walk out of the API surface. Mounting under `/api/v1/` rather than `/api/` is what
 * keeps `/docs`, `/openapi.json` and `/health` off the relay: Next answers those 404 without
 * a round trip.
 *
 * `OPTIONS` is deliberately absent. Next implements it with a correct `Allow` header, and a
 * same-origin caller never sends a preflight.
 */
export const GET = relayToBackend;
export const HEAD = relayToBackend;
export const POST = relayToBackend;
export const PUT = relayToBackend;
export const PATCH = relayToBackend;
export const DELETE = relayToBackend;
