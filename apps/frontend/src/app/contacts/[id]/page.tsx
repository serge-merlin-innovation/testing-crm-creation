import { notFound } from "next/navigation";
import { SignedInShell } from "@/components/signed-in-shell";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";
import { fetchAsReader } from "@/lib/server-fetch";
import { ContactView, type ContactDetail } from "./contact-view";

type ContactPageProps = { params: Promise<{ id: string }> };

export default async function ContactPage({ params }: ContactPageProps) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) {
    notFound();
  }
  const response = await fetchAsReader(`/api/v1/contacts/${id}`);
  if (!response?.ok) {
    notFound();
  }
  const contact = (await response.json()) as ContactDetail;
  const language = await getLanguage();

  return (
    <SignedInShell>
      <main className="flex flex-col gap-4 p-6">
        <ContactView initial={contact} messages={MESSAGES[language]} language={language} />
      </main>
    </SignedInShell>
  );
}
