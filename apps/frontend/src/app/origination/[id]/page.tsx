import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { SignedInShell } from "@/components/signed-in-shell";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import type { Opportunity } from "@/lib/origination";
import { fetchAsReader } from "@/lib/server-fetch";
import { readForwardedIdentity } from "@/lib/session-identity";
import { OpportunityView } from "./opportunity-view";

type OpportunityPageProps = { params: Promise<{ id: string }> };

// ORI-01 c3: an opportunity the reader neither owns nor was invited to renders Not found, like a missing one.
export default async function OpportunityPage({ params }: OpportunityPageProps) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) {
    notFound();
  }
  const response = await fetchAsReader(`/api/v1/origination/opportunities/${id}`);
  if (!response?.ok) {
    notFound();
  }
  const opportunity = (await response.json()) as Opportunity;
  const identity = readForwardedIdentity(await headers());
  const language = await getLanguage();

  return (
    <SignedInShell>
      <main className="flex flex-col gap-4 p-6">
        <OpportunityView initial={opportunity} permissions={identity.permissions} messages={MESSAGES[language]} />
      </main>
    </SignedInShell>
  );
}
