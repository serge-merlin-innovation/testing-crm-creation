import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { AcceptInvitationForm } from "./accept-invitation-form";

type Props = { searchParams: Promise<{ token?: string | string[] }> };

export default async function AcceptInvitationPage({ searchParams }: Props) {
  const { token } = await searchParams;
  const language = await getLanguage();

  return <AcceptInvitationForm token={(Array.isArray(token) ? token[0] : token) ?? ""} messages={MESSAGES[language]} />;
}
