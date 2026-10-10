/** Fee terms, fee visibility and invoices (DEAL-05, AUTHZ-06, REP-07). Pure: no fetch, no React. */

export const FEES_READ = "fees.read";
export const INVOICES_MANAGE = "invoices.manage";
export const DEALS_READ_SUMMARY = "deals.read_summary";

export type SuccessFeeKind = "percent" | "fixed" | "lehman";
export type LehmanTier = { up_to: string | null; percent: string };

export type FeeTerms = {
  mandate_id: number;
  code_name: string;
  retainer_monthly: string;
  success_fee_kind: SuccessFeeKind;
  success_fee_percent: string | null;
  success_fee_fixed: string | null;
  minimum_fee: string;
  lehman_tiers: LehmanTier[];
  retainers_creditable: boolean;
  retainers_paid: string;
  expected_fee: string;
  final_fee: string | null;
  engaged: boolean;
  can_edit: boolean;
};

export type Invoice = {
  id: number;
  mandate_id: number;
  type: "retainer" | "success_fee";
  amount: string;
  sent_date: string;
  paid_date: string | null;
};

export type FeeForm = {
  retainer_monthly: string;
  success_fee_kind: SuccessFeeKind;
  success_fee_percent: string;
  success_fee_fixed: string;
  minimum_fee: string;
  lehman_tiers: string;
  retainers_creditable: boolean;
  change_reason: string;
  amended_letter_url: string;
};

/** The UI hides every fee field without fees.read; the API refuses them anyway (AUTHZ-06). */
export function canSeeFees(permissions: string[]): boolean {
  return permissions.includes(FEES_READ);
}

export function canRecordInvoices(permissions: string[]): boolean {
  return permissions.includes(FEES_READ) && permissions.includes(INVOICES_MANAGE);
}

/** "10000:3, 20000:2, :1" <-> tiers. An empty bound is the open last band. */
export function formatTiers(tiers: LehmanTier[]): string {
  return tiers.map((tier) => `${tier.up_to ?? ""}:${tier.percent}`).join(", ");
}

export function parseTiers(text: string): LehmanTier[] {
  return text
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const [upTo, percent] = part.split(":").map((value) => value.trim());
      return { up_to: upTo ? upTo : null, percent: percent ?? "" };
    });
}

export function formFromTerms(terms: FeeTerms | null): FeeForm {
  return {
    retainer_monthly: terms?.retainer_monthly ?? "0",
    success_fee_kind: terms?.success_fee_kind ?? "percent",
    success_fee_percent: terms?.success_fee_percent ?? "",
    success_fee_fixed: terms?.success_fee_fixed ?? "",
    minimum_fee: terms?.minimum_fee ?? "0",
    lehman_tiers: terms ? formatTiers(terms.lehman_tiers) : "",
    retainers_creditable: terms?.retainers_creditable ?? false,
    change_reason: "",
    amended_letter_url: "",
  };
}

export function feePayload(form: FeeForm): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    retainer_monthly: form.retainer_monthly || "0",
    success_fee_kind: form.success_fee_kind,
    minimum_fee: form.minimum_fee || "0",
    retainers_creditable: form.retainers_creditable,
  };
  if (form.success_fee_kind === "percent") payload.success_fee_percent = form.success_fee_percent;
  if (form.success_fee_kind === "fixed") payload.success_fee_fixed = form.success_fee_fixed;
  if (form.success_fee_kind === "lehman") payload.lehman_tiers = parseTiers(form.lehman_tiers);
  if (form.change_reason.trim()) payload.change_reason = form.change_reason.trim();
  if (form.amended_letter_url.trim()) payload.amended_letter_url = form.amended_letter_url.trim();
  return payload;
}

/** After engagement, changing the saved terms needs a reason and the amended letter (DEAL-05 c3). */
export function needsAmendment(terms: FeeTerms | null, form: FeeForm): boolean {
  if (!terms || !terms.engaged) return false;
  const saved = formFromTerms(terms);
  const keys: (keyof FeeForm)[] = [
    "retainer_monthly",
    "success_fee_kind",
    "success_fee_percent",
    "success_fee_fixed",
    "minimum_fee",
    "lehman_tiers",
    "retainers_creditable",
  ];
  return keys.some((key) => {
    const a = saved[key];
    const b = form[key];
    if (typeof a === "string" && typeof b === "string" && a !== "" && b !== "" && !Number.isNaN(Number(a))) {
      return Number(a) !== Number(b);
    }
    return a !== b;
  });
}

export function feesQuery(minExpectedFee: string): string {
  const value = minExpectedFee.trim();
  return value ? `?min_expected_fee=${encodeURIComponent(value)}` : "";
}
