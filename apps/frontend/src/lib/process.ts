import type { MessageKey } from "./i18n/messages";

export type OfferRound = "indicative" | "binding";
export type FinancingCertainty =
  "committed" | "highly_confident" | "subject_to_financing" | "equity_only";
export const FINANCING: FinancingCertainty[] = [
  "committed",
  "highly_confident",
  "subject_to_financing",
  "equity_only",
];
export const FINANCING_LABEL: Record<FinancingCertainty, MessageKey> = {
  committed: "offers.financing.committed",
  highly_confident: "offers.financing.highly_confident",
  subject_to_financing: "offers.financing.subject_to_financing",
  equity_only: "offers.financing.equity_only",
};

export type Offer = {
  id: number;
  buyer_id: number;
  buyer_name: string;
  round: OfferRound;
  version: number;
  ev: string;
  equity_value: string;
  cash_pct: string;
  earn_out_pct: string;
  vendor_loan_pct: string;
  rollover_pct: string;
  conditions: string;
  financing_certainty: FinancingCertainty;
  received_at: string;
  late: boolean;
  entered_by_name: string;
  entered_at: string;
  ev_ebitda: string | null;
};

export type Comparison = {
  ebitda: string | null;
  ebitda_year: number | null;
  bids: Offer[];
  history: Offer[];
  deadlines: { indicative_at: string | null; binding_at: string | null };
};

export type FunnelStep = {
  key: FunnelKey;
  count: number;
  conversion_pct: string | null;
};
export type FunnelKey = "approached" | "nda" | "im" | "offers" | "binding";
export const FUNNEL_LABEL: Record<FunnelKey, MessageKey> = {
  approached: "funnel.approached",
  nda: "funnel.nda",
  im: "funnel.im",
  offers: "funnel.offers",
  binding: "funnel.binding",
};

export type LetterResult = {
  sent: {
    buyer_id: number;
    buyer_name: string;
    contact_name: string;
    language: string;
    subject: string;
  }[];
  excluded: {
    buyer_id: number;
    buyer_name: string;
    reason: string;
    message: string;
  }[];
};

export type TemplateKind = "letter" | "report";
export type Template = {
  id: number;
  kind: TemplateKind;
  name: string;
  language: "en" | "fr" | "nl";
  subject: string;
  body: string;
  references_im: boolean;
  updated_at: string;
  updated_by_name: string | null;
};
export type TemplateName = {
  kind: TemplateKind;
  name: string;
  languages: string[];
};

export const MERGE_FIELDS = [
  "salutation",
  "first_name",
  "last_name",
  "contact_name",
  "buyer_name",
  "code_name",
  "stage",
  "date",
  "funnel",
  "timeline",
  "next_steps",
] as const;

/** Merge fields in `text` the server would refuse. */
export function unknownFields(text: string): string[] {
  const known = new Set<string>(MERGE_FIELDS);
  const found = new Set<string>();
  for (const match of text.matchAll(/\{\{\s*([a-z_]+)\s*\}\}/g)) {
    if (!known.has(match[1])) found.add(match[1]);
  }
  return [...found].sort();
}

/** Cash, earn-out, vendor loan and rollover must make 100%. */
export function structureTotal(parts: string[]): number {
  return parts.reduce((sum, part) => sum + (Number.parseFloat(part) || 0), 0);
}

export function structureAddsUp(parts: string[]): boolean {
  return Math.abs(structureTotal(parts) - 100) < 0.005;
}

/** Earlier versions of the same buyer's offer in the same round, newest first. */
export function earlierVersions(history: Offer[], bid: Offer): Offer[] {
  return history.filter(
    (item) =>
      item.buyer_id === bid.buyer_id &&
      item.round === bid.round &&
      item.version < bid.version,
  );
}

/** `datetime-local` value to an ISO string, or null when empty. */
export function localToIso(value: string): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}
