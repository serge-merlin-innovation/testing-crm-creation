import { SignedInShell } from "@/components/signed-in-shell";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { AuditView } from "./audit-view";

export default async function AuditPage() {
  const language = await getLanguage();

  return (
    <SignedInShell>
      <main className="flex flex-col gap-4 p-4 md:p-6">
        <AuditView messages={MESSAGES[language]} />
      </main>
    </SignedInShell>
  );
}
