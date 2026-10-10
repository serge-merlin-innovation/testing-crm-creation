"use client";

import { useState, type FormEvent } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { fieldErrors, readDetail, type Mandate } from "@/lib/deals";
import type { MessageKey } from "@/lib/i18n/messages";
import type { Milestone } from "@/lib/pipeline";
import { sendJson, useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;

export function MilestonesTab({ mandate, messages }: { mandate: Mandate; messages: Messages }) {
  const path = `/api/v1/mandates/${mandate.id}/milestones`;
  const milestones = useApiData<Milestone[]>(path);
  const [name, setName] = useState("");
  const [planned, setPlanned] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    const result = await sendJson(path, "POST", { name, planned_date: planned });
    if (result.status === 201) {
      setName("");
      setPlanned("");
      await milestones.reload();
      return;
    }
    const inline = fieldErrors(result.body);
    setErrors(Object.keys(inline).length ? inline : { form: readDetail(result.body, messages["common.saveFailed"]) });
  }

  async function setActual(milestone: Milestone, value: string) {
    await sendJson(`${path}/${milestone.id}`, "PATCH", { actual_date: value || null });
    await milestones.reload();
  }

  return (
    <div className="flex flex-col gap-4">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{messages["milestones.name"]}</TableHead>
            <TableHead>{messages["milestones.planned"]}</TableHead>
            <TableHead>{messages["milestones.actual"]}</TableHead>
            <TableHead>{messages["milestones.status"]}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {(milestones.data ?? []).map((milestone) => (
            <TableRow key={milestone.id} data-late={milestone.late}>
              <TableCell>{milestone.name}</TableCell>
              <TableCell>{milestone.planned_date}</TableCell>
              <TableCell>
                {mandate.can_edit ? (
                  <Input
                    type="date"
                    aria-label={`${messages["milestones.actual"]} ${milestone.name}`}
                    defaultValue={milestone.actual_date ?? ""}
                    onBlur={(event) => void setActual(milestone, event.target.value)}
                  />
                ) : (
                  (milestone.actual_date ?? "")
                )}
              </TableCell>
              <TableCell>
                {milestone.late ? (
                  <Badge variant="destructive">
                    {milestone.days_late} {messages["milestones.daysLate"]}
                  </Badge>
                ) : (
                  <Badge variant="secondary">{messages["milestones.onTime"]}</Badge>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {mandate.can_edit ? (
        <form onSubmit={(event) => void add(event)}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="milestone-name">{messages["milestones.name"]}</FieldLabel>
              <Input id="milestone-name" value={name} onChange={(event) => setName(event.target.value)} required />
              <FieldError>{errors.name}</FieldError>
            </Field>
            <Field>
              <FieldLabel htmlFor="milestone-planned">{messages["milestones.planned"]}</FieldLabel>
              <Input
                id="milestone-planned"
                type="date"
                value={planned}
                onChange={(event) => setPlanned(event.target.value)}
                required
              />
              <FieldError>{errors.planned_date}</FieldError>
            </Field>
            {errors.form ? (
              <Alert variant="destructive">
                <AlertDescription>{errors.form}</AlertDescription>
              </Alert>
            ) : null}
            <Button type="submit">{messages["milestones.add"]}</Button>
          </FieldGroup>
        </form>
      ) : null}
    </div>
  );
}

export function ClosingTab({
  mandate,
  onSaved,
  messages,
}: {
  mandate: Mandate;
  onSaved: (mandate: Mandate) => void;
  messages: Messages;
}) {
  const [outcome, setOutcome] = useState("closed_won");
  const [finalEv, setFinalEv] = useState("");
  const [buyer, setBuyer] = useState("");
  const [multiple, setMultiple] = useState("");
  const [closingDate, setClosingDate] = useState("");
  const [tombstone, setTombstone] = useState<string>("");
  const [abortReason, setAbortReason] = useState("");
  const [reopenReason, setReopenReason] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function submit(path: string, body: Record<string, unknown>) {
    setErrors({});
    const result = await sendJson(path, "POST", { version: mandate.version, ...body });
    if (result.status === 200) {
      onSaved(result.body as Mandate);
      return;
    }
    const inline = fieldErrors(result.body);
    setErrors(Object.keys(inline).length ? inline : { form: readDetail(result.body, messages["common.saveFailed"]) });
  }

  function close(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const body: Record<string, unknown> = { outcome };
    if (outcome === "closed_won") {
      if (finalEv) body.final_ev = finalEv;
      if (buyer) body.buyer = buyer;
      if (multiple) body.ev_ebitda = multiple;
      if (closingDate) body.closing_date = closingDate;
      if (tombstone) body.tombstone_allowed = tombstone === "yes";
    } else {
      body.abort_reason = abortReason;
    }
    void submit(`/api/v1/mandates/${mandate.id}/close`, body);
  }

  const formError = errors.form ? (
    <Alert variant="destructive">
      <AlertDescription>{errors.form}</AlertDescription>
    </Alert>
  ) : null;

  if (mandate.closed_at) {
    const o = mandate.outcome;
    return (
      <div className="flex flex-col gap-4">
        <Alert>
          <AlertDescription>{messages["closing.readOnly"]}</AlertDescription>
        </Alert>
        <Table>
          <TableBody>
            {mandate.stage === "aborted" ? (
              <TableRow>
                <TableHead>{messages["closing.abortReason"]}</TableHead>
                <TableCell>{o.abort_reason}</TableCell>
              </TableRow>
            ) : (
              <>
                <TableRow>
                  <TableHead>{messages["closing.finalEv"]}</TableHead>
                  <TableCell>{o.final_ev}</TableCell>
                </TableRow>
                <TableRow>
                  <TableHead>{messages["closing.buyer"]}</TableHead>
                  <TableCell>{o.buyer}</TableCell>
                </TableRow>
                <TableRow>
                  <TableHead>{messages["closing.multiple"]}</TableHead>
                  <TableCell>{o.ev_ebitda}</TableCell>
                </TableRow>
                <TableRow>
                  <TableHead>{messages["closing.date"]}</TableHead>
                  <TableCell>{o.closing_date}</TableCell>
                </TableRow>
                <TableRow>
                  <TableHead>{messages["closing.tombstone"]}</TableHead>
                  <TableCell>{o.tombstone_allowed ? messages["closing.yes"] : messages["closing.no"]}</TableCell>
                </TableRow>
              </>
            )}
          </TableBody>
        </Table>
        {mandate.can_reopen ? (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void submit(`/api/v1/mandates/${mandate.id}/reopen`, { reason: reopenReason });
            }}
          >
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="reopen-reason">{messages["closing.reopenReason"]}</FieldLabel>
                <Textarea id="reopen-reason" value={reopenReason} onChange={(event) => setReopenReason(event.target.value)} />
                <FieldError>{errors.reason}</FieldError>
              </Field>
              {formError}
              <Button type="submit" variant="outline">
                {messages["closing.reopen"]}
              </Button>
            </FieldGroup>
          </form>
        ) : null}
      </div>
    );
  }

  if (!mandate.can_close) {
    return <p>{messages["closing.partnersOnly"]}</p>;
  }

  return (
    <form onSubmit={close}>
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="close-outcome">{messages["closing.outcome"]}</FieldLabel>
          <Select value={outcome} onValueChange={setOutcome}>
            <SelectTrigger id="close-outcome">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="closed_won">{messages["closing.won"]}</SelectItem>
              <SelectItem value="aborted">{messages["closing.aborted"]}</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        {outcome === "closed_won" ? (
          <>
            <Field>
              <FieldLabel htmlFor="close-ev">{messages["closing.finalEv"]}</FieldLabel>
              <Input id="close-ev" inputMode="decimal" value={finalEv} onChange={(event) => setFinalEv(event.target.value)} />
              <FieldError>{errors.final_ev}</FieldError>
            </Field>
            <Field>
              <FieldLabel htmlFor="close-buyer">{messages["closing.buyer"]}</FieldLabel>
              <Input id="close-buyer" value={buyer} onChange={(event) => setBuyer(event.target.value)} />
              <FieldError>{errors.buyer}</FieldError>
            </Field>
            <Field>
              <FieldLabel htmlFor="close-multiple">{messages["closing.multiple"]}</FieldLabel>
              <Input
                id="close-multiple"
                inputMode="decimal"
                value={multiple}
                onChange={(event) => setMultiple(event.target.value)}
              />
              <FieldError>{errors.ev_ebitda}</FieldError>
            </Field>
            <Field>
              <FieldLabel htmlFor="close-date">{messages["closing.date"]}</FieldLabel>
              <Input id="close-date" type="date" value={closingDate} onChange={(event) => setClosingDate(event.target.value)} />
              <FieldError>{errors.closing_date}</FieldError>
            </Field>
            <Field>
              <FieldLabel htmlFor="close-tombstone">{messages["closing.tombstone"]}</FieldLabel>
              <Select value={tombstone} onValueChange={setTombstone}>
                <SelectTrigger id="close-tombstone" aria-invalid={Boolean(errors.tombstone_allowed)}>
                  <SelectValue placeholder={messages["closing.choose"]} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="yes">{messages["closing.yes"]}</SelectItem>
                  <SelectItem value="no">{messages["closing.no"]}</SelectItem>
                </SelectContent>
              </Select>
              <FieldError>{errors.tombstone_allowed}</FieldError>
            </Field>
          </>
        ) : (
          <Field>
            <FieldLabel htmlFor="close-abort-reason">{messages["closing.abortReason"]}</FieldLabel>
            <Textarea id="close-abort-reason" value={abortReason} onChange={(event) => setAbortReason(event.target.value)} />
            <FieldError>{errors.abort_reason}</FieldError>
          </Field>
        )}
        {formError}
        <Button type="submit" variant="destructive">
          {messages["closing.confirm"]}
        </Button>
      </FieldGroup>
    </form>
  );
}
