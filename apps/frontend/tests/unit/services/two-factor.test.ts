import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.resetModules();
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("two-step sign-in", () => {
  it("reports that the password passed and a code is now due", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ step: "code", challenge: "c-1" })));
    const { login } = await import("@/services/auth");

    await expect(login("ana@firm.be", "pw")).resolves.toEqual({ step: "code", challenge: "c-1" });
  });

  it("hands over the QR code on a first sign-in", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ step: "enrol", challenge: "c-1", otpauth_uri: "otpauth://totp/x", qr_svg: "<svg/>" }),
      ),
    );
    const { login } = await import("@/services/auth");

    await expect(login("ana@firm.be", "pw")).resolves.toEqual({
      step: "enrol",
      challenge: "c-1",
      otpauthUri: "otpauth://totp/x",
      qrSvg: "<svg/>",
    });
  });

  it("sends the code with the challenge and returns the one-time recovery codes", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({ step: "done", csrf_token: "t", recovery_codes: ["AAAA-BBBB"] }),
    );
    vi.stubGlobal("fetch", fetcher);
    const { submitSecondFactor } = await import("@/services/auth");

    await expect(submitSecondFactor("c-1", "123456", true)).resolves.toEqual({
      step: "done",
      recoveryCodes: ["AAAA-BBBB"],
    });
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/auth/login/second-factor",
      expect.objectContaining({ method: "POST" }),
    );
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
      challenge: "c-1",
      code: "123456",
      trust_device: true,
    });
  });

  it("never shows a server error's technical detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "Traceback: asyncpg failed" }, 500)),
    );
    const { login, AuthenticationError } = await import("@/services/auth");

    const failure = await login("ana@firm.be", "pw").catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(AuthenticationError);
    expect((failure as Error).message).toBe("Something went wrong. Please try again.");
  });
});
