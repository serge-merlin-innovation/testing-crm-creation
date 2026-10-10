import { SignedInShell } from "@/components/signed-in-shell";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { SessionPolicyForm } from "./session-policy-form";

export default async function Settings() {
  const language = await getLanguage();

  return (
    <SignedInShell>
      <main className="flex flex-col gap-4 p-4 md:p-6">
        <SessionPolicyForm messages={MESSAGES[language]} />
      </main>
    </SignedInShell>
  );
}
