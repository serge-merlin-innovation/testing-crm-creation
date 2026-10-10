import { LoginForm } from "./login-form";
import { sanitizeReturnTo } from "@/lib/auth-routing";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";

type LoginPageProps = {
  searchParams: Promise<{ next?: string | string[] }>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const { next } = await searchParams;
  const language = await getLanguage();

  return (
    <LoginForm
      returnTo={sanitizeReturnTo(Array.isArray(next) ? next[0] : next)}
      messages={MESSAGES[language]}
    />
  );
}
