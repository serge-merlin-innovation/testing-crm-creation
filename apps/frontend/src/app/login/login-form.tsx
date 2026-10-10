"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { getMicrosoftAuthorizeUrl, login } from "@/services/auth";
import Image from "next/image";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldSeparator,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";

export function LoginForm({
  returnTo,
  initialError = "",
}: {
  returnTo: string;
  initialError?: string;
}) {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [isRedirecting, setIsRedirecting] = useState(false);
  const [loginError, setLoginError] = useState(initialError);
  // Tracked separately from loginError so the username/password fields only turn
  // red when *they* were rejected. An OAuth callback failure (an unlinked Microsoft
  // account) says nothing about the typed credentials, and marking them invalid
  // would send the user off to re-check a password that was never the problem.
  const [hasCredentialError, setHasCredentialError] = useState(false);

  // Either sign-in path in flight disables both, so a user cannot start a
  // Microsoft redirect on top of a pending password submit.
  const isBusy = isSigningIn || isRedirecting;

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoginError("");
    setHasCredentialError(false);
    setIsSigningIn(true);

    try {
      await login(username, password);
      setPassword("");
      // The proxy resolves the role from the session cookie on the next request, so there is
      // nothing to cache here.
      router.replace(returnTo);
    } catch (error) {
      setLoginError(
        error instanceof Error
          ? error.message
          : "We could not reach the backend.",
      );
      setHasCredentialError(true);
    } finally {
      setIsSigningIn(false);
    }
  }

  async function signInWithMicrosoft() {
    setLoginError("");
    setHasCredentialError(false);
    setIsRedirecting(true);

    try {
      // A full navigation, not router.push — the next stop is Microsoft's domain.
      window.location.assign(await getMicrosoftAuthorizeUrl(returnTo));
    } catch (error) {
      setLoginError(
        error instanceof Error
          ? error.message
          : "We could not start Microsoft sign-in.",
      );
      // Only reset on failure: on success the page is already navigating away, and
      // clearing the spinner would flash an idle button during the redirect.
      setIsRedirecting(false);
    }
  }

  return (
    <main className="flex min-h-svh items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>
            <h1>Welcome back</h1>
          </CardTitle>
          <CardDescription>Sign in to continue to your workspace.</CardDescription>
        </CardHeader>
        <CardContent>
          <FieldGroup>
            <form onSubmit={signIn}>
              <FieldGroup>
                <Field>
                  <FieldLabel htmlFor="username">Username or email</FieldLabel>
                  <Input
                    id="username"
                    type="text"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    autoComplete="username"
                    autoFocus
                    required
                    placeholder="name@company.com"
                    disabled={isBusy}
                    aria-invalid={hasCredentialError}
                  />
                </Field>

                <Field>
                  <FieldLabel htmlFor="password">Password</FieldLabel>
                  <Input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    autoComplete="current-password"
                    required
                    placeholder="Enter your password"
                    disabled={isBusy}
                    aria-invalid={hasCredentialError}
                  />
                </Field>

                {loginError ? (
                  <Alert variant="destructive">
                    <AlertTitle>Sign-in failed</AlertTitle>
                    <AlertDescription>{loginError}</AlertDescription>
                  </Alert>
                ) : null}

                <Button type="submit" disabled={isBusy}>
                  {isSigningIn ? "Signing in…" : "Sign in securely"}
                </Button>
              </FieldGroup>
            </form>

            <FieldSeparator>or</FieldSeparator>

            <Button
              type="button"
              variant="outline"
              disabled={isBusy}
              onClick={signInWithMicrosoft}
            >
              <Image src="/microsoft-logo.svg" alt="" width={16} height={16} />
              {isRedirecting ? "Redirecting…" : "Sign in with Microsoft"}
            </Button>
          </FieldGroup>
        </CardContent>
      </Card>
    </main>
  );
}
