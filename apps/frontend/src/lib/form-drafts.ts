export type DraftStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

const PREFIX = "crm.draft:";

export function saveDraft(storage: DraftStorage, key: string, values: unknown): void {
  storage.setItem(`${PREFIX}${key}`, JSON.stringify(values));
}

export function loadDraft(storage: DraftStorage, key: string): unknown {
  const raw = storage.getItem(`${PREFIX}${key}`);
  if (raw === null) {
    return null;
  }
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return null;
  }
}

export function clearDraft(storage: DraftStorage, key: string): void {
  storage.removeItem(`${PREFIX}${key}`);
}
