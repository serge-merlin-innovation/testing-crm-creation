"use client";

import { useEffect, useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import type { MessageKey } from "@/lib/i18n/messages";
import { readString } from "@/lib/json-field";
import { parseSessionPolicy, sessionPolicyBody, type SessionPolicy } from "@/lib/session-policy";
import { apiFetch } from "@/services/api";

const PATH = "/api/v1/sessions/policy";

export function SessionPolicyForm({ messages }: { messages: Record<MessageKey, string> }) {
  const [policy, setPolicy] = useState<SessionPolicy | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    void apiFetch(PATH)
      .then((response) => (response.ok ? response.json() : null))
      .then((payload: unknown) => setPolicy(parseSessionPolicy(payload)))
      .catch(() => setError(messages["settings.saveFailed"]));
  }, [messages]);

  if (!policy) {
    return error ? (
      <Alert variant="destructive">
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    ) : null;
  }

  const number = (key: keyof SessionPolicy) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setPolicy({ ...policy, [key]: Number(event.target.value) });

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    setNotice("");
    setError("");
    const response = await apiFetch(PATH, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(sessionPolicyBody(policy)),
    });
    if (!response.ok) {
      const payload: unknown = await response.json().catch(() => null);
      setError(response.status === 422 ? (readString(payload, "detail") ?? messages["settings.saveFailed"]) : messages["settings.saveFailed"]);
      return;
    }
    setPolicy(parseSessionPolicy(await response.json()));
    setNotice(messages["settings.saved"]);
  };

  return (
    <Card className="max-w-md">
      <CardHeader>
        <CardTitle>
          <h2>{messages["settings.sessionTitle"]}</h2>
        </CardTitle>
        <CardDescription>{messages["settings.newSessionsOnly"]}</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={(event) => void save(event)}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="desktop-idle">{messages["settings.desktopIdle"]}</FieldLabel>
              <Input id="desktop-idle" type="number" min={5} max={120} value={policy.desktopIdleMinutes} onChange={number("desktopIdleMinutes")} />
            </Field>
            <Field>
              <FieldLabel htmlFor="mobile-idle">{messages["settings.mobileIdle"]}</FieldLabel>
              <Input id="mobile-idle" type="number" min={5} max={120} value={policy.mobileIdleMinutes} onChange={number("mobileIdleMinutes")} />
            </Field>
            <Field>
              <FieldLabel htmlFor="absolute">{messages["settings.absolute"]}</FieldLabel>
              <Input id="absolute" type="number" min={1} max={24} value={policy.absoluteHours} onChange={number("absoluteHours")} />
            </Field>
            <Field orientation="horizontal">
              <Switch
                id="mobile-read-only"
                checked={policy.mobileReadOnly}
                onCheckedChange={(checked) => setPolicy({ ...policy, mobileReadOnly: checked })}
              />
              <FieldLabel htmlFor="mobile-read-only">{messages["settings.mobileReadOnly"]}</FieldLabel>
            </Field>
          </FieldGroup>
          <div>
            <Button type="submit">{messages["settings.save"]}</Button>
          </div>
          {notice ? (
            <Alert>
              <AlertDescription>{notice}</AlertDescription>
            </Alert>
          ) : null}
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
        </form>
      </CardContent>
    </Card>
  );
}
