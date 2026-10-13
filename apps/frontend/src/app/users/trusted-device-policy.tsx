"use client";

import { useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Switch } from "@/components/ui/switch";
import type { MessageKey } from "@/lib/i18n/messages";
import { sendJson, useApiData } from "@/lib/use-api";

type Policy = { trusted_devices_enabled: boolean };

export function TrustedDevicePolicy({ messages }: { messages: Record<MessageKey, string> }) {
  const policy = useApiData<Policy>("/api/v1/security/policy");
  const [error, setError] = useState("");

  async function toggle(enabled: boolean) {
    setError("");
    const result = await sendJson("/api/v1/security/policy", "PUT", { trusted_devices_enabled: enabled });
    if (result.status !== 200) {
      setError(messages["common.saveFailed"]);
    }
    await policy.reload();
  }

  return (
    <Card className="max-w-md">
      <CardHeader>
        <CardTitle>
          <h2>{messages["users.policyTitle"]}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Field orientation="horizontal">
          <Switch
            id="trusted-devices"
            checked={policy.data?.trusted_devices_enabled ?? false}
            disabled={!policy.data}
            onCheckedChange={(checked) => void toggle(checked)}
          />
          <FieldLabel htmlFor="trusted-devices">{messages["users.trustedDevices"]}</FieldLabel>
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
