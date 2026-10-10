import { cookies, headers } from "next/headers";
import { LANGUAGE_COOKIE, preferredLanguage, type Language } from "./messages";

export async function getLanguage(): Promise<Language> {
  return preferredLanguage((await cookies()).get(LANGUAGE_COOKIE)?.value, (await headers()).get("accept-language"));
}
