import { notFound } from "next/navigation";
import { SignedInShell } from "@/components/signed-in-shell";
import type { Mandate } from "@/lib/deals";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { fetchAsReader } from "@/lib/server-fetch";
import { DealView } from "./deal-view";

type DealPageProps = { params: Promise<{ id: string }> };

// AUTHZ-02 / AUTH-01 c7: a deal the reader cannot see renders Not found, exactly like a missing one.
export default async function DealPage({ params }: DealPageProps) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) {
    notFound();
  }
  const response = await fetchAsReader(`/api/v1/mandates/${id}`);
  if (!response?.ok) {
    notFound();
  }
  const mandate = (await response.json()) as Mandate;
  const language = await getLanguage();

  return (
    <SignedInShell>
      <main className="flex flex-col gap-4 p-6">
        <DealView initial={mandate} messages={MESSAGES[language]} />
      </main>
    </SignedInShell>
  );
}
