import { LANGUAGES, type Language } from "@/lib/i18n/messages";

export const RECORD_LANGUAGES: readonly Language[] = LANGUAGES;

export type ContactForm = {
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  source: string;
  function: string;
};

export function contactPayload(
  form: ContactForm,
  extra: { companyId: number | null; language: Language; marketingOptOut: boolean },
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
  };
}

export function companyPayload(
  form: { name: string; type: string; countryId: string; number: string; belgian: boolean; language: Language },
  ignoreSimilar: boolean,
): Record<string, unknown> {
  return {
    name: form.name || null,
    type: form.type,
    country_id: Number(form.countryId),
    ignore_similar: ignoreSimilar,
    [form.belgian ? "enterprise_number" : "vat_or_registry_number"]: form.number || null,
    language: form.language,
  };
}
