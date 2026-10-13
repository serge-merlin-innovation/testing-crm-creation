export const MIN_QUERY_LENGTH = 3;

export type Criteria = {
  q?: string | null;
  company_types?: string[];
  country_ids?: number[];
  sector_ids?: number[];
  ev_min?: string | null;
  ev_max?: string | null;
};

/** The query string the search endpoint takes; empty criteria are left out. */
export function searchQuery(criteria: Criteria, filterId?: number | null): string {
  const params = new URLSearchParams();
  if (criteria.q?.trim()) params.set("q", criteria.q.trim());
  if (filterId) params.set("filter_id", String(filterId));
  for (const value of criteria.company_types ?? []) params.append("company_type", value);
  for (const value of criteria.country_ids ?? []) params.append("country_id", String(value));
  for (const value of criteria.sector_ids ?? []) params.append("sector_id", String(value));
  if (criteria.ev_min) params.set("ev_min", criteria.ev_min);
  if (criteria.ev_max) params.set("ev_max", criteria.ev_max);
  return params.toString();
}

export function canSearch(criteria: Criteria, filterId?: number | null): boolean {
  return (
    (criteria.q?.trim().length ?? 0) >= MIN_QUERY_LENGTH ||
    Boolean(filterId) ||
    Boolean(criteria.company_types?.length || criteria.country_ids?.length || criteria.sector_ids?.length) ||
    Boolean(criteria.ev_min || criteria.ev_max)
  );
}

/** "Jan Peeters" -> first and last name for create-from-search; a single word is the last name. */
export function splitName(text: string): { first_name: string; last_name: string } {
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (words.length <= 1) return { first_name: "", last_name: words[0] ?? "" };
  return { first_name: words[0], last_name: words.slice(1).join(" ") };
}
