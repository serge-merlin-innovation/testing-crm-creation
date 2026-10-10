import { headers } from "next/headers";
import { SignedInShell } from "@/components/signed-in-shell";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { hasRecordAccess } from "@/lib/reports";
import { readForwardedIdentity } from "@/lib/session-identity";
import { HomeView } from "./home-view";

export default async function Overview() {
  const identity = readForwardedIdentity(await headers());
  const language = await getLanguage();

  return (
    <SignedInShell>
      <main className="flex flex-col gap-4 p-6">
        <HomeView records={hasRecordAccess(identity.permissions)} messages={MESSAGES[language]} />
      </main>
    </SignedInShell>
  );
}
