import { SignedInShell } from "@/components/signed-in-shell";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { StageCriteriaView } from "./stage-criteria-view";

export default async function StageCriteriaPage() {
  const language = await getLanguage();

  return (
    <SignedInShell>
      <main className="flex flex-col gap-4 p-6">
        <StageCriteriaView messages={MESSAGES[language]} />
      </main>
    </SignedInShell>
  );
}
