"use client";

import { useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LANGUAGE_COOKIE, LANGUAGES, type Language, type MessageKey } from "@/lib/i18n/messages";
import { useApiData, sendJson } from "@/lib/use-api";

const NAMES: Record<Language, string> = { en: "English", fr: "Français", nl: "Nederlands" };

export function LanguageCard({ messages, language }: { messages: Record<MessageKey, string>; language: Language }) {
  const me = useApiData<{ id: number }>("/api/v1/users/me");
  const [error, setError] = useState("");

  async function choose(value: string) {
    if (!me.data) {
      return;
    }
    const result = await sendJson(`/api/v1/users/${me.data.id}`, "PATCH", { language: value });
    if (result.status !== 200) {
      setError(messages["profile.languageFailed"]);
      return;
    }
    document.cookie = `${LANGUAGE_COOKIE}=${value}; path=/; max-age=31536000; samesite=lax`;
    window.location.reload();
  }

  return (
    <Card className="max-w-md">
      <CardHeader>
        <CardTitle>
          <h2>{messages["profile.language"]}</h2>
        </CardTitle>
        <CardDescription>{messages["profile.languageDescription"]}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Field>
          <FieldLabel htmlFor="profile-language">{messages["profile.language"]}</FieldLabel>
          <Select value={language} onValueChange={(value) => void choose(value)} disabled={!me.data}>
            <SelectTrigger id="profile-language">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LANGUAGES.map((option) => (
                <SelectItem key={option} value={option} lang={option}>
                  {NAMES[option]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}
