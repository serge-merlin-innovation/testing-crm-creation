"use client";

import { useState } from "react";
import { ScrollRegion } from "@/components/scroll-region";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { MessageKey } from "@/lib/i18n/messages";
import { sendJson, useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;
type Preference = { kind: string; channel: string };

const CHANNELS: { value: string; label: MessageKey }[] = [
  { value: "both", label: "notifications.both" },
  { value: "in_app", label: "notifications.inApp" },
  { value: "email", label: "notifications.email" },
  { value: "none", label: "notifications.none" },
];

const KIND_LABEL: Record<string, MessageKey> = {
  "deal_team.added": "notifications.kind.dealTeamAdded",
  "task.assigned": "notifications.kind.taskAssigned",
  "task.overdue_digest": "notifications.kind.taskOverdueDigest",
  "milestone.due": "notifications.kind.milestoneDue",
};

/** ACT-06: one channel per event type. Unnamed kinds show their technical name. */
export function NotificationPreferencesCard({ messages }: { messages: Messages }) {
  const preferences = useApiData<Preference[]>("/api/v1/notifications/preferences");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function choose(kind: string, channel: string) {
    const result = await sendJson("/api/v1/notifications/preferences", "PUT", { preferences: { [kind]: channel } });
    if (result.status !== 200) {
      setNotice("");
      setError(messages["common.saveFailed"]);
      return;
    }
    setError("");
    setNotice(messages["notifications.saved"]);
    await preferences.reload();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>{messages["notifications.title"]}</h2>
        </CardTitle>
        <CardDescription>{messages["notifications.description"]}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {preferences.failed ? (
          <Alert variant="destructive">
            <AlertDescription>{messages["common.loadFailed"]}</AlertDescription>
          </Alert>
        ) : null}
        <div className="overflow-x-auto" tabIndex={0}>
          <ScrollRegion label={messages["a11y.scrollRegion"]}>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{messages["notifications.event"]}</TableHead>
                  <TableHead>{messages["notifications.channel"]}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(preferences.data ?? []).map((preference) => {
                  const label = KIND_LABEL[preference.kind] ? messages[KIND_LABEL[preference.kind]] : preference.kind;
                  return (
                    <TableRow key={preference.kind}>
                      <TableCell>{label}</TableCell>
                      <TableCell>
                        <Select value={preference.channel} onValueChange={(value) => void choose(preference.kind, value)}>
                          <SelectTrigger aria-label={`${messages["notifications.channel"]} ${label}`}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {CHANNELS.map((channel) => (
                              <SelectItem key={channel.value} value={channel.value}>
                                {messages[channel.label]}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </ScrollRegion>
        </div>
        {notice ? <p role="status">{notice}</p> : null}
        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}
