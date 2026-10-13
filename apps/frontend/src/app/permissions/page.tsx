import { SignedInShell } from "@/components/signed-in-shell";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { PermissionMatrixEditor } from "./permission-matrix-editor";

export default async function PermissionsPage() {
  const language = await getLanguage();

  return (
    <SignedInShell>
      <main className="flex flex-col gap-4 p-6">
        <PermissionMatrixEditor messages={MESSAGES[language]} />
      </main>
    </SignedInShell>
  );
}
