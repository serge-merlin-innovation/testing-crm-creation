import { readString } from "./json-field";

/** The sell-side list. Every mandate type uses it in v1 (DEAL-01, derived); mirrors the backend. */
export const DEAL_STAGES = [
  "conflict_review",
  "preparation",
  "marketing",
  "information_memorandum",
  "indicative_offers",
  "due_diligence",
  "binding_offers",
  "spa_negotiation",
  "signing",
  "closing",
  "closed_won",
  "aborted",
] as const;

export const MANDATE_TYPES = ["sell_side", "buy_side", "fundraising", "debt_advisory"] as const;
export const TEAM_ROLES = ["lead_partner", "partner", "director", "analyst", "other"] as const;

export type Mandate = {
  id: number;
  code_name: string;
  type: string;
  stage: string;
  client_id: number;
  client_name: string;
  target_id: number | null;
  target_name: string | null;
  sector_id: number;
  estimated_ev: string;
  lead_partner_id: number;
  lead_partner_name: string;
  stages: string[];
  version: number;
  stage_changed_at: string | null;
  closed_at: string | null;
  outcome: {
    final_ev: string | null;
    buyer: string | null;
    ev_ebitda: string | null;
    closing_date: string | null;
    tombstone_allowed: boolean | null;
    abort_reason: string | null;
  };
  can_edit: boolean;
  can_manage_team: boolean;
  can_close: boolean;
  can_reopen: boolean;
};

export type HistoryEntry = {
  action: string;
  at: string;
  user_id: number | null;
  user_name: string | null;
  field: string | null;
  old_value: string | null;
  new_value: string | null;
};

export type HistoryRow = { who: string; when: string; what: string; old: string; new: string };

export function isHttpsUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.host !== "";
  } catch {
    return false;
  }
}

/** Anchor props for a stored document link: a new tab, and never a non-https href. */
export function documentLinkProps(url: string) {
  return isHttpsUrl(url) ? { href: url, target: "_blank", rel: "noopener noreferrer" } : null;
}

export function readStaleConflict(
  status: number,
  body: unknown,
): { message: string; current: Record<string, unknown> } | null {
  if (status !== 409 || typeof body !== "object" || body === null) {
    return null;
  }
  const detail = (body as { detail?: unknown }).detail;
  const message = readString(detail, "message");
  const current = typeof detail === "object" && detail !== null ? (detail as { current?: unknown }).current : null;
  if (message === null || typeof current !== "object" || current === null) {
    return null;
  }
  return { message, current: current as Record<string, unknown> };
}

export function historyRows(entries: HistoryEntry[]): HistoryRow[] {
  return entries.map((entry) => ({
    who: entry.user_name ?? "",
    when: entry.at,
    what: entry.field ?? entry.action,
    old: entry.old_value ?? "",
    new: entry.new_value ?? "",
  }));
}

/** The backend's 422 `errors: [{field, message}]`, keyed by field for inline display. */
export function fieldErrors(body: unknown): Record<string, string> {
  const errors = typeof body === "object" && body !== null ? (body as { errors?: unknown }).errors : null;
  if (!Array.isArray(errors)) {
    return {};
  }
  const result: Record<string, string> = {};
  for (const error of errors) {
    const field = readString(error, "field");
    const message = readString(error, "message");
    if (field && message && !(field in result)) {
      result[field] = message;
    }
  }
  return result;
}

export function readDetail(body: unknown, fallback: string): string {
  return readString(body, "detail") ?? fallback;
}
