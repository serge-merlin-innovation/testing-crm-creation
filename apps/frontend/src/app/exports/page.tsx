import { headers } from "next/headers";
import { SignedInShell } from "@/components/signed-in-shell";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { readForwardedIdentity } from "@/lib/session-identity";
import { ExportsView } from "./exports-view";

export default async function ExportsPage() {
  const language = await getLanguage();
  const identity = readForwardedIdentity(await headers());

  return (
    <SignedInShell>
      <main className="flex flex-col gap-4 p-4 md:p-6">
        <ExportsView messages={MESSAGES[language]} canApprove={identity.permissions.includes("exports.approve")} />
      </main>
    </SignedInShell>
  );
}
