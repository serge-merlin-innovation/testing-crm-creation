import { SignedInShell } from "@/components/signed-in-shell";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { TrustedDevicePolicy } from "./trusted-device-policy";
import { UsersView } from "./users-view";

export default async function Users() {
  const language = await getLanguage();

  return (
    <SignedInShell>
      <main className="flex flex-col gap-4 p-4 md:p-6">
        <UsersView messages={MESSAGES[language]} />
        <TrustedDevicePolicy messages={MESSAGES[language]} />
      </main>
    </SignedInShell>
  );
}
