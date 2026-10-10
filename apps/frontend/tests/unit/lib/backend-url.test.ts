import { afterEach, describe, expect, it, vi } from "vitest";
import { getBackendUrl } from "@/lib/backend-url";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("getBackendUrl", () => {
  it("reads the server-only BACKEND_URL, never a bundled public one", () => {
    vi.stubEnv("BACKEND_URL", "https://server-api.example.test");
    vi.stubEnv("NEXT_PUBLIC_BACKEND_URL", "https://ignored-public-api.example.test");

    expect(getBackendUrl("/api/v1/auth/check-auth").toString()).toBe(
      "https://server-api.example.test/api/v1/auth/check-auth",
    );
  });

  it("preserves the requested query string", () => {
    vi.stubEnv("BACKEND_URL", "https://server-api.example.test");

    expect(getBackendUrl("/api/v1/users", "?limit=10").toString()).toBe(
      "https://server-api.example.test/api/v1/users?limit=10",
    );
  });

  it("falls back to the local backend when nothing is configured", () => {
    expect(getBackendUrl("/api/v1/users").toString()).toBe(
      "http://localhost:8000/api/v1/users",
    );
  });
});
