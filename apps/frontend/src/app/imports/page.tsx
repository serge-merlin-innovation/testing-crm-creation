import { SignedInShell } from "@/components/signed-in-shell";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { ImportsView } from "./imports-view";

export default async function ImportsPage() {
  const language = await getLanguage();

  return (
    <SignedInShell>
      <main className="flex flex-col gap-4 p-6">
        <ImportsView messages={MESSAGES[language]} />
      </main>
    </SignedInShell>
  );
}
