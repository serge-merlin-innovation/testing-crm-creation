import type { Language } from "./messages";

const BELGIAN_TIME_ZONE = "Europe/Brussels";

// fr-BE groups thousands with a space in Intl; the firm writes 1.234,56 in both FR and NL.
const NUMBER_LOCALE: Record<Language, string> = { en: "en-GB", fr: "nl-BE", nl: "nl-BE" };

export function formatDate(value: Date, language: Language): string {
  return new Intl.DateTimeFormat(language === "en" ? "en-GB" : `${language}-BE`, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: BELGIAN_TIME_ZONE,
  }).format(value);
}

export function formatNumber(value: number, language: Language, decimals = 2): string {
  return new Intl.NumberFormat(NUMBER_LOCALE[language], {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}
