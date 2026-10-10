import { SignedInShell } from "@/components/signed-in-shell";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { LanguageCard } from "./language-card";
import { LastLoginCard } from "./last-login";
import { LogoutEverywhereCard } from "./logout-everywhere";
import { CalendarFeedCard, EmailLoggingCard } from "./mail-and-calendar";
import { NotificationPreferencesCard } from "./notification-preferences";

export default async function Profile() {
  const language = await getLanguage();

  return (
    <SignedInShell>
      <main className="flex flex-col gap-4 p-4 md:p-6">
        <LanguageCard messages={MESSAGES[language]} language={language} />
        <LastLoginCard messages={MESSAGES[language]} language={language} />
        <LogoutEverywhereCard messages={MESSAGES[language]} />
        <EmailLoggingCard messages={MESSAGES[language]} />
        <CalendarFeedCard messages={MESSAGES[language]} />
        <NotificationPreferencesCard messages={MESSAGES[language]} />
      </main>
    </SignedInShell>
  );
}
