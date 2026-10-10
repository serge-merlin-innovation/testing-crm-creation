import { SignedInShell } from "@/components/signed-in-shell";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { InboxView } from "./inbox-view";

export default async function InboxPage() {
  const language = await getLanguage();

  return (
    <SignedInShell>
      <main className="flex flex-col gap-4 p-6">
        <InboxView messages={MESSAGES[language]} language={language} />
      </main>
    </SignedInShell>
  );
}
