"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate } from "@/lib/i18n/format";
import type { Language, MessageKey } from "@/lib/i18n/messages";
import { useApiData } from "@/lib/use-api";

type Interaction = { user_id: number; name: string; count: number; last_interaction_at: string };

/** CON-02 c2: last interaction and count per colleague, from logged emails and meetings. */
export function WhoKnows({
  contactId,
  contactName,
  messages,
  language,
}: {
  contactId: number;
  contactName: string;
  messages: Record<MessageKey, string>;
  language: Language;
}) {
  const rows = useApiData<Interaction[]>(`/api/v1/contacts/${contactId}/interactions`);

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>
            {messages["contacts.relationshipsTitle"]} {contactName}
          </h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Table aria-label={`${messages["contacts.relationshipsTitle"]} ${contactName}`}>
          <TableHeader>
            <TableRow>
              <TableHead>{messages["contacts.colleague"]}</TableHead>
              <TableHead>{messages["contacts.interactions"]}</TableHead>
              <TableHead>{messages["contacts.lastInteraction"]}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(rows.data ?? []).map((row) => (
              <TableRow key={row.user_id}>
                <TableCell>{row.name}</TableCell>
                <TableCell>{row.count}</TableCell>
                <TableCell>{formatDate(new Date(row.last_interaction_at), language)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {rows.data?.length === 0 ? <p>{messages["common.empty"]}</p> : null}
      </CardContent>
    </Card>
  );
}
