"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/services/api";

export type Loaded<T> = { data: T | null; failed: boolean; reload: () => Promise<void> };

/** GETs a backend path through the same-origin relay; `failed` covers network and non-2xx. */
export function useApiData<T>(path: string | null): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [failed, setFailed] = useState(false);

  async function reload() {
    if (!path) {
      return;
    }
    const response = await apiFetch(path).catch(() => null);
    const payload: unknown = response?.ok ? await response.json().catch(() => null) : null;
    setFailed(payload === null);
    setData(payload as T | null);
  }

  useEffect(() => {
    let active = true;
    if (path) {
      void apiFetch(path)
        .catch(() => null)
        .then(async (response) => {
          const payload: unknown = response?.ok ? await response.json().catch(() => null) : null;
          if (active) {
            setFailed(payload === null);
            setData(payload as T | null);
          }
        });
    }
    return () => {
      active = false;
    };
  }, [path]);

  return { data, failed, reload };
}

export async function sendJson(
  path: string,
  method: "POST" | "PATCH" | "PUT" | "DELETE",
  body?: unknown,
): Promise<{ status: number; body: unknown }> {
  const response = await apiFetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).catch(() => null);
  if (!response) {
    return { status: 0, body: null };
  }
  const payload: unknown = response.status === 204 ? null : await response.json().catch(() => null);
  return { status: response.status, body: payload };
}
