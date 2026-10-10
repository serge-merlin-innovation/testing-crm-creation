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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import type { MessageKey } from "@/lib/i18n/messages";
import { sendJson, useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;
type Feed = { url: string };

export function EmailLoggingCard({ messages }: { messages: Messages }) {
  const address = useApiData<{ address: string }>("/api/v1/email-logging/address");

  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>
          <h2>{messages["mail.title"]}</h2>
        </CardTitle>
        <CardDescription>{messages["mail.description"]}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Field>
          <FieldLabel htmlFor="logging-address">{messages["mail.address"]}</FieldLabel>
          <Input id="logging-address" readOnly value={address.data?.address ?? ""} />
        </Field>
        <Button asChild variant="outline" className="self-start">
          <a href="/inbox">{messages["mail.openInbox"]}</a>
        </Button>
      </CardContent>
    </Card>
  );
}

export function CalendarFeedCard({ messages }: { messages: Messages }) {
  const feed = useApiData<Feed>("/api/v1/calendar-feed/");
  const [url, setUrl] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const shown = url ?? feed.data?.url ?? "";

  async function copy() {
    await navigator.clipboard.writeText(shown).catch(() => undefined);
    setNotice(messages["feed.copied"]);
  }

  async function regenerate() {
    setError("");
    const result = await sendJson("/api/v1/calendar-feed/regenerate", "POST");
    if (result.status !== 200) {
      setError(messages["common.saveFailed"]);
      return;
    }
    setUrl((result.body as Feed).url);
    setNotice(messages["feed.regenerated"]);
  }

  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>
          <h2>{messages["feed.title"]}</h2>
        </CardTitle>
        <CardDescription>{messages["feed.description"]}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Field>
          <FieldLabel htmlFor="calendar-url">{messages["feed.url"]}</FieldLabel>
          <Input id="calendar-url" readOnly value={shown} />
        </Field>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => void copy()} disabled={!shown}>
            {messages["feed.copy"]}
          </Button>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive">{messages["feed.regenerate"]}</Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>{messages["feed.regenerate"]}</AlertDialogTitle>
                <AlertDialogDescription>{messages["feed.regenerateDescription"]}</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>{messages["logout.cancel"]}</AlertDialogCancel>
                <AlertDialogAction variant="destructive" onClick={() => void regenerate()}>
                  {messages["feed.regenerateConfirm"]}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
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
