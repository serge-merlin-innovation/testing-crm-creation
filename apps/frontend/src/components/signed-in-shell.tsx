import { headers } from "next/headers";
import { AppNavbar } from "@/components/app-navbar";
import { readForwardedIdentity } from "@/lib/session-identity";

export async function SignedInShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const identity = readForwardedIdentity(await headers());

  return (
    <>
      <AppNavbar {...identity} />
      {children}
    </>
  );
}
