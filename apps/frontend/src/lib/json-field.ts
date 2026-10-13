function fieldOf(payload: unknown, key: string): unknown {
  if (typeof payload !== "object" || payload === null) {
    return undefined;
  }

  return (payload as Record<string, unknown>)[key];
}

export function readString(payload: unknown, key: string): string | null {
  const value = fieldOf(payload, key);

  return typeof value === "string" ? value : null;
}

export function readStringArray(payload: unknown, key: string): string[] | null {
  const value = fieldOf(payload, key);

  return Array.isArray(value) && value.every((item) => typeof item === "string") ? value : null;
}
