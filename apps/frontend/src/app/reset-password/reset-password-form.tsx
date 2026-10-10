"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { LOGIN_PATH } from "@/lib/auth-routing";
import type { MessageKey } from "@/lib/i18n/messages";
import { requestPasswordReset, resetPassword } from "@/services/auth";

type Messages = Record<MessageKey, string>;

/** Without a token it asks for the email; with the emailed token it sets the new password. */
export function ResetPasswordForm({ token, messages }: { token: string; messages: Messages }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<void>, done: string) {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      await action();
      setNotice(done);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : messages["common.saveFailed"]);
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      void run(() => requestPasswordReset(email), messages["account.forgotSent"]);
      return;
    }
    if (password !== confirm) {
      setError(messages["account.mismatch"]);
      return;
    }
    void run(() => resetPassword(token, password), messages["account.resetDone"]);
  }

  const finished = Boolean(token && notice);

  return (
    <main className="flex min-h-svh items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>
            <h1>{token ? messages["account.resetTitle"] : messages["account.forgotTitle"]}</h1>
          </CardTitle>
          <CardDescription>
            {token ? messages["account.resetDescription"] : messages["account.forgotDescription"]}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit}>
            <FieldGroup>
              {token ? (
                <>
                  <Field>
                    <FieldLabel htmlFor="new-password">{messages["account.newPassword"]}</FieldLabel>
                    <Input
                      id="new-password"
                      type="password"
                      autoComplete="new-password"
                      required
                      disabled={finished}
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
                      disabled={finished}
                      value={confirm}
                      onChange={(event) => setConfirm(event.target.value)}
                    />
                  </Field>
                </>
              ) : (
                <Field>
                  <FieldLabel htmlFor="email">{messages["login.email"]}</FieldLabel>
                  <Input
                    id="email"
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                  />
                </Field>
              )}
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
              {finished ? null : (
                <Button type="submit" disabled={busy}>
                  {token ? messages["account.setPassword"] : messages["account.sendLink"]}
                </Button>
              )}
              <Button asChild variant="ghost">
                <Link href={LOGIN_PATH}>{messages["account.backToLogin"]}</Link>
              </Button>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
