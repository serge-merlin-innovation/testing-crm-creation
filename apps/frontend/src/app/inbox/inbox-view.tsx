"use client";

import { useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate } from "@/lib/i18n/format";
import type { Language, MessageKey } from "@/lib/i18n/messages";
import { sendJson, useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;
type Unmatched = { id: number; sender: string; subject: string; received_at: string; correspondents: string[] };
type Contact = { id: number; first_name: string; last_name: string };

export function InboxView({ messages, language }: { messages: Messages; language: Language }) {
  const inbox = useApiData<Unmatched[]>("/api/v1/email-logging/unmatched");
  const contacts = useApiData<Contact[]>("/api/v1/contacts/?q=");
  const [choice, setChoice] = useState<Record<number, string>>({});
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function act(item: Unmatched, action: "link" | "discard") {
    setError("");
    setNotice("");
    const result =
      action === "link"
        ? await sendJson(`/api/v1/email-logging/unmatched/${item.id}/link`, "POST", {
            links: [{ record_type: "contact", record_id: Number(choice[item.id]) }],
          })
        : await sendJson(`/api/v1/email-logging/unmatched/${item.id}`, "DELETE");
    if (result.status !== 201 && result.status !== 204) {
      setError(messages["common.saveFailed"]);
      return;
    }
    setNotice(action === "link" ? messages["inbox.linked"] : messages["inbox.discarded"]);
    await inbox.reload();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h1>{messages["inbox.title"]}</h1>
        </CardTitle>
        <CardDescription>{messages["inbox.description"]}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {inbox.failed ? (
          <Alert variant="destructive">
            <AlertDescription>{messages["common.loadFailed"]}</AlertDescription>
          </Alert>
        ) : null}
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{messages["inbox.subject"]}</TableHead>
                <TableHead>{messages["inbox.from"]}</TableHead>
                <TableHead>{messages["inbox.received"]}</TableHead>
                <TableHead>{messages["inbox.contact"]}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(inbox.data ?? []).map((item) => (
                <TableRow key={item.id}>
                  <TableCell>{item.subject}</TableCell>
                  <TableCell>{item.correspondents.join(", ")}</TableCell>
                  <TableCell>{formatDate(new Date(item.received_at), language)}</TableCell>
                  <TableCell>
                    <Select
                      value={choice[item.id] ?? ""}
                      onValueChange={(value) => setChoice((current) => ({ ...current, [item.id]: value }))}
                    >
                      <SelectTrigger aria-label={`${messages["inbox.contact"]} ${item.subject}`}>
                        <SelectValue placeholder={messages["inbox.pickContact"]} />
                      </SelectTrigger>
                      <SelectContent>
                        {(contacts.data ?? []).map((contact) => (
                          <SelectItem key={contact.id} value={String(contact.id)}>
                            {contact.first_name} {contact.last_name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell className="flex gap-2">
                    <Button size="sm" disabled={!choice[item.id]} onClick={() => void act(item, "link")}>
                      {messages["inbox.link"]}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => void act(item, "discard")}>
                      {messages["inbox.discard"]}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        {inbox.data?.length === 0 ? <p>{messages["common.empty"]}</p> : null}
        {notice ? <p role="status">{notice}</p> : null}
        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}
