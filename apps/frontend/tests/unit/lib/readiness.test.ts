import { describe, expect, it, vi } from "vitest";
import { unstable_doesMiddlewareMatch } from "next/experimental/testing/server";
import { audienceFor } from "@/lib/page-audience";
import { config } from "@/proxy";
import { readiness } from "@/lib/readiness";

describe("the uptime probe's readiness URL (NFR-03)", () => {
  it("is ready when the backend and its database answer", async () => {
    const fetcher = vi.fn((input: URL | RequestInfo) => Promise.resolve(Response.json({ status: "ready", input: String(input) })));
    const response = await readiness(fetcher as unknown as typeof fetch);
    expect(response.status).toBe(200);
    expect(String(fetcher.mock.calls[0]?.[0])).toContain("/health/ready");
  });

  it.each([
    ["the backend reports its database down", () => Promise.resolve(new Response("{}", { status: 503 }))],
    ["the backend does not answer", () => Promise.reject(new Error("ECONNREFUSED"))],
  ])("is 503 when %s", async (_, answer) => {
    const response = await readiness(vi.fn(answer) as unknown as typeof fetch);
    expect(response.status).toBe(503);
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it("is public: the probe has no session", () => {
    expect(audienceFor("/health/ready").kind).toBe("public");
    expect(unstable_doesMiddlewareMatch({ config, url: "/health/ready" })).toBe(false);
  });
});
