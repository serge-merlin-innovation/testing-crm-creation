import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { SignedInShell } from "@/components/signed-in-shell";
import type { Mandate } from "@/lib/deals";
import { DEALS_READ_SUMMARY } from "@/lib/fees";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { fetchAsReader } from "@/lib/server-fetch";
import { readForwardedIdentity } from "@/lib/session-identity";
import { DealView } from "./deal-view";

type DealPageProps = { params: Promise<{ id: string }> };

// AUTHZ-02 / AUTH-01 c7: a deal the reader cannot see renders Not found, exactly like a missing one.
export default async function DealPage({ params }: DealPageProps) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) {
    notFound();
  }
  const identity = readForwardedIdentity(await headers());
  let summaryOnly = false;
  let response = await fetchAsReader(`/api/v1/mandates/${id}`);
  if (response?.status === 404 && identity.permissions.includes(DEALS_READ_SUMMARY)) {
    // Back-office on a deal it is not staffed on: the read-only summary (ROLE-01 c4).
    response = await fetchAsReader(`/api/v1/mandates/${id}/summary`);
    summaryOnly = true;
  }
  if (!response?.ok) {
    notFound();
  }
  const mandate = (await response.json()) as Mandate;
  const language = await getLanguage();

  return (
    <SignedInShell>
      <main className="flex flex-col gap-4 p-6">
        <DealView
          initial={mandate}
          permissions={identity.permissions}
          summaryOnly={summaryOnly}
          messages={MESSAGES[language]}
        />
      </main>
    </SignedInShell>
  );
}
