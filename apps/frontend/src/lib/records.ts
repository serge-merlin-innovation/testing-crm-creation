import { LANGUAGES, type Language } from "@/lib/i18n/messages";

export const RECORD_LANGUAGES: readonly Language[] = LANGUAGES;

export type ContactForm = {
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  source: string;
  function: string;
  salutation: string;
};

export function contactPayload(
  form: ContactForm,
  extra: { companyId: number | null; language: Language; marketingOptOut: boolean; doNotContact: boolean },
): Record<string, unknown> {
  return {
    first_name: form.first_name,
    last_name: form.last_name,
    email: form.email || null,
    phone: form.phone || null,
    source: form.source,
    function: form.function || null,
    company_id: extra.companyId,
    language: extra.language,
    marketing_opt_out: extra.marketingOptOut,
    do_not_contact: extra.doNotContact,
    salutation: form.salutation.trim() || null,
  };
}

export function companyPayload(
  form: {
    name: string;
    type: string;
    countryId: string;
    number: string;
    belgian: boolean;
    language: Language;
    address?: string;
    legalForm?: string | null;
    naceCode?: string | null;
  },
  ignoreSimilar: boolean,
): Record<string, unknown> {
  return {
    address: form.address?.trim() || null,
    legal_form: form.legalForm || null,
    nace_code: form.naceCode || null,
    name: form.name || null,
    type: form.type,
    country_id: Number(form.countryId),
    ignore_similar: ignoreSimilar,
    [form.belgian ? "enterprise_number" : "vat_or_registry_number"]: form.number || null,
    language: form.language,
  };
}

export type RegisterPrefill = {
  enterprise_number: string;
  available: boolean;
  name: string | null;
  address: string | null;
  nace_code: string | null;
  legal_form: string | null;
};

export type CompanyRef = { id: number; name: string };

/** CO-01 c2: the backend names the API record; the user opens the company page. */
export function companyHref(id: number): string {
  return `/companies/${id}`;
}

export function contactHref(id: number): string {
  return `/contacts/${id}`;
}

export const METRICS = ["revenue", "ebitda", "net_debt", "fte"] as const;
export type Metric = (typeof METRICS)[number];

export type Figure = {
  value: string;
  source: "nbb" | "manual";
  recorded_at: string;
  source_date: string | null;
  original_currency: string;
  original_value: string | null;
  eur_rate: string | null;
};
export type MetricFigures = { value: string; imported: Figure | null; override: Figure | null };
export type FinancialYear = { year: number; metrics: Partial<Record<Metric, MetricFigures>> };

export type FinancialForm = Record<Metric, string> & { currency: string; eurRate: string };

/** CO-02 c1/c4: blank figures are left out; a foreign currency carries its EUR rate. */
export function financialPayload(form: FinancialForm): Record<string, unknown> {
  const currency = form.currency.trim().toUpperCase() || "EUR";
  const figures = Object.fromEntries(
    METRICS.filter((metric) => form[metric].trim() !== "").map((metric) => [metric, form[metric].trim()]),
  );
  return { ...figures, currency, eur_rate: currency === "EUR" ? null : form.eurRate.trim() || null };
}

export type GroupNode = { id: number; name: string; children: GroupNode[] };

/** Every company in a group tree, so a parent picker can leave out the ones that would loop. */
export function groupIds(node: GroupNode): number[] {
  return [node.id, ...node.children.flatMap(groupIds)];
}

export type Employment = {
  company_id: number;
  company_name: string;
  function: string | null;
  start_date: string | null;
  end_date: string | null;
};

/** CON-01 c2: the current role first, then earlier ones, newest first. */
export function employmentRows(current: Employment | null, history: Employment[]): Employment[] {
  return [...(current ? [current] : []), ...history];
}
