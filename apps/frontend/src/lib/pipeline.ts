import { DEAL_STAGES } from "./deals";
import { readString } from "./json-field";

export type DealListItem = {
  id: number;
  code_name: string;
  type: string;
  stage: string;
  lead_partner_id: number;
  lead_partner_name: string;
  sector_id: number;
  estimated_ev: string;
  stage_changed_at: string | null;
  closed_at: string | null;
};

export type DealFilters = { partner_id: string; type: string; sector_id: string; stage: string };
export const ANY = "any";
export const NO_FILTERS: DealFilters = { partner_id: ANY, type: ANY, sector_id: ANY, stage: ANY };

export type SortKey = "code_name" | "stage" | "lead_partner_name" | "estimated_ev" | "stage_changed_at";
export type Sort = { key: SortKey; descending: boolean };

/** The query string the backend list takes; "any" leaves a filter out. */
export function dealsQuery(filters: DealFilters, search = ""): string {
  const params = new URLSearchParams();
  if (search) params.set("q", search);
  for (const [key, value] of Object.entries(filters)) {
    if (value && value !== ANY) params.set(key, value);
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function stageIndex(stage: string): number {
  return DEAL_STAGES.indexOf(stage as (typeof DEAL_STAGES)[number]);
}

/** Board columns: every open stage in order. Closed deals are listed, never dragged. */
export const BOARD_STAGES = DEAL_STAGES.filter((stage) => stage !== "closed_won" && stage !== "aborted");

export function groupByStage(deals: DealListItem[]): Record<string, DealListItem[]> {
  const columns: Record<string, DealListItem[]> = Object.fromEntries(DEAL_STAGES.map((stage) => [stage, []]));
  for (const deal of deals) {
    (columns[deal.stage] ??= []).push(deal);
  }
  return columns;
}

export function isBackward(from: string, to: string): boolean {
  return stageIndex(to) < stageIndex(from);
}

export function sortDeals(deals: DealListItem[], sort: Sort): DealListItem[] {
  const value = (deal: DealListItem): string | number => {
    switch (sort.key) {
      case "stage":
        return stageIndex(deal.stage);
      case "estimated_ev":
        return Number(deal.estimated_ev);
      case "stage_changed_at":
        return deal.stage_changed_at ?? "";
      default:
        return deal[sort.key].toLowerCase();
    }
  };
  const sorted = [...deals].sort((a, b) => {
    const left = value(a);
    const right = value(b);
    return left < right ? -1 : left > right ? 1 : a.id - b.id;
  });
  return sort.descending ? sorted.reverse() : sorted;
}

export function toggleSort(current: Sort, key: SortKey): Sort {
  return current.key === key ? { key, descending: !current.descending } : { key, descending: false };
}

export function stageLabel(stage: string): string {
  const words = stage.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** The partners present in the visible deals, for the partner filter. */
export function partnerOptions(deals: DealListItem[]): { value: string; label: string }[] {
  const seen = new Map<number, string>();
  for (const deal of deals) seen.set(deal.lead_partner_id, deal.lead_partner_name);
  return [...seen.entries()]
    .sort((a, b) => a[1].localeCompare(b[1]))
    .map(([id, name]) => ({ value: String(id), label: name }));
}

/** A blocked move's 422 carries `detail.reasons`; anything else falls back to one message. */
export function blockedReasons(body: unknown): string[] | null {
  const detail = typeof body === "object" && body !== null ? (body as { detail?: unknown }).detail : null;
  const reasons = typeof detail === "object" && detail !== null ? (detail as { reasons?: unknown }).reasons : null;
  return Array.isArray(reasons) && reasons.every((reason) => typeof reason === "string") ? reasons : null;
}

export function firstError(body: unknown): string | null {
  const errors = typeof body === "object" && body !== null ? (body as { errors?: unknown }).errors : null;
  if (Array.isArray(errors) && errors.length) return readString(errors[0], "message");
  return readString(body, "detail");
}

export type Milestone = {
  id: number;
  name: string;
  planned_date: string;
  actual_date: string | null;
  late: boolean;
  days_late: number;
};

/** The fields an admin may require before a deal leaves a stage; mirrors the backend list. */
export const CRITERION_FIELDS = [
  { value: "target_id", label: "Target" },
  { value: "estimated_ev", label: "Estimated EV" },
  { value: "sector_id", label: "Sector" },
  { value: "client_id", label: "Client" },
] as const;
