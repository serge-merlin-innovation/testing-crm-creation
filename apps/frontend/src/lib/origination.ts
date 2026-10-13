export const OPPORTUNITY_STAGES = [
  "lead",
  "contacted",
  "meeting_held",
  "pitch",
  "engagement_letter_sent",
  "won",
  "lost",
  "on_hold",
] as const;
export type OpportunityStage = (typeof OPPORTUNITY_STAGES)[number];

export const TRIGGERS = ["succession", "growth", "carve_out", "distress"] as const;
export const LOST_REASONS = ["fee", "competitor", "timing", "client_decided_not_to_sell"] as const;
export type LostReason = (typeof LOST_REASONS)[number];

/** Won goes through its own confirmation (it creates the mandate); these move with the stage control. */
export const MOVABLE_STAGES: OpportunityStage[] = OPPORTUNITY_STAGES.filter((stage) => stage !== "won");
const CLOSED: OpportunityStage[] = ["won", "lost"];

export type Credential = {
  id: number;
  code_name: string;
  type: string;
  sector_id: number;
  ev: string | null;
  closing_date: string | null;
};

export type Opportunity = {
  id: number;
  company_id: number;
  company_name: string;
  owner_id: number;
  owner_name: string;
  type: string;
  trigger: string;
  estimated_ev: string;
  probability: number;
  sector_id: number | null;
  stage: OpportunityStage;
  lost_reason: LostReason | null;
  competitor_advisor: string | null;
  revisit_date: string | null;
  mandate_id: number | null;
  conflict_warning: boolean;
  is_owner: boolean;
  members?: { user_id: number; name: string; role_name: string | null }[];
  links?: { id: number; label: string; url: string }[];
  credentials?: Credential[];
  fee_draft?: Record<string, unknown> | null;
};

export function isClosed(opportunity: Pick<Opportunity, "stage">): boolean {
  return CLOSED.includes(opportunity.stage);
}

export function stageLabelKey(stage: OpportunityStage) {
  return `origination.stage.${stage}` as const;
}

export function lostReasonLabelKey(reason: LostReason) {
  return `origination.lost.${reason}` as const;
}

/** The pipeline board: one column per stage, in stage order. */
export function groupByStage(opportunities: Opportunity[]): Record<OpportunityStage, Opportunity[]> {
  const columns = Object.fromEntries(OPPORTUNITY_STAGES.map((stage) => [stage, [] as Opportunity[]])) as Record<
    OpportunityStage,
    Opportunity[]
  >;
  for (const opportunity of opportunities) {
    columns[opportunity.stage]?.push(opportunity);
  }
  return columns;
}

/** The body of a stage move: only the fields the stage asks for. */
export function stagePayload(
  stage: OpportunityStage,
  extra: { lostReason?: string; competitor?: string; revisitDate?: string },
): Record<string, string> {
  const body: Record<string, string> = { stage };
  if (stage === "lost") {
    if (extra.lostReason) body.lost_reason = extra.lostReason;
    if (extra.competitor?.trim()) body.competitor_advisor = extra.competitor.trim();
  }
  if (stage === "on_hold" && extra.revisitDate) {
    body.revisit_date = extra.revisitDate;
  }
  return body;
}

/** Credential search query: sector and EV band in EUR thousands; blanks are left out. */
export function credentialQuery(filters: { sectorId?: string; evMin?: string; evMax?: string }): string {
  const params = new URLSearchParams();
  if (filters.sectorId) params.set("sector_id", filters.sectorId);
  if (filters.evMin?.trim()) params.set("ev_min", filters.evMin.trim());
  if (filters.evMax?.trim()) params.set("ev_max", filters.evMax.trim());
  const text = params.toString();
  return text ? `?${text}` : "";
}

/** Weighted pipeline value: EV times probability, in EUR thousands. */
export function weightedEv(opportunities: Opportunity[]): number {
  return opportunities
    .filter((opportunity) => !isClosed(opportunity))
    .reduce((total, opportunity) => total + (Number(opportunity.estimated_ev) * opportunity.probability) / 100, 0);
}
