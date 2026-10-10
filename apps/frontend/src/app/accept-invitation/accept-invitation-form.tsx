"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { LoginForm } from "@/app/login/login-form";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { DEFAULT_AUTHENTICATED_PATH, LOGIN_PATH } from "@/lib/auth-routing";
import type { MessageKey } from "@/lib/i18n/messages";
import { acceptInvitation, readInvitation, type Invitation, type LoginStep } from "@/services/auth";

type Messages = Record<MessageKey, string>;

export function AcceptInvitationForm({ token, messages }: { token: string; messages: Messages }) {
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  const [linkError, setLinkError] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState<LoginStep | null>(null);

  useEffect(() => {
    void readInvitation(token)
      .then(setInvitation)
      .catch((failure: unknown) => setLinkError(failure instanceof Error ? failure.message : messages["common.loadFailed"]));
  }, [token, messages]);

  if (step) {
    return <LoginForm returnTo={DEFAULT_AUTHENTICATED_PATH} messages={messages} initialStep={step} />;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (password !== confirm) {
      setError(messages["account.mismatch"]);
      return;
    }
    setBusy(true);
    try {
      setStep(await acceptInvitation(token, password));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : messages["common.saveFailed"]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-svh items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>
            <h1>{messages["account.inviteTitle"]}</h1>
          </CardTitle>
          <CardDescription>{messages["account.inviteDescription"]}</CardDescription>
        </CardHeader>
        <CardContent>
          {linkError ? (
            <FieldGroup>
              <Alert variant="destructive">
                <AlertDescription>{linkError}</AlertDescription>
              </Alert>
              <Button asChild variant="outline">
                <Link href={LOGIN_PATH}>{messages["account.backToLogin"]}</Link>
              </Button>
            </FieldGroup>
          ) : (
            <form onSubmit={(event) => void submit(event)}>
              <FieldGroup>
                <Field>
                  <FieldLabel htmlFor="invite-email">{messages["login.email"]}</FieldLabel>
                  <Input id="invite-email" readOnly value={invitation?.email ?? ""} autoComplete="username" />
                </Field>
                <Field>
                  <FieldLabel htmlFor="new-password">{messages["account.newPassword"]}</FieldLabel>
                  <Input
                    id="new-password"
                    type="password"
                    autoComplete="new-password"
                    required
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    aria-invalid={Boolean(error)}
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="confirm-password">{messages["account.confirmPassword"]}</FieldLabel>
                  <Input
                    id="confirm-password"
                    type="password"
                    autoComplete="new-password"
                    required
                    value={confirm}
                    onChange={(event) => setConfirm(event.target.value)}
                  />
                </Field>
                <p className="text-muted-foreground text-sm">{messages["account.resetDescription"]}</p>
                {error ? (
                  <Alert variant="destructive">
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                ) : null}
                <Button type="submit" disabled={busy || !invitation}>
                  {messages["account.setPassword"]}
                </Button>
              </FieldGroup>
            </form>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
