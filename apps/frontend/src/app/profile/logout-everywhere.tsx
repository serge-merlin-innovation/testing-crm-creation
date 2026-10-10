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
import { LOGIN_PATH } from "@/lib/auth-routing";
import type { MessageKey } from "@/lib/i18n/messages";
import { unsavedChanges } from "@/lib/unsaved-changes";
import { clearApiCsrfToken } from "@/services/api";
import { logoutEverywhere } from "@/services/session";

export function LogoutEverywhereCard({ messages }: { messages: Record<MessageKey, string> }) {
  const [error, setError] = useState("");

  const confirm = async () => {
    try {
      await logoutEverywhere();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "");
      return;
    }
    unsavedChanges.clear();
    clearApiCsrfToken();
    window.location.replace(LOGIN_PATH);
  };

  return (
    <Card className="max-w-md">
      <CardHeader>
        <CardTitle>
          <h2>{messages["profile.logoutEverywhere"]}</h2>
        </CardTitle>
        <CardDescription>{messages["profile.logoutEverywhereDescription"]}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="destructive">{messages["profile.logoutEverywhere"]}</Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{messages["profile.logoutEverywhere"]}</AlertDialogTitle>
              <AlertDialogDescription>{messages["profile.logoutEverywhereDescription"]}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{messages["logout.cancel"]}</AlertDialogCancel>
              <AlertDialogAction variant="destructive" onClick={() => void confirm()}>
                {messages["profile.logoutEverywhereConfirm"]}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}
