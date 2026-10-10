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

export function readBoolean(payload: unknown, key: string): boolean | null {
  const value = fieldOf(payload, key);

  return typeof value === "boolean" ? value : null;
}
