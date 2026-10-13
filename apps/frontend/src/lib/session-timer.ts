import { readString } from "./json-field";

export type SessionStatus = {
  idleExpiresAt: Date;
  absoluteExpiresAt: Date | null;
  warningSeconds: number;
  mobile: boolean;
  mobileReadOnly: boolean;
};

export type SessionPhase = "active" | "warning" | "expired";

const RENEW_THROTTLE_MS = 60_000;

export function parseSessionStatus(payload: unknown): SessionStatus | null {
  const idle = readString(payload, "idle_expires_at");
  if (!idle || typeof payload !== "object" || payload === null) {
    return null;
  }
  const record = payload as Record<string, unknown>;
  const absolute = readString(payload, "absolute_expires_at");
  return {
    idleExpiresAt: new Date(idle),
    absoluteExpiresAt: absolute ? new Date(absolute) : null,
    warningSeconds: typeof record.warning_seconds === "number" ? record.warning_seconds : 120,
    mobile: record.mobile === true,
    mobileReadOnly: record.mobile_read_only === true,
  };
}

export function expiresAt(status: SessionStatus): Date {
  const absolute = status.absoluteExpiresAt;
  return absolute && absolute < status.idleExpiresAt ? absolute : status.idleExpiresAt;
}

export function sessionPhase(status: SessionStatus, now: Date): SessionPhase {
  const remaining = expiresAt(status).getTime() - now.getTime();
  if (remaining <= 0) {
    return "expired";
  }
  return remaining <= status.warningSeconds * 1000 ? "warning" : "active";
}

/** Tabs share one server session: whichever has seen the latest activity holds the truth. */
export function laterStatus(current: SessionStatus, incoming: SessionStatus): SessionStatus {
  return expiresAt(incoming) > expiresAt(current) ? incoming : current;
}

export function shouldRenewOnActivity(lastRenewal: Date | null, now: Date): boolean {
  return lastRenewal === null || now.getTime() - lastRenewal.getTime() >= RENEW_THROTTLE_MS;
}
