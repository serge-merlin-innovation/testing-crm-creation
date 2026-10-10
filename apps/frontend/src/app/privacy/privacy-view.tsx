"use client";

import { useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { readDetail } from "@/lib/deals";
import type { MessageKey } from "@/lib/i18n/messages";
import { sendJson, useApiData } from "@/lib/use-api";
import { apiFetch } from "@/services/api";

type Messages = Record<MessageKey, string>;
type Contact = { id: number; first_name: string; last_name: string; email: string | null };
type Review = { id: number; contact_id: number; contact_name: string; last_interaction_at: string };

async function download(path: string, filename: string): Promise<boolean> {
  const response = await apiFetch(path).catch(() => null);
  if (!response?.ok) return false;
  const link = document.createElement("a");
  link.href = URL.createObjectURL(await response.blob());
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
  return true;
}

export function PrivacyView({ messages, isCompliance }: { messages: Messages; isCompliance: boolean }) {
  const reviews = useApiData<Review[]>("/api/v1/privacy/retention-reviews");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const contacts = useApiData<Contact[]>(isCompliance ? `/api/v1/contacts/?q=${encodeURIComponent(search)}` : null);
  const [hold, setHold] = useState<Record<number, string>>({});
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function act(path: string, method: "POST", body: unknown, done: string) {
    setNotice("");
    setError("");
    const result = await sendJson(path, method, body);
    if (result.status >= 200 && result.status < 300) {
      setNotice(done);
      await Promise.all([contacts.reload(), reviews.reload()]);
      return;
    }
    setError(readDetail(result.body, messages["common.saveFailed"]));
  }

  const alerts = (
    <>
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {notice ? (
        <Alert>
          <AlertDescription role="status">{notice}</AlertDescription>
        </Alert>
      ) : null}
    </>
  );

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>
            <h1>{messages["privacy.reviews"]}</h1>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{messages["privacy.contact"]}</TableHead>
                <TableHead>{messages["privacy.lastInteraction"]}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(reviews.data ?? []).map((review) => (
                <TableRow key={review.id}>
                  <TableCell>{review.contact_name}</TableCell>
                  <TableCell>{review.last_interaction_at.slice(0, 10)}</TableCell>
                  <TableCell className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        void act(`/api/v1/privacy/retention-reviews/${review.id}`, "POST", { decision: "keep" }, messages["common.save"])
                      }
                    >
                      {messages["privacy.keep"]}
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() =>
                        void act(
                          `/api/v1/privacy/retention-reviews/${review.id}`,
                          "POST",
                          { decision: "anonymise" },
                          messages["privacy.erased"],
                        )
                      }
                    >
                      {messages["privacy.anonymise"]}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {reviews.data?.length === 0 ? <p>{messages["common.empty"]}</p> : null}
          {isCompliance ? null : alerts}
        </CardContent>
      </Card>

      {isCompliance ? (
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>{messages["privacy.title"]}</h2>
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <form
              className="flex gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                setSearch(query);
              }}
            >
              <Input aria-label={messages["common.search"]} value={query} onChange={(event) => setQuery(event.target.value)} />
              <Button type="submit" variant="outline">
                {messages["common.search"]}
              </Button>
            </form>
            {alerts}
            <div className="overflow-x-auto" tabIndex={0}>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{messages["privacy.contact"]}</TableHead>
                    <TableHead>{messages["privacy.hold"]}</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(contacts.data ?? []).map((contact) => {
                    const name = `${contact.first_name} ${contact.last_name}`;
                    return (
                      <TableRow key={contact.id}>
                        <TableCell>
                          {name}
                          <br />
                          {contact.email ?? ""}
                        </TableCell>
                        <TableCell>
                          <Field orientation="horizontal">
                            <FieldLabel htmlFor={`hold-${contact.id}`} className="sr-only">
                              {messages["privacy.hold"]}
                            </FieldLabel>
                            <Input
                              id={`hold-${contact.id}`}
                              value={hold[contact.id] ?? ""}
                              placeholder={messages["privacy.holdPlaceholder"]}
                              onChange={(event) => setHold({ ...hold, [contact.id]: event.target.value })}
                            />
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={(hold[contact.id] ?? "").trim().length < 3}
                              onClick={() =>
                                void act(
                                  `/api/v1/contacts/${contact.id}/legal-holds`,
                                  "POST",
                                  { reason: hold[contact.id] },
                                  messages["privacy.holdAdded"],
                                )
                              }
                            >
                              {messages["privacy.addHold"]}
                            </Button>
                          </Field>
                        </TableCell>
                        <TableCell className="flex gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            aria-label={`${messages["privacy.export"]} ${name}`}
                            onClick={() =>
                              void download(`/api/v1/contacts/${contact.id}/export`, `person-${contact.id}.json`).then(
                                (ok) => (ok ? undefined : setError(messages["common.loadFailed"])),
                              )
                            }
                          >
                            {messages["privacy.export"]}
                          </Button>
                          <AlertDialog>
                            <AlertDialogTrigger asChild>
                              <Button size="sm" variant="destructive" aria-label={`${messages["privacy.erase"]} ${name}`}>
                                {messages["privacy.erase"]}
                              </Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                              <AlertDialogHeader>
                                <AlertDialogTitle>
                                  {messages["privacy.erase"]} {name}
                                </AlertDialogTitle>
                                <AlertDialogDescription>{messages["privacy.eraseConfirm"]}</AlertDialogDescription>
                              </AlertDialogHeader>
                              <AlertDialogFooter>
                                <AlertDialogCancel>{messages["login.retry"]}</AlertDialogCancel>
                                <AlertDialogAction
                                  onClick={() =>
                                    void act(`/api/v1/contacts/${contact.id}/erase`, "POST", undefined, messages["privacy.erased"])
                                  }
                                >
                                  {messages["privacy.erase"]}
                                </AlertDialogAction>
                              </AlertDialogFooter>
                            </AlertDialogContent>
                          </AlertDialog>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
