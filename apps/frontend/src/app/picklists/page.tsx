import { SignedInShell } from "@/components/signed-in-shell";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { PicklistsView } from "./picklists-view";

export default async function PicklistsPage() {
  const language = await getLanguage();

  return (
    <SignedInShell>
      <main className="flex flex-col gap-4 p-6">
        <PicklistsView messages={MESSAGES[language]} language={language} />
      </main>
    </SignedInShell>
  );
}
