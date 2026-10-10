import type { MessageKey } from "./i18n/messages";

export type RequestStatus = "pending" | "approved" | "rejected";

export type MyAccessRequest = {
  id: number;
  code_name: string;
  reason: string;
  status: RequestStatus;
  created_at: string;
  decision_reason: string | null;
  expires_at: string | null;
};

export type AccessRequestItem = {
  id: number;
  code_name: string;
  requester_name: string;
  reason: string;
  status: RequestStatus;
  created_at: string;
};

export type AccessComment = {
  author_name: string;
  on_behalf_of_name: string | null;
  body: string;
  recommendation: "approve" | "reject" | null;
  label: string;
  created_at: string;
};

export type AccessRequestContext = AccessRequestItem & {
  requester_id: number;
  decision_reason: string | null;
  decided_by_name: string | null;
  expires_at: string | null;
  conflicts: { mandate_id: number; code_name: string; company_name: string }[];
  comments: AccessComment[];
  can_decide: boolean;
  can_comment: boolean;
};

export type Delegation = {
  id: number;
  delegate_id: number;
  delegate_name: string;
  starts_on: string;
  ends_on: string;
  active: boolean;
};

export type AccessReview = {
  id: number;
  mandate_id: number;
  code_name: string;
  quarter: string;
  partner_name: string;
  due_at: string;
  completed_at: string | null;
  escalated_at: string | null;
  members: { user_id: number; name: string; role: string }[];
};

export const STATUS_LABEL: Record<RequestStatus, MessageKey> = {
  pending: "access.status.pending",
  approved: "access.status.approved",
  rejected: "access.status.rejected",
};

/** Header the backend reads for a sensitive action (AUTH-02 c5): the current 2FA code, spaces removed. */
export function stepUpHeaders(code: string): Record<string, string> {
  return { "X-Step-Up-Code": code.replace(/\s+/g, "") };
}

/** `YYYY-MM-DD` of `days` after `from`, the default end of a wall crossing. */
export function addDays(from: Date, days: number): string {
  const moved = new Date(from.getTime() + days * 86_400_000);
  return moved.toISOString().slice(0, 10);
}

/** End of the chosen day in UTC, so access lasts through the day the approver picked. */
export function endOfDay(day: string): string {
  return `${day}T23:59:59Z`;
}

export function isOverdue(review: Pick<AccessReview, "completed_at" | "due_at">, now: Date): boolean {
  return review.completed_at === null && new Date(review.due_at).getTime() <= now.getTime();
}
