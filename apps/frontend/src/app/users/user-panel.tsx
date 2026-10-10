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
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { readDetail } from "@/lib/deals";
import type { MessageKey } from "@/lib/i18n/messages";
import {
  canConfirm,
  ownerCandidates,
  type OffboardingConfirmation,
  type OffboardingPreview,
} from "@/lib/offboarding";
import { sendJson, useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;

export type DirectoryUser = {
  id: number;
  name: string;
  email: string;
  role_name: string | null;
  status: string;
  last_login_at: string | null;
};

type SecurityProfile = {
  two_factor_enabled: boolean;
  locked_until: string | null;
  travel_from: string | null;
  travel_until: string | null;
};

export function UserPanel({
  user,
  everyone,
  messages,
  onChanged,
}: {
  user: DirectoryUser;
  everyone: DirectoryUser[];
  messages: Messages;
  onChanged: () => Promise<void>;
}) {
  const inactive = user.status === "inactive";
  const security = useApiData<SecurityProfile>(inactive ? null : `/api/v1/users/${user.id}/security`);
  const preview = useApiData<OffboardingPreview>(inactive ? null : `/api/v1/users/${user.id}/offboarding`);
  const [travel, setTravel] = useState<{ from: string; until: string } | null>(null);
  const [newOwner, setNewOwner] = useState<number | null>(null);
  const [confirmation, setConfirmation] = useState<OffboardingConfirmation | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const travelValue = travel ?? {
    from: security.data?.travel_from ?? "",
    until: security.data?.travel_until ?? "",
  };

  async function act(path: string, method: "POST" | "PUT", body: unknown, done: string) {
    setNotice("");
    setError("");
    const result = await sendJson(path, method, body);
    if (result.status >= 200 && result.status < 300) {
      setNotice(done);
      await security.reload();
      return result.body;
    }
    setError(readDetail(result.body, messages["common.saveFailed"]));
    return null;
  }

  async function saveTravel(from: string, until: string) {
    await act(
      `/api/v1/users/${user.id}/travel`,
      "PUT",
      { travel_from: from || null, travel_until: until || null },
      messages["users.travelSaved"],
    );
    setTravel(null);
  }

  async function deactivate() {
    const body = await act(`/api/v1/users/${user.id}/deactivate`, "POST", { new_owner_id: newOwner }, "");
    if (body) {
      setConfirmation(body as OffboardingConfirmation);
      setNotice("");
      await onChanged();
    }
  }

  async function reactivate() {
    if (await act(`/api/v1/users/${user.id}/reactivate`, "POST", undefined, messages["users.reactivated"])) {
      await onChanged();
    }
  }

  const records = preview.data ? [...preview.data.contacts, ...preview.data.tasks, ...preview.data.deals] : [];
  const candidates = preview.data ? ownerCandidates(preview.data, everyone) : [];

  const alerts = (
    <>
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
    </>
  );

  if (confirmation) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>
            <h2>{messages["users.confirmation"]}</h2>
          </CardTitle>
          <CardDescription>{user.email}</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-2" aria-label={messages["users.confirmation"]}>
            <dt>{messages["users.sessionsEnded"]}</dt>
            <dd>{confirmation.sessions_ended}</dd>
            <dt>{messages["users.tokensRevoked"]}</dt>
            <dd>{confirmation.api_tokens_revoked + confirmation.api_clients_revoked}</dd>
            <dt>{messages["users.membershipsRemoved"]}</dt>
            <dd>{confirmation.deal_memberships_removed}</dd>
            <dt>{messages["users.reassigned"]}</dt>
            <dd>{confirmation.new_owner_name ?? "-"}</dd>
          </dl>
          <ul className="mt-4 flex flex-col gap-1" aria-label={messages["users.owned"]}>
            {confirmation.reassigned.map((record) => (
              <li key={`${record.type}-${record.id}`}>
                {record.type}: {record.label}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    );
  }

  if (inactive) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>
            <h2>{user.name}</h2>
          </CardTitle>
          <CardDescription>{user.email}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Button className="self-start" onClick={() => void reactivate()}>
            {messages["users.reactivate"]}
          </Button>
          {alerts}
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>
            <h2>{messages["users.security"]}</h2>
          </CardTitle>
          <CardDescription>{user.email}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <FieldGroup>
            <Field orientation="horizontal">
              <FieldLabel>{messages["users.locked"]}</FieldLabel>
              <span>{security.data?.locked_until ?? messages["users.notLocked"]}</span>
              <Button
                size="sm"
                variant="outline"
                disabled={!security.data?.locked_until}
                onClick={() => void act(`/api/v1/users/${user.id}/unlock`, "POST", undefined, messages["users.unlocked"])}
              >
                {messages["users.unlock"]}
              </Button>
            </Field>
            <Field orientation="horizontal">
              <FieldLabel>{messages["users.twoFactor"]}</FieldLabel>
              <span>{security.data?.two_factor_enabled ? messages["users.twoFactorOn"] : messages["users.twoFactorOff"]}</span>
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  void act(`/api/v1/users/${user.id}/reset-2fa`, "POST", undefined, messages["users.reset2faDone"])
                }
              >
                {messages["users.reset2fa"]}
              </Button>
            </Field>
            <FieldLabel>{messages["users.travel"]}</FieldLabel>
            <div className="flex flex-wrap items-end gap-2">
              <Field>
                <FieldLabel htmlFor="travel-from">{messages["users.travelFrom"]}</FieldLabel>
                <Input
                  id="travel-from"
                  type="date"
                  value={travelValue.from}
                  onChange={(event) => setTravel({ ...travelValue, from: event.target.value })}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="travel-until">{messages["users.travelUntil"]}</FieldLabel>
                <Input
                  id="travel-until"
                  type="date"
                  value={travelValue.until}
                  onChange={(event) => setTravel({ ...travelValue, until: event.target.value })}
                />
              </Field>
              <Button size="sm" onClick={() => void saveTravel(travelValue.from, travelValue.until)}>
                {messages["users.travelSave"]}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => void saveTravel("", "")}>
                {messages["users.travelClear"]}
              </Button>
            </div>
          </FieldGroup>
          {alerts}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2>{messages["users.offboardTitle"]}</h2>
          </CardTitle>
          <CardDescription>{messages["users.offboardDescription"]}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <h3>{messages["users.owned"]}</h3>
          {records.length ? (
            <ul className="flex flex-col gap-1" aria-label={messages["users.owned"]}>
              {records.map((record) => (
                <li key={`${record.type}-${record.id}`}>
                  {record.type}: {record.label}
                </li>
              ))}
            </ul>
          ) : (
            <p>{messages["users.nothingOwned"]}</p>
          )}
          {preview.data?.needs_new_owner ? (
            <Field>
              <FieldLabel htmlFor="new-owner">{messages["users.newOwner"]}</FieldLabel>
              <Select value={newOwner === null ? "" : String(newOwner)} onValueChange={(value) => setNewOwner(Number(value))}>
                <SelectTrigger id="new-owner">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {candidates.map((candidate) => (
                    <SelectItem key={candidate.id} value={String(candidate.id)}>
                      {candidate.name} ({candidate.role_name})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {preview.data.new_owner_must_be_partner ? <p>{messages["users.newOwnerPartner"]}</p> : null}
            </Field>
          ) : null}
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" className="self-start" disabled={!canConfirm(preview.data, newOwner)}>
                {messages["users.offboard"]}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>{messages["users.offboardTitle"]}</AlertDialogTitle>
                <AlertDialogDescription>{messages["users.offboardDescription"]}</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>{messages["login.retry"]}</AlertDialogCancel>
                <AlertDialogAction onClick={() => void deactivate()}>{messages["users.confirmDeactivate"]}</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </CardContent>
      </Card>
    </div>
  );
}
