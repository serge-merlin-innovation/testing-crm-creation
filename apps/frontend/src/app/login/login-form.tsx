"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/services/auth";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import type { MessageKey } from "@/lib/i18n/messages";

export function LoginForm({
  returnTo,
  messages,
}: {
  returnTo: string;
  messages: Record<MessageKey, string>;
}) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [loginError, setLoginError] = useState("");

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoginError("");
    setIsSigningIn(true);

    try {
      await login(email, password);
      setPassword("");
      // The proxy resolves the role from the session cookie on the next request.
      router.replace(returnTo);
    } catch (error) {
      setLoginError(
        error instanceof Error ? error.message : messages["login.unreachable"],
      );
    } finally {
      setIsSigningIn(false);
    }
  }

  return (
    <main className="flex min-h-svh items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>
            <h1>{messages["login.title"]}</h1>
          </CardTitle>
          <CardDescription>{messages["login.description"]}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={signIn}>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="email">{messages["login.email"]}</FieldLabel>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  autoComplete="email"
                  autoFocus
                  required
                  placeholder="name@firm.be"
                  disabled={isSigningIn}
                  aria-invalid={Boolean(loginError)}
                />
              </Field>

              <Field>
                <FieldLabel htmlFor="password">{messages["login.password"]}</FieldLabel>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
                  required
                  disabled={isSigningIn}
                  aria-invalid={Boolean(loginError)}
                />
              </Field>

              {loginError ? (
                <Alert variant="destructive">
                  <AlertTitle>{messages["login.failed"]}</AlertTitle>
                  <AlertDescription>{loginError}</AlertDescription>
                </Alert>
              ) : null}

              <Button type="submit" disabled={isSigningIn}>
                {isSigningIn ? messages["login.submitting"] : messages["login.submit"]}
              </Button>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
