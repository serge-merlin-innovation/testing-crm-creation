"use client";

import { useState, type FormEvent } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { login, submitSecondFactor, type LoginStep } from "@/services/auth";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import type { MessageKey } from "@/lib/i18n/messages";

type Messages = Record<MessageKey, string>;

function secretOf(otpauthUri: string): string {
  return new URL(otpauthUri).searchParams.get("secret") ?? "";
}

function downloadCodes(codes: string[]) {
  const blob = new Blob([`${codes.join("\n")}\n`], { type: "text/plain" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "crm-recovery-codes.txt";
  link.click();
  URL.revokeObjectURL(link.href);
}

export function LoginForm({
  returnTo,
  messages,
}: {
  returnTo: string;
  messages: Messages;
}) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [trustDevice, setTrustDevice] = useState(false);
  const [step, setStep] = useState<LoginStep | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [loginError, setLoginError] = useState("");

  function advance(next: LoginStep) {
    if (next.step !== "done") {
      setStep(next);
      return;
    }

    if (next.recoveryCodes?.length) {
      setRecoveryCodes(next.recoveryCodes);
      return;
    }

    // The proxy resolves the role from the session cookie on the next request.
    router.replace(returnTo);
  }

  async function run(action: () => Promise<LoginStep>) {
    setLoginError("");
    setIsBusy(true);

    try {
      advance(await action());
    } catch (error) {
      setLoginError(
        error instanceof Error ? error.message : messages["login.unreachable"],
      );
    } finally {
      setIsBusy(false);
    }
  }

  function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void run(async () => {
      const next = await login(email, password);
      setPassword("");
      return next;
    });
  }

  function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!step || step.step === "done") {
      return;
    }
    void run(() => submitSecondFactor(step.challenge, code, trustDevice));
  }

  function startOver() {
    setStep(null);
    setCode("");
    setLoginError("");
  }

  const errorAlert = loginError ? (
    <Alert variant="destructive">
      <AlertTitle>{messages["login.failed"]}</AlertTitle>
      <AlertDescription>{loginError}</AlertDescription>
    </Alert>
  ) : null;

  if (recoveryCodes) {
    return (
      <main className="flex min-h-svh items-center justify-center p-6">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle>
              <h1>{messages["login.recoveryTitle"]}</h1>
            </CardTitle>
            <CardDescription>{messages["login.recoveryDescription"]}</CardDescription>
          </CardHeader>
          <CardContent>
            <FieldGroup>
              <ul aria-label={messages["login.recoveryTitle"]} className="grid grid-cols-2 gap-2 font-mono">
                {recoveryCodes.map((recoveryCode) => (
                  <li key={recoveryCode}>{recoveryCode}</li>
                ))}
              </ul>
              <Button variant="outline" onClick={() => downloadCodes(recoveryCodes)}>
                {messages["login.recoveryDownload"]}
              </Button>
              <Button onClick={() => router.replace(returnTo)}>{messages["login.continue"]}</Button>
            </FieldGroup>
          </CardContent>
        </Card>
      </main>
    );
  }

  if (step && step.step !== "done") {
    const enrolling = step.step === "enrol";

    return (
      <main className="flex min-h-svh items-center justify-center p-6">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle>
              <h1>{enrolling ? messages["login.enrolTitle"] : messages["login.codeTitle"]}</h1>
            </CardTitle>
            <CardDescription>
              {enrolling ? messages["login.enrolDescription"] : messages["login.codeDescription"]}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={verify}>
              <FieldGroup>
                {step.step === "enrol" ? (
                  <>
                    <Image
                      src={`data:image/svg+xml;utf8,${encodeURIComponent(step.qrSvg)}`}
                      alt="QR code"
                      width={192}
                      height={192}
                      unoptimized
                      className="mx-auto"
                    />
                    <Field>
                      <FieldLabel htmlFor="totp-secret">{messages["login.enrolKey"]}</FieldLabel>
                      <Input id="totp-secret" readOnly value={secretOf(step.otpauthUri)} className="font-mono" />
                    </Field>
                  </>
                ) : null}

                <Field>
                  <FieldLabel htmlFor="code">{messages["login.code"]}</FieldLabel>
                  <Input
                    id="code"
                    value={code}
                    onChange={(event) => setCode(event.target.value)}
                    autoComplete="one-time-code"
                    inputMode={enrolling ? "numeric" : "text"}
                    autoFocus
                    required
                    disabled={isBusy}
                    aria-invalid={Boolean(loginError)}
                  />
                </Field>

                <Field orientation="horizontal">
                  <Checkbox
                    id="trust-device"
                    checked={trustDevice}
                    onCheckedChange={(checked) => setTrustDevice(checked === true)}
                    disabled={isBusy}
                  />
                  <FieldLabel htmlFor="trust-device">{messages["login.trustDevice"]}</FieldLabel>
                </Field>

                {errorAlert}

                <Button type="submit" disabled={isBusy}>
                  {messages["login.verify"]}
                </Button>
                <Button type="button" variant="ghost" onClick={startOver} disabled={isBusy}>
                  {messages["login.retry"]}
                </Button>
              </FieldGroup>
            </form>
          </CardContent>
        </Card>
      </main>
    );
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
                  disabled={isBusy}
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
                  disabled={isBusy}
                  aria-invalid={Boolean(loginError)}
                />
              </Field>

              {errorAlert}

              <Button type="submit" disabled={isBusy}>
                {isBusy ? messages["login.submitting"] : messages["login.submit"]}
              </Button>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
