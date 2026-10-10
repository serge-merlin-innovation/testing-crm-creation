"use client";

import { useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  APPROVAL_LABEL,
  blockedReason,
  BUYER_STATUSES,
  DECLINE_LABEL,
  DECLINE_REASONS,
  SETTABLE_STATUSES,
  STATUS_LABEL,
  toggle,
  type AddResult,
  type Approval,
  type Buyer,
  type BuyerGrid,
  type BuyerStatus,
  type DeclineReason,
  type Suggestion,
} from "@/lib/buyers";
import { fillTemplate } from "@/lib/compliance";
import { documentLinkProps, fieldErrors, readDetail, type Mandate } from "@/lib/deals";
import type { MessageKey } from "@/lib/i18n/messages";
import { sendJson, useApiData } from "@/lib/use-api";
import { apiFetch } from "@/services/api";

type Messages = Record<MessageKey, string>;
type Team = { members: { user_id: number; name: string }[] };

function SuggestPanel({
  mandate,
  team,
  onAdded,
  messages,
}: {
  mandate: Mandate;
  team: Team | null;
  onAdded: () => Promise<void>;
  messages: Messages;
}) {
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [ownerId, setOwnerId] = useState("");
  const [rationale, setRationale] = useState("");
  const [result, setResult] = useState<AddResult | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function suggest() {
    const response = await apiFetch(`/api/v1/mandates/${mandate.id}/buyers/suggestions`).catch(() => null);
    const rows = response?.ok ? ((await response.json()) as Suggestion[]) : [];
    setSuggestions(rows);
    setSelected([]);
    setResult(null);
  }

  async function add(confirm: boolean) {
    setErrors({});
    const items = selected.map((company_id) => ({ company_id, owner_id: Number(ownerId) || 0, rationale }));
    const response = await sendJson(`/api/v1/mandates/${mandate.id}/buyers`, "POST", { items, confirm });
    if (response.status !== 200) {
      const inline = fieldErrors(response.body);
      const flat = Object.fromEntries(Object.entries(inline).map(([key, value]) => [key.split(".").pop() ?? key, value]));
      setErrors(Object.keys(flat).length ? flat : { form: readDetail(response.body, messages["common.saveFailed"]) });
      return;
    }
    const body = response.body as AddResult;
    setResult(body);
    await onAdded();
  }

  const blockedByWarnings = result !== null && result.warnings.length > 0 && result.added.length === 0;

  return (
    <section className="flex flex-col gap-3" aria-label={messages["buyers.suggest"]}>
      <div className="flex gap-2">
        <Button type="button" variant="outline" onClick={() => void suggest()}>
          {messages["buyers.suggest"]}
        </Button>
      </div>
      {suggestions?.length === 0 ? <p>{messages["buyers.noSuggestions"]}</p> : null}
      {suggestions && suggestions.length > 0 ? (
        <>
          <Table aria-label={messages["buyers.suggest"]}>
            <TableHeader>
              <TableRow>
                <TableHead />
                <TableHead>{messages["buyers.company"]}</TableHead>
                <TableHead>{messages["buyers.score"]}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {suggestions.map((row) => (
                <TableRow key={row.company_id}>
                  <TableCell>
                    <Checkbox
                      aria-label={fillTemplate(messages["buyers.select"], { name: row.name })}
                      checked={selected.includes(row.company_id)}
                      onCheckedChange={() => setSelected(toggle(selected, row.company_id))}
                    />
                  </TableCell>
                  <TableCell>{row.name}</TableCell>
                  <TableCell>{row.matched.join(", ")}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="buyer-owner">{messages["buyers.owner"]}</FieldLabel>
              <Select value={ownerId} onValueChange={setOwnerId}>
                <SelectTrigger id="buyer-owner">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(team?.members ?? []).map((member) => (
                    <SelectItem key={member.user_id} value={String(member.user_id)}>
                      {member.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FieldError>{errors.owner_id}</FieldError>
            </Field>
            <Field>
              <FieldLabel htmlFor="buyer-rationale">{messages["buyers.rationale"]}</FieldLabel>
              <Input id="buyer-rationale" value={rationale} onChange={(event) => setRationale(event.target.value)} />
              <FieldError>{errors.rationale}</FieldError>
            </Field>
            {errors.form ? (
              <Alert variant="destructive">
                <AlertDescription>{errors.form}</AlertDescription>
              </Alert>
            ) : null}
            <div className="flex gap-2">
              <Button type="button" disabled={selected.length === 0} onClick={() => void add(false)}>
                {messages["buyers.addSelected"]}
              </Button>
              {blockedByWarnings ? (
                <Button type="button" variant="destructive" onClick={() => void add(true)}>
                  {messages["buyers.addAnyway"]}
                </Button>
              ) : null}
            </div>
          </FieldGroup>
        </>
      ) : null}
      {result ? (
        <Alert variant={result.warnings.length ? "destructive" : "default"}>
          <AlertDescription>
            <p role="status">
              {fillTemplate(messages["buyers.added"], {
                added: String(result.added.length),
                skipped: String(result.skipped.length),
              })}
            </p>
            {result.warnings.map((warning) => (
              <p key={`${warning.company_id}-${warning.reason}`}>
                {fillTemplate(messages[`buyers.warning.${warning.reason}`], { name: warning.name })}
              </p>
            ))}
          </AlertDescription>
        </Alert>
      ) : null}
    </section>
  );
}

const NDA_FIELDS = [
  ["sent_date", "buyers.nda.sent"],
  ["markup_received_date", "buyers.nda.markup"],
  ["agreed_date", "buyers.nda.agreed"],
  ["signed_date", "buyers.nda.signed"],
  ["standstill_end", "buyers.nda.standstill"],
  ["non_solicit_end", "buyers.nda.nonSolicit"],
] as const;

function NdaForm({
  mandateId,
  buyer,
  onSaved,
  messages,
}: {
  mandateId: number;
  buyer: Buyer;
  onSaved: () => Promise<void>;
  messages: Messages;
}) {
  const initial = Object.fromEntries(
    [...NDA_FIELDS.map(([key]) => key), "document_url"].map((key) => [
      key,
      (buyer.nda?.[key as keyof NonNullable<Buyer["nda"]>] as string | null) ?? "",
    ]),
  );
  const [values, setValues] = useState<Record<string, string>>(initial);
  const [error, setError] = useState("");

  async function save() {
    setError("");
    const body = Object.fromEntries(Object.entries(values).map(([key, value]) => [key, value || null]));
    const response = await sendJson(`/api/v1/mandates/${mandateId}/buyers/${buyer.id}/nda`, "PUT", body);
    if (response.status !== 200) {
      setError(readDetail(response.body, messages["common.saveFailed"]));
      return;
    }
    await onSaved();
  }

  return (
    <FieldGroup aria-label={`${messages["buyers.nda"]} ${buyer.name}`}>
      <div className="grid gap-2 md:grid-cols-3">
        {NDA_FIELDS.map(([key, label]) => (
          <Field key={key}>
            <FieldLabel htmlFor={`nda-${buyer.id}-${key}`}>{messages[label]}</FieldLabel>
            <Input
              id={`nda-${buyer.id}-${key}`}
              type="date"
              value={values[key]}
              onChange={(event) => setValues({ ...values, [key]: event.target.value })}
            />
          </Field>
        ))}
        <Field>
          <FieldLabel htmlFor={`nda-${buyer.id}-link`}>{messages["buyers.nda.link"]}</FieldLabel>
          <Input
            id={`nda-${buyer.id}-link`}
            value={values.document_url}
            onChange={(event) => setValues({ ...values, document_url: event.target.value })}
          />
        </Field>
      </div>
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <div>
        <Button type="button" variant="outline" onClick={() => void save()}>
          {messages["buyers.nda.save"]}
        </Button>
      </div>
    </FieldGroup>
  );
}

export function BuyersTab({ mandate, messages }: { mandate: Mandate; messages: Messages }) {
  const grid = useApiData<BuyerGrid>(`/api/v1/mandates/${mandate.id}/buyers`);
  const team = useApiData<Team>(`/api/v1/mandates/${mandate.id}/team`);
  const [selected, setSelected] = useState<number[]>([]);
  const [status, setStatus] = useState<BuyerStatus>("contacted");
  const [reason, setReason] = useState<DeclineReason | "">("");
  const [error, setError] = useState("");
  const [ndaFor, setNdaFor] = useState<number | null>(null);

  const buyers = grid.data?.buyers ?? [];
  const localBlock = buyers
    .filter((buyer) => selected.includes(buyer.id))
    .map((buyer) => blockedReason(buyer, status))
    .find((reasonKey) => reasonKey !== null);

  async function apply() {
    setError("");
    const response = await sendJson(`/api/v1/mandates/${mandate.id}/buyers/status`, "POST", {
      buyer_ids: selected,
      status,
      decline_reason: status === "declined" ? reason || null : null,
    });
    if (response.status !== 200) {
      setError(readDetail(response.body, messages["common.saveFailed"]));
      return;
    }
    setSelected([]);
    await grid.reload();
  }

  async function setApproval(buyer: Buyer, approval: Approval) {
    setError("");
    const response = await sendJson(`/api/v1/mandates/${mandate.id}/buyers/${buyer.id}`, "PATCH", { approval });
    if (response.status !== 200) {
      setError(readDetail(response.body, messages["common.saveFailed"]));
      return;
    }
    await grid.reload();
  }

  return (
    <div className="flex flex-col gap-4">
      {grid.data ? (
        <section aria-label={messages["buyers.funnel"]} className="flex flex-wrap gap-2">
          {BUYER_STATUSES.map((key) => (
            <Badge key={key} variant="secondary" data-funnel={key}>
              {messages[STATUS_LABEL[key]]}: {grid.data?.funnel[key] ?? 0}
            </Badge>
          ))}
        </section>
      ) : null}
      {mandate.can_edit ? (
        <SuggestPanel mandate={mandate} team={team.data} onAdded={grid.reload} messages={messages} />
      ) : null}
      <Separator />
      <div className="flex gap-2">
        <Button asChild variant="outline">
          <a href={`/api/v1/mandates/${mandate.id}/buyers/export`} download>
            {messages["buyers.export"]}
          </a>
        </Button>
      </div>
      {buyers.length === 0 ? <p>{messages["buyers.empty"]}</p> : null}
      {buyers.length > 0 ? (
        <div className="overflow-x-auto" tabIndex={0}>
          <Table aria-label={messages["buyers.title"]}>
            <TableHeader>
              <TableRow>
                <TableHead />
                <TableHead>{messages["buyers.company"]}</TableHead>
                <TableHead>{messages["buyers.owner"]}</TableHead>
                <TableHead>{messages["buyers.approval"]}</TableHead>
                <TableHead>{messages["buyers.statusCol"]}</TableHead>
                <TableHead>{messages["buyers.nda"]}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {buyers.map((buyer) => {
                const link = buyer.nda?.document_url ? documentLinkProps(buyer.nda.document_url) : null;
                return (
                  <TableRow key={buyer.id} data-buyer={buyer.name}>
                    <TableCell>
                      <Checkbox
                        aria-label={fillTemplate(messages["buyers.select"], { name: buyer.name })}
                        checked={selected.includes(buyer.id)}
                        onCheckedChange={() => setSelected(toggle(selected, buyer.id))}
                      />
                    </TableCell>
                    <TableCell>
                      <p>{buyer.name}</p>
                      <p className="text-muted-foreground text-sm">{buyer.rationale}</p>
                    </TableCell>
                    <TableCell>{buyer.owner_name}</TableCell>
                    <TableCell>
                      {grid.data?.can_approve && mandate.can_edit ? (
                        <Select value={buyer.approval} onValueChange={(value) => void setApproval(buyer, value as Approval)}>
                          <SelectTrigger aria-label={`${messages["buyers.approval"]} ${buyer.name}`}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {(Object.keys(APPROVAL_LABEL) as Approval[]).map((value) => (
                              <SelectItem key={value} value={value}>
                                {messages[APPROVAL_LABEL[value]]}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        messages[APPROVAL_LABEL[buyer.approval]]
                      )}
                    </TableCell>
                    <TableCell data-status={buyer.status}>
                      <p>
                        {messages[STATUS_LABEL[buyer.status]]}
                        {buyer.decline_reason ? ` (${messages[DECLINE_LABEL[buyer.decline_reason]]})` : ""}
                      </p>
                      <p className="text-muted-foreground text-sm">
                        {fillTemplate(messages["buyers.changed"], {
                          date: buyer.status_changed_at.slice(0, 10),
                          name: buyer.status_changed_by_name,
                        })}
                      </p>
                    </TableCell>
                    <TableCell>
                      {link ? (
                        <a {...link} className="underline">
                          {messages["buyers.nda.link"]}
                        </a>
                      ) : null}
                      {mandate.can_edit && buyer.approval === "approved" ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => setNdaFor(ndaFor === buyer.id ? null : buyer.id)}
                        >
                          {messages["buyers.nda"]}
                        </Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      ) : null}
      {ndaFor !== null && buyers.find((buyer) => buyer.id === ndaFor) ? (
        <NdaForm
          key={ndaFor}
          mandateId={mandate.id}
          buyer={buyers.find((buyer) => buyer.id === ndaFor) as Buyer}
          onSaved={grid.reload}
          messages={messages}
        />
      ) : null}
      {mandate.can_edit && buyers.length > 0 ? (
        <FieldGroup>
          <div className="flex flex-wrap items-end gap-2">
            <Field>
              <FieldLabel htmlFor="buyer-status">{messages["buyers.newStatus"]}</FieldLabel>
              <Select value={status} onValueChange={(value) => setStatus(value as BuyerStatus)}>
                <SelectTrigger id="buyer-status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SETTABLE_STATUSES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {messages[STATUS_LABEL[value]]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            {status === "declined" ? (
              <Field>
                <FieldLabel htmlFor="buyer-decline">{messages["buyers.declineReason"]}</FieldLabel>
                <Select value={reason} onValueChange={(value) => setReason(value as DeclineReason)}>
                  <SelectTrigger id="buyer-decline">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DECLINE_REASONS.map((value) => (
                      <SelectItem key={value} value={value}>
                        {messages[DECLINE_LABEL[value]]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
            ) : null}
            <Button type="button" disabled={selected.length === 0} onClick={() => void apply()}>
              {messages["buyers.apply"]}
            </Button>
          </div>
          {localBlock ? <p className="text-muted-foreground text-sm">{messages[localBlock]}</p> : null}
        </FieldGroup>
      ) : null}
      {error ? (
        <Alert variant="destructive" data-grid-error>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}
