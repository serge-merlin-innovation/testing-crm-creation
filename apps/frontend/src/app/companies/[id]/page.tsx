import { notFound } from "next/navigation";
import { SignedInShell } from "@/components/signed-in-shell";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { fetchAsReader } from "@/lib/server-fetch";
import { CompanyView, type CompanyDetail } from "./company-view";

type CompanyPageProps = { params: Promise<{ id: string }> };

export default async function CompanyPage({ params }: CompanyPageProps) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) {
    notFound();
  }
  const response = await fetchAsReader(`/api/v1/companies/${id}`);
  if (!response?.ok) {
    notFound();
  }
  const company = (await response.json()) as CompanyDetail;
  const language = await getLanguage();

  return (
    <SignedInShell>
      <main className="flex flex-col gap-4 p-6">
        <CompanyView initial={company} messages={MESSAGES[language]} language={language} />
      </main>
    </SignedInShell>
  );
}
