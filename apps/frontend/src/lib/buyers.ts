import type { MessageKey } from "./i18n/messages";

export const BUYER_STATUSES = [
  "long_list",
  "contacted",
  "teaser_sent",
  "nda_sent",
  "nda_signed",
  "im_sent",
  "indicative_offer",
  "management_meeting",
  "binding_offer",
  "declined",
] as const;
export type BuyerStatus = (typeof BUYER_STATUSES)[number];
export type Approval = "pending" | "approved" | "excluded";
export const DECLINE_REASONS = ["price", "fit", "timing", "no_response"] as const;
export type DeclineReason = (typeof DECLINE_REASONS)[number];

export type Nda = {
  sent_date: string | null;
  markup_received_date: string | null;
  agreed_date: string | null;
  signed_date: string | null;
  document_url: string | null;
  standstill_end: string | null;
  non_solicit_end: string | null;
};

export type Buyer = {
  id: number;
  company_id: number;
  name: string;
  type: string;
  owner_id: number;
  owner_name: string;
  rationale: string;
  contact_id: number | null;
  contact_name: string | null;
  approval: Approval;
  status: BuyerStatus;
  status_changed_at: string;
  status_changed_by_name: string;
  decline_reason: DeclineReason | null;
  notes: string | null;
  nda: Nda | null;
};

export type BuyerGrid = { buyers: Buyer[]; funnel: Record<BuyerStatus, number>; can_approve: boolean };
export type Suggestion = { company_id: number; name: string; type: string; score: number; matched: string[] };
export type AddWarning = { company_id: number; name: string; reason: "conflict" | "client_exclusion" };
export type AddResult = { added: number[]; skipped: number[]; warnings: AddWarning[] };

export const STATUS_LABEL: Record<BuyerStatus, MessageKey> = {
  long_list: "buyers.status.long_list",
  contacted: "buyers.status.contacted",
  teaser_sent: "buyers.status.teaser_sent",
  nda_sent: "buyers.status.nda_sent",
  nda_signed: "buyers.status.nda_signed",
  im_sent: "buyers.status.im_sent",
  indicative_offer: "buyers.status.indicative_offer",
  management_meeting: "buyers.status.management_meeting",
  binding_offer: "buyers.status.binding_offer",
  declined: "buyers.status.declined",
};

export const DECLINE_LABEL: Record<DeclineReason, MessageKey> = {
  price: "buyers.decline.price",
  fit: "buyers.decline.fit",
  timing: "buyers.decline.timing",
  no_response: "buyers.decline.no_response",
};

export const APPROVAL_LABEL: Record<Approval, MessageKey> = {
  pending: "buyers.approval.pending",
  approved: "buyers.approval.approved",
  excluded: "buyers.approval.excluded",
};

const AFTER_NDA: BuyerStatus[] = ["im_sent", "indicative_offer", "management_meeting", "binding_offer"];

/** Statuses a user may pick in the grid. NDA signed comes from the NDA's signed date, never by hand. */
export const SETTABLE_STATUSES: BuyerStatus[] = BUYER_STATUSES.filter((status) => status !== "nda_signed");

/** Mirrors the backend (BUY-02 c2, BUY-03 c2): why `buyer` cannot move to `status`, or null. */
export function blockedReason(buyer: Pick<Buyer, "approval" | "nda">, status: BuyerStatus): MessageKey | null {
  if (status === "long_list" || status === "declined") return null;
  if (status === "nda_signed") return "buyers.blocked.ndaSigned";
  if (buyer.approval !== "approved") return "buyers.blocked.notApproved";
  if (AFTER_NDA.includes(status) && !buyer.nda?.signed_date) return "buyers.blocked.needsNda";
  return null;
}

export function toggle(selected: number[], id: number): number[] {
  return selected.includes(id) ? selected.filter((value) => value !== id) : [...selected, id];
}
