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

/** An API date: a plain `YYYY-MM-DD` is a calendar day (never shifted), a timestamp is read in Brussels time. */
export function formatIsoDate(value: string | null | undefined, language: Language): string {
  if (!value) {
    return "";
  }
  const day = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (day) {
    return `${day[3]}/${day[2]}/${day[1]}`;
  }
  return formatDate(new Date(value), language);
}

export function formatDateTime(value: string | Date | null | undefined, language: Language): string {
  if (!value) {
    return "";
  }
  const date = typeof value === "string" ? new Date(value) : value;
  const time = new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: BELGIAN_TIME_ZONE,
  }).format(date);
  return `${formatDate(date, language)} ${time}`;
}

export function formatNumber(value: number, language: Language, decimals = 2): string {
  return new Intl.NumberFormat(NUMBER_LOCALE[language], {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/** EV and fee figures arrive as decimal strings; shown as whole units with Belgian grouping. */
export function formatAmount(value: string | number | null | undefined, language: Language, decimals = 0): string {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) ? formatNumber(number, language, decimals) : String(value);
}
