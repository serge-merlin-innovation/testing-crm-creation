import { cookies } from "next/headers";
import { LANGUAGE_COOKIE, resolveLanguage, type Language } from "./messages";

export async function getLanguage(): Promise<Language> {
  return resolveLanguage((await cookies()).get(LANGUAGE_COOKIE)?.value);
}
