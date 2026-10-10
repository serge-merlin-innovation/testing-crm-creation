import { SignedInShell } from "@/components/signed-in-shell";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { LastLoginCard } from "./last-login";
import { LogoutEverywhereCard } from "./logout-everywhere";

export default async function Profile() {
  const language = await getLanguage();

  return (
    <SignedInShell>
      <main className="flex flex-col gap-4 p-4 md:p-6">
        <LastLoginCard messages={MESSAGES[language]} language={language} />
        <LogoutEverywhereCard messages={MESSAGES[language]} />
      </main>
    </SignedInShell>
  );
}
