import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { ResetPasswordForm } from "./reset-password-form";

type Props = { searchParams: Promise<{ token?: string | string[] }> };

export default async function ResetPasswordPage({ searchParams }: Props) {
  const { token } = await searchParams;
  const language = await getLanguage();

  return <ResetPasswordForm token={(Array.isArray(token) ? token[0] : token) ?? ""} messages={MESSAGES[language]} />;
}
