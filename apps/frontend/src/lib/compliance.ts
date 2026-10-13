import type { MessageKey } from "./i18n/messages";

export type ConflictStatus = "clear" | "review" | "cleared" | "rejected";
export type KycStatus = "none" | "pending" | "approved" | "frozen";

export type Kyc = {
  status: KycStatus;
  ubo_check: boolean;
  id_check: boolean;
  pep_sanctions_screening: boolean;
  sanctions_hit: boolean;
  reviewed_at: string | null;
  approved_at: string | null;
  reviewer_name: string | null;
  frozen: boolean;
  can_review: boolean;
};

export type ConflictHit = {
  company_name: string;
  role: string;
  matched_company_name: string;
  other_mandate_id: number;
  other_code_name: string;
  other_role: string;
  other_stage: string;
};

export type ConflictReviewItem = { mandate_id: number; code_name: string; opened_at: string; hits: number };

export const CONFLICT_STATUS_LABEL: Record<ConflictStatus, MessageKey> = {
  clear: "compliance.status.clear",
  review: "compliance.status.review",
  cleared: "compliance.status.cleared",
  rejected: "compliance.status.rejected",
};

export const KYC_STATUS_LABEL: Record<KycStatus, MessageKey> = {
  none: "compliance.kyc.none",
  pending: "compliance.kyc.pending",
  approved: "compliance.kyc.approved",
  frozen: "compliance.kyc.frozen",
};

/** Mirrors the backend rule (ORI-05 c2) so the form shows the status the review will produce. */
export function kycOutcome(review: Pick<Kyc, "ubo_check" | "id_check" | "pep_sanctions_screening" | "sanctions_hit">): KycStatus {
  if (review.sanctions_hit) return "frozen";
  return review.ubo_check && review.id_check && review.pep_sanctions_screening ? "approved" : "pending";
}

export function fillTemplate(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) => values[key] ?? match);
}
