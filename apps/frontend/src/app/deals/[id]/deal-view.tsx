"use client";

import { useState, type FormEvent } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  documentLinkProps,
  fieldErrors,
  historyRows,
  isHttpsUrl,
  readDetail,
  readStaleConflict,
  TEAM_ROLES,
  type HistoryEntry,
  type Mandate,
} from "@/lib/deals";
import type { MessageKey } from "@/lib/i18n/messages";
import { stageLabel } from "@/lib/pipeline";
import { sendJson, useApiData } from "@/lib/use-api";
import { ClosingTab, MilestonesTab } from "./pipeline-tabs";

type Messages = Record<MessageKey, string>;
type Member = {
  user_id: number;
  name: string;
  email: string;
  role: string;
  added_by_name: string;
  added_at: string;
  expires_at: string | null;
};
type Team = { can_manage: boolean; members: Member[] };
type Candidate = { id: number; name: string; email: string; role_name: string | null };
type Link = { id: number; label: string; url: string };
type Crossing = { action: string; user_name: string; by_user_name: string; role: string; at: string };

function Summary({ mandate, onSaved, messages }: { mandate: Mandate; onSaved: (m: Mandate) => void; messages: Messages }) {
  const [codeName, setCodeName] = useState(mandate.code_name);
  const [ev, setEv] = useState(mandate.estimated_ev);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [conflict, setConflict] = useState<{ message: string; current: Mandate } | null>(null);
  const [saving, setSaving] = useState(false);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    setSaving(true);
    const result = await sendJson(`/api/v1/mandates/${mandate.id}`, "PATCH", {
      version: mandate.version,
      code_name: codeName,
      estimated_ev: ev,
    });
    setSaving(false);
    if (result.status === 200) {
      setConflict(null);
      onSaved(result.body as Mandate);
      return;
    }
    const stale = readStaleConflict(result.status, result.body);
    if (stale) {
      setConflict({ message: stale.message, current: stale.current as unknown as Mandate });
      return;
    }
    const inline = fieldErrors(result.body);
    setErrors(Object.keys(inline).length ? inline : { form: readDetail(result.body, messages["common.saveFailed"]) });
  }

  function useNewer() {
    if (!conflict) return;
    onSaved(conflict.current);
    setCodeName(conflict.current.code_name);
    setEv(conflict.current.estimated_ev);
    setConflict(null);
  }

  return (
    <div className="flex flex-col gap-4">
      <Table>
        <TableBody>
          <TableRow>
            <TableHead>{messages["deals.client"]}</TableHead>
            <TableCell>{mandate.client_name}</TableCell>
          </TableRow>
          <TableRow>
            <TableHead>{messages["deals.target"]}</TableHead>
            <TableCell>{mandate.target_name ?? messages["deals.none"]}</TableCell>
          </TableRow>
          <TableRow>
            <TableHead>{messages["deals.type"]}</TableHead>
            <TableCell>{mandate.type}</TableCell>
          </TableRow>
          <TableRow>
            <TableHead>{messages["deals.stage"]}</TableHead>
            <TableCell>
              <Badge variant="secondary">{stageLabel(mandate.stage)}</Badge>
            </TableCell>
          </TableRow>
          <TableRow>
            <TableHead>{messages["deals.leadPartner"]}</TableHead>
            <TableCell>{mandate.lead_partner_name}</TableCell>
          </TableRow>
        </TableBody>
      </Table>

      {conflict ? (
        <Alert variant="destructive">
          <AlertTitle>{messages["deals.conflictTitle"]}</AlertTitle>
          <AlertDescription className="flex flex-col gap-2">
            <p>{conflict.message}</p>
            <p>
              {messages["deals.codeName"]}: {conflict.current.code_name}. {messages["deals.ev"]}:{" "}
              {conflict.current.estimated_ev}
            </p>
            <Button type="button" variant="outline" onClick={useNewer}>
              {messages["deals.useNewer"]}
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      {mandate.can_edit ? (
        <form onSubmit={(event) => void save(event)}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="edit-code-name">{messages["deals.codeName"]}</FieldLabel>
              <Input id="edit-code-name" value={codeName} onChange={(event) => setCodeName(event.target.value)} />
              <FieldError>{errors.code_name}</FieldError>
            </Field>
            <Field>
              <FieldLabel htmlFor="edit-ev">{messages["deals.ev"]}</FieldLabel>
              <Input id="edit-ev" inputMode="decimal" value={ev} onChange={(event) => setEv(event.target.value)} />
              <FieldError>{errors.estimated_ev}</FieldError>
            </Field>
            {errors.form ? (
              <Alert variant="destructive">
                <AlertDescription>{errors.form}</AlertDescription>
              </Alert>
            ) : null}
            <Button type="submit" disabled={saving}>
              {saving ? messages["common.saving"] : messages["common.save"]}
            </Button>
          </FieldGroup>
        </form>
      ) : null}
    </div>
  );
}

function TeamTab({ mandateId, messages }: { mandateId: number; messages: Messages }) {
  const team = useApiData<Team>(`/api/v1/mandates/${mandateId}/team`);
  const canManage = team.data?.can_manage ?? false;
  const candidates = useApiData<Candidate[]>(canManage ? `/api/v1/mandates/${mandateId}/team/candidates` : null);
  const crossings = useApiData<Crossing[]>(`/api/v1/mandates/${mandateId}/wall-crossings`);
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState("analyst");
  const [expires, setExpires] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    await Promise.all([team.reload(), candidates.reload(), crossings.reload()]);
  }

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const result = await sendJson(`/api/v1/mandates/${mandateId}/team`, "POST", {
      user_id: Number(userId),
      role,
      expires_at: expires ? new Date(`${expires}T23:59:59`).toISOString() : null,
    });
    if (result.status !== 201) {
      setError(readDetail(result.body, messages["common.saveFailed"]));
      return;
    }
    setUserId("");
    await refresh();
  }

  async function remove(member: Member) {
    setError("");
    const result = await sendJson(`/api/v1/mandates/${mandateId}/team/${member.user_id}`, "DELETE");
    if (result.status !== 204) {
      setError(readDetail(result.body, messages["common.saveFailed"]));
    }
    await refresh();
  }

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{messages["common.name"]}</TableHead>
              <TableHead>{messages["deals.role"]}</TableHead>
              <TableHead>{messages["deals.addedBy"]}</TableHead>
              <TableHead>{messages["deals.addedAt"]}</TableHead>
              <TableHead>{messages["deals.expires"]}</TableHead>
              {canManage ? <TableHead /> : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {(team.data?.members ?? []).map((member) => (
              <TableRow key={member.user_id}>
                <TableCell>{member.name}</TableCell>
                <TableCell>{member.role}</TableCell>
                <TableCell>{member.added_by_name}</TableCell>
                <TableCell>{new Date(member.added_at).toLocaleString()}</TableCell>
                <TableCell>{member.expires_at ? new Date(member.expires_at).toLocaleDateString() : ""}</TableCell>
                {canManage ? (
                  <TableCell>
                    <Button size="sm" variant="outline" onClick={() => void remove(member)}>
                      {messages["common.remove"]}
                    </Button>
                  </TableCell>
                ) : null}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {canManage ? (
        <form onSubmit={(event) => void add(event)}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="team-user">{messages["deals.member"]}</FieldLabel>
              <Select value={userId} onValueChange={setUserId}>
                <SelectTrigger id="team-user">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(candidates.data ?? []).map((candidate) => (
                    <SelectItem key={candidate.id} value={String(candidate.id)}>
                      {candidate.name} ({candidate.role_name})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field>
              <FieldLabel htmlFor="team-role">{messages["deals.role"]}</FieldLabel>
              <Select value={role} onValueChange={setRole}>
                <SelectTrigger id="team-role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TEAM_ROLES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {value}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field>
              <FieldLabel htmlFor="team-expires">{messages["deals.expires"]}</FieldLabel>
              <Input id="team-expires" type="date" value={expires} onChange={(event) => setExpires(event.target.value)} />
            </Field>
            <Button type="submit" disabled={!userId}>
              {messages["deals.addMember"]}
            </Button>
          </FieldGroup>
        </form>
      ) : null}

      <h3>{messages["deals.wallCrossings"]}</h3>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{messages["deals.when"]}</TableHead>
              <TableHead>{messages["deals.action"]}</TableHead>
              <TableHead>{messages["deals.who"]}</TableHead>
              <TableHead>{messages["deals.addedBy"]}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(crossings.data ?? []).map((crossing, index) => (
              <TableRow key={index}>
                <TableCell>{new Date(crossing.at).toLocaleString()}</TableCell>
                <TableCell>{crossing.action}</TableCell>
                <TableCell>{crossing.user_name}</TableCell>
                <TableCell>{crossing.by_user_name}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function HistoryTab({ mandateId, version, messages }: { mandateId: number; version: number; messages: Messages }) {
  const history = useApiData<HistoryEntry[]>(`/api/v1/mandates/${mandateId}/history?v=${version}`);

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{messages["deals.when"]}</TableHead>
            <TableHead>{messages["deals.who"]}</TableHead>
            <TableHead>{messages["deals.field"]}</TableHead>
            <TableHead>{messages["deals.old"]}</TableHead>
            <TableHead>{messages["deals.newValue"]}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {historyRows(history.data ?? []).map((row, index) => (
            <TableRow key={index}>
              <TableCell>{new Date(row.when).toLocaleString()}</TableCell>
              <TableCell>{row.who}</TableCell>
              <TableCell>{row.what}</TableCell>
              <TableCell>{row.old}</TableCell>
              <TableCell>{row.new}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function LinksTab({ mandateId, canEdit, messages }: { mandateId: number; canEdit: boolean; messages: Messages }) {
  const links = useApiData<Link[]>(`/api/v1/mandates/${mandateId}/links`);
  const [label, setLabel] = useState("");
  const [url, setUrl] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isHttpsUrl(url)) {
      setErrors({ url: messages["deals.httpsOnly"] });
      return;
    }
    const result = await sendJson(`/api/v1/mandates/${mandateId}/links`, "POST", { label, url });
    if (result.status !== 201) {
      const inline = fieldErrors(result.body);
      setErrors(Object.keys(inline).length ? inline : { form: readDetail(result.body, messages["common.saveFailed"]) });
      return;
    }
    setErrors({});
    setLabel("");
    setUrl("");
    await links.reload();
  }

  async function remove(link: Link) {
    await sendJson(`/api/v1/mandates/${mandateId}/links/${link.id}`, "DELETE");
    await links.reload();
  }

  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-col gap-2">
        {(links.data ?? []).map((link) => {
          const props = documentLinkProps(link.url);
          return (
            <li key={link.id} className="flex items-center gap-2">
              <Badge variant="outline">{link.label}</Badge>
              {props ? (
                <Button asChild variant="link">
                  <a {...props}>{link.url}</a>
                </Button>
              ) : null}
              {canEdit ? (
                <Button size="sm" variant="ghost" onClick={() => void remove(link)}>
                  {messages["common.remove"]}
                </Button>
              ) : null}
            </li>
          );
        })}
      </ul>
      {canEdit ? (
        <form onSubmit={(event) => void add(event)}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="link-label">{messages["deals.linkLabel"]}</FieldLabel>
              <Input id="link-label" value={label} onChange={(event) => setLabel(event.target.value)} required />
              <FieldError>{errors.label}</FieldError>
            </Field>
            <Field>
              <FieldLabel htmlFor="link-url">{messages["deals.linkUrl"]}</FieldLabel>
              <Input
                id="link-url"
                type="url"
                placeholder="https://"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                required
              />
              <FieldError>{errors.url}</FieldError>
            </Field>
            {errors.form ? (
              <Alert variant="destructive">
                <AlertDescription>{errors.form}</AlertDescription>
              </Alert>
            ) : null}
            <Button type="submit">{messages["deals.addLink"]}</Button>
          </FieldGroup>
        </form>
      ) : null}
    </div>
  );
}

export function DealView({ initial, messages }: { initial: Mandate; messages: Messages }) {
  const [mandate, setMandate] = useState(initial);

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h1>{mandate.code_name}</h1>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="summary">
          <TabsList>
            <TabsTrigger value="summary">{messages["deals.summary"]}</TabsTrigger>
            <TabsTrigger value="team">{messages["deals.team"]}</TabsTrigger>
            <TabsTrigger value="links">{messages["deals.links"]}</TabsTrigger>
            <TabsTrigger value="milestones">{messages["milestones.title"]}</TabsTrigger>
            <TabsTrigger value="closing">{messages["closing.title"]}</TabsTrigger>
            <TabsTrigger value="history">{messages["deals.history"]}</TabsTrigger>
          </TabsList>
          <TabsContent value="summary">
            <Summary mandate={mandate} onSaved={setMandate} messages={messages} />
          </TabsContent>
          <TabsContent value="team">
            <TeamTab mandateId={mandate.id} messages={messages} />
          </TabsContent>
          <TabsContent value="links">
            <LinksTab mandateId={mandate.id} canEdit={mandate.can_edit} messages={messages} />
          </TabsContent>
          <TabsContent value="milestones">
            <MilestonesTab key={mandate.version} mandate={mandate} messages={messages} />
          </TabsContent>
          <TabsContent value="closing">
            <ClosingTab key={mandate.version} mandate={mandate} onSaved={setMandate} messages={messages} />
          </TabsContent>
          <TabsContent value="history">
            <HistoryTab mandateId={mandate.id} version={mandate.version} messages={messages} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
