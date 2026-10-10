import { headers } from "next/headers";
import { SignedInShell } from "@/components/signed-in-shell";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { readForwardedIdentity } from "@/lib/session-identity";
import { OriginationView } from "./origination-view";

export default async function OriginationPage() {
  const language = await getLanguage();
  const identity = readForwardedIdentity(await headers());

  return (
    <SignedInShell>
      <main className="flex flex-col gap-4 p-6">
        <OriginationView messages={MESSAGES[language]} canCreate={identity.permissions.includes("mandates.create")} />
      </main>
    </SignedInShell>
  );
}
