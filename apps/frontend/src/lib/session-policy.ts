export type SessionPolicy = {
  desktopIdleMinutes: number;
  mobileIdleMinutes: number;
  absoluteHours: number;
  mobileReadOnly: boolean;
};

export function parseSessionPolicy(payload: unknown): SessionPolicy | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const record = payload as Record<string, unknown>;
  const { desktop_idle_minutes, mobile_idle_minutes, absolute_hours, mobile_read_only } = record;
  if (
    typeof desktop_idle_minutes !== "number" ||
    typeof mobile_idle_minutes !== "number" ||
    typeof absolute_hours !== "number" ||
    typeof mobile_read_only !== "boolean"
  ) {
    return null;
  }
  return {
    desktopIdleMinutes: desktop_idle_minutes,
    mobileIdleMinutes: mobile_idle_minutes,
    absoluteHours: absolute_hours,
    mobileReadOnly: mobile_read_only,
  };
}

export function sessionPolicyBody(policy: SessionPolicy) {
  return {
    desktop_idle_minutes: policy.desktopIdleMinutes,
    mobile_idle_minutes: policy.mobileIdleMinutes,
    absolute_hours: policy.absoluteHours,
    mobile_read_only: policy.mobileReadOnly,
  };
}
