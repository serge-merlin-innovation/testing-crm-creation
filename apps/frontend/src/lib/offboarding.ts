export type OwnedRecord = { type: "contact" | "task" | "deal"; id: number; label: string };

export type OffboardingPreview = {
  user_id: number;
  name: string;
  contacts: OwnedRecord[];
  tasks: OwnedRecord[];
  deals: OwnedRecord[];
  deal_memberships: number;
  needs_new_owner: boolean;
  new_owner_must_be_partner: boolean;
};

export type OffboardingConfirmation = {
  user_id: number;
  sessions_ended: number;
  api_tokens_revoked: number;
  api_clients_revoked: number;
  deal_memberships_removed: number;
  new_owner_id: number | null;
  new_owner_name: string | null;
  reassigned: OwnedRecord[];
};

export type Candidate = { id: number; name: string; role_name: string | null; status: string };

export const PARTNER_ROLE = "Partner";

/** Who may take over: another active user, and a Partner when deals are handed over (ADM-03). */
export function ownerCandidates(preview: OffboardingPreview, users: Candidate[]): Candidate[] {
  return users.filter(
    (user) =>
      user.id !== preview.user_id &&
      user.status === "active" &&
      user.role_name !== null &&
      (!preview.new_owner_must_be_partner || user.role_name === PARTNER_ROLE),
  );
}

/** Confirming stays disabled until a new owner is chosen whenever there is something to hand over. */
export function canConfirm(preview: OffboardingPreview | null, newOwnerId: number | null): boolean {
  return preview !== null && (!preview.needs_new_owner || newOwnerId !== null);
}

export function approvalNotice(template: string, limit: number): string {
  return template.replace("{limit}", String(limit));
}
