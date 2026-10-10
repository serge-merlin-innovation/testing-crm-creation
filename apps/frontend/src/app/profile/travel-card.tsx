"use client";

import { useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { readDetail } from "@/lib/deals";
import type { MessageKey } from "@/lib/i18n/messages";
import { sendJson, useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;
type Me = { id: number };
type Security = { travel_from: string | null; travel_until: string | null };

/** AUTH-12 c1: my own travelling range; no new-country alerts while it lasts. */
export function TravelCard({ messages }: { messages: Messages }) {
  const me = useApiData<Me>("/api/v1/users/me");
  const security = useApiData<Security>(me.data ? `/api/v1/users/${me.data.id}/security` : null);
  const [edited, setEdited] = useState<{ from: string; until: string } | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const value = edited ?? { from: security.data?.travel_from ?? "", until: security.data?.travel_until ?? "" };

  async function save(from: string, until: string) {
    if (!me.data) {
      return;
    }
    setNotice("");
    setError("");
    const result = await sendJson(`/api/v1/users/${me.data.id}/travel`, "PUT", {
      travel_from: from || null,
      travel_until: until || null,
    });
    if (result.status >= 200 && result.status < 300) {
      setNotice(messages["users.travelSaved"]);
      setEdited(null);
      await security.reload();
      return;
    }
    setError(readDetail(result.body, messages["common.saveFailed"]));
  }

  return (
    <Card className="max-w-md" role="region" aria-labelledby="travel-title">
      <CardHeader>
        <CardTitle>
          <h2 id="travel-title">{messages["users.travel"]}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end gap-2">
          <Field>
            <FieldLabel htmlFor="my-travel-from">{messages["users.travelFrom"]}</FieldLabel>
            <Input
              id="my-travel-from"
              type="date"
              value={value.from}
              onChange={(event) => setEdited({ ...value, from: event.target.value })}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="my-travel-until">{messages["users.travelUntil"]}</FieldLabel>
            <Input
              id="my-travel-until"
              type="date"
              value={value.until}
              onChange={(event) => setEdited({ ...value, until: event.target.value })}
            />
          </Field>
        </div>
        <div className="flex gap-2">
          <Button size="sm" disabled={!me.data} onClick={() => void save(value.from, value.until)}>
            {messages["users.travelSave"]}
          </Button>
          <Button size="sm" variant="ghost" disabled={!me.data} onClick={() => void save("", "")}>
            {messages["users.travelClear"]}
          </Button>
        </div>
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
      </CardContent>
    </Card>
  );
}
