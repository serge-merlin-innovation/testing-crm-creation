import { headers } from "next/headers";
import { AppNavbar } from "@/components/app-navbar";
import { SessionProvider } from "@/components/session-provider";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { readForwardedIdentity } from "@/lib/session-identity";

export async function SignedInShell({ children }: { children: React.ReactNode }) {
  const identity = readForwardedIdentity(await headers());
  const language = await getLanguage();

  return (
    <SessionProvider messages={MESSAGES[language]}>
      <AppNavbar {...identity} messages={MESSAGES[language]} />
      {children}
    </SessionProvider>
  );
}
