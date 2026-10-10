import { SignedInShell } from "@/components/signed-in-shell";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { MergeView } from "./merge-view";

export default async function MergePage() {
  const language = await getLanguage();

  return (
    <SignedInShell>
      <main className="flex flex-col gap-4 p-6">
        <MergeView messages={MESSAGES[language]} />
      </main>
    </SignedInShell>
  );
}
