"use client";

import { type FormEvent, useState } from "react";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { downloadWithStepUp } from "@/lib/access";
import type { MessageKey } from "@/lib/i18n/messages";
import { apiFetch } from "@/services/api";

type Messages = Record<MessageKey, string>;

/** A mass export button that asks the 2FA code again before downloading (AUTH-02 c5). */
export function StepUpExport({
  path,
  filename,
  label,
  messages,
  onDone,
}: {
  path: string;
  filename: string;
  label: string;
  messages: Messages;
  onDone?: () => void | Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const result = await downloadWithStepUp((url, init) => apiFetch(url, { ...init, bounce: false }), path, code);
    setCode("");
    if (result.kind === "code") {
      setError(messages["stepUp.wrongCode"]);
      return;
    }
    if (result.kind === "error") {
      setError(result.message || messages["common.loadFailed"]);
      return;
    }
    const link = document.createElement("a");
    link.href = URL.createObjectURL(result.blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
    setOpen(false);
    await onDone?.();
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        setError(null);
        setCode("");
      }}
    >
      <AlertDialogTrigger asChild>
        <Button variant="outline">{label}</Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <form aria-label={messages["stepUp.title"]} onSubmit={(event) => void submit(event)}>
          <AlertDialogHeader>
            <AlertDialogTitle>{messages["stepUp.title"]}</AlertDialogTitle>
            <AlertDialogDescription>{messages["stepUp.description"]}</AlertDialogDescription>
          </AlertDialogHeader>
          <FieldGroup className="py-4">
            <Field>
              <FieldLabel htmlFor="step-up-code">{messages["access.code"]}</FieldLabel>
              <Input
                id="step-up-code"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={code}
                onChange={(event) => setCode(event.target.value)}
              />
              <FieldError>{error}</FieldError>
            </Field>
          </FieldGroup>
          <AlertDialogFooter>
            <AlertDialogCancel type="button">{messages["stepUp.cancel"]}</AlertDialogCancel>
            <Button type="submit" disabled={!code.trim()}>
              {messages["stepUp.confirm"]}
            </Button>
          </AlertDialogFooter>
        </form>
      </AlertDialogContent>
    </AlertDialog>
  );
}
