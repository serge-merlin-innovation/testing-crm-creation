"use client";

import { ScrollRegion } from "@/components/scroll-region";
import { useState, type FormEvent } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import {
  CONFLICT_STATUS_LABEL,
  fillTemplate,
  KYC_STATUS_LABEL,
  kycOutcome,
  type ConflictHit,
  type ConflictStatus,
  type Kyc,
} from "@/lib/compliance";
import { fieldErrors, readDetail, type Mandate } from "@/lib/deals";
import { type MessageKey, languageOf } from "@/lib/i18n/messages";
import { formatIsoDate } from "@/lib/i18n/format";
import { stageLabel } from "@/lib/pipeline";
import { sendJson, useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;
type Counterparty = { company_id: number; name: string };
type Company = { id: number; name: string };
type Props = { mandate: Mandate; onChanged: () => Promise<void>; messages: Messages };

const KYC_CHECKS = [
  ["ubo_check", "compliance.ubo"],
  ["id_check", "compliance.idCheck"],
  ["pep_sanctions_screening", "compliance.pep"],
  ["sanctions_hit", "compliance.sanctionsHit"],
] as const;

function ConflictSection({ mandate, onChanged, messages }: Props) {
  // After a decision an unstaffed compliance officer can no longer read the deal (AUTHZ-02), so the
  // decision's own response is what this section shows.
  const [decided, setDecided] = useState<ConflictStatus | null>(null);
  const status = decided ?? (mandate.conflict_status as ConflictStatus);
  // 403 for everyone but compliance: only compliance learns what the deal conflicts with (AUTHZ-05 c2).
  const hits = useApiData<ConflictHit[]>(`/api/v1/mandates/${mandate.id}/conflicts`);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function decide(decision: "clear" | "reject") {
    setError(null);
    const result = await sendJson(`/api/v1/mandates/${mandate.id}/conflicts/decision`, "POST", { decision, reason });
    if (result.status === 200) {
      setReason("");
      setDecided((result.body as { conflict_status: ConflictStatus }).conflict_status);
      await onChanged();
      return;
    }
    setError(readDetail(result.body, messages["common.saveFailed"]));
  }

  return (
    <section className="flex flex-col gap-3" aria-label={messages["compliance.conflictStatus"]}>
      <div className="flex items-center gap-2">
        <h2>{messages["compliance.conflictStatus"]}</h2>
        <Badge variant={status === "review" || status === "rejected" ? "destructive" : "secondary"} data-conflict={status}>
          {messages[CONFLICT_STATUS_LABEL[status]]}
        </Badge>
      </div>
      {status === "review" && !hits.data ? <p>{messages["compliance.reviewHint"]}</p> : null}
      {hits.data && hits.data.length > 0 ? (
        <ScrollRegion label={messages["a11y.scrollRegion"]}>
          <Table aria-label={messages["compliance.conflicts"]}>
            <TableHeader>
              <TableRow>
                <TableHead>{messages["compliance.ourCompany"]}</TableHead>
                <TableHead>{messages["compliance.matched"]}</TableHead>
                <TableHead>{messages["compliance.otherDeal"]}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {hits.data.map((hit) => (
                <TableRow key={`${hit.company_name}-${hit.other_mandate_id}`}>
                  <TableCell>
                    {hit.company_name} ({hit.role})
                  </TableCell>
                  <TableCell>
                    {hit.matched_company_name} ({hit.other_role})
                  </TableCell>
                  <TableCell>
                    {hit.other_code_name} · {stageLabel(hit.other_stage)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ScrollRegion>
      ) : null}
      {hits.data && status === "review" ? (
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="conflict-reason">{messages["compliance.reason"]}</FieldLabel>
            <Textarea id="conflict-reason" value={reason} onChange={(event) => setReason(event.target.value)} />
            <FieldError>{error}</FieldError>
          </Field>
          <div className="flex gap-2">
            <Button type="button" disabled={!reason.trim()} onClick={() => void decide("clear")}>
              {messages["compliance.clear"]}
            </Button>
            <Button type="button" variant="destructive" disabled={!reason.trim()} onClick={() => void decide("reject")}>
              {messages["compliance.reject"]}
            </Button>
          </div>
        </FieldGroup>
      ) : null}
    </section>
  );
}

function CounterpartySection({ mandate, onChanged, messages }: Props) {
  const path = `/api/v1/mandates/${mandate.id}/counterparties`;
  const counterparties = useApiData<Counterparty[]>(path);
  const [query, setQuery] = useState("");
  const companies = useApiData<Company[]>(query.trim().length >= 2 ? `/api/v1/companies/?q=${encodeURIComponent(query)}&limit=8` : null);
  const [error, setError] = useState<string | null>(null);
  const known = new Set((counterparties.data ?? []).map((c) => c.company_id));

  async function add(companyId: number) {
    setError(null);
    const result = await sendJson(path, "POST", { company_id: companyId });
    if (result.status === 201) {
      setQuery("");
      await counterparties.reload();
      await onChanged();
      return;
    }
    const inline = fieldErrors(result.body);
    setError(inline.company_id ?? readDetail(result.body, messages["common.saveFailed"]));
  }

  return (
    <section className="flex flex-col gap-3" aria-label={messages["compliance.counterparties"]}>
      <h2>{messages["compliance.counterparties"]}</h2>
      <ul className="flex flex-wrap gap-2">
        {(counterparties.data ?? []).map((c) => (
          <li key={c.company_id}>
            <Badge variant="outline">{c.name}</Badge>
          </li>
        ))}
      </ul>
      {mandate.can_edit ? (
        <Field>
          <FieldLabel htmlFor="counterparty-search">{messages["compliance.addCounterparty"]}</FieldLabel>
          <Input id="counterparty-search" value={query} onChange={(event) => setQuery(event.target.value)} />
          <FieldError>{error}</FieldError>
          <div className="flex flex-wrap gap-2">
            {(companies.data ?? [])
              .filter((company) => !known.has(company.id))
              .map((company) => (
                <Button key={company.id} type="button" variant="outline" size="sm" onClick={() => void add(company.id)}>
                  {company.name}
                </Button>
              ))}
          </div>
        </Field>
      ) : null}
    </section>
  );
}

function KycSection({ mandate, onChanged, messages }: Props) {
  const path = `/api/v1/mandates/${mandate.id}/kyc`;
  const kyc = useApiData<Kyc>(path);
  const [review, setReview] = useState<Record<string, boolean> | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  if (!kyc.data) return null;
  const current = kyc.data;
  const form = review ?? {
    ubo_check: current.ubo_check,
    id_check: current.id_check,
    pep_sanctions_screening: current.pep_sanctions_screening,
    sanctions_hit: current.sanctions_hit,
  };

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const result = await sendJson(path, "POST", form);
    if (result.status === 200) {
      setReview(null);
      await kyc.reload();
      await onChanged();
      return;
    }
    setError(readDetail(result.body, messages["common.saveFailed"]));
  }

  async function unfreeze() {
    setError(null);
    const result = await sendJson(`/api/v1/mandates/${mandate.id}/unfreeze`, "POST", { reason });
    if (result.status === 200) {
      setReason("");
      setReview(null);
      await kyc.reload();
      await onChanged();
      return;
    }
    setError(readDetail(result.body, messages["common.saveFailed"]));
  }

  return (
    <section className="flex flex-col gap-3" aria-label={messages["compliance.kyc"]}>
      <div className="flex items-center gap-2">
        <h2>{messages["compliance.kycStatus"]}</h2>
        <Badge variant={current.status === "approved" ? "default" : current.status === "frozen" ? "destructive" : "secondary"}>
          {messages[KYC_STATUS_LABEL[current.status]]}
        </Badge>
      </div>
      {current.approved_at && current.reviewer_name ? (
        <p>
          {fillTemplate(messages["compliance.approvedBy"], {
            date: formatIsoDate(current.approved_at, languageOf(messages)),
            name: current.reviewer_name,
          })}
        </p>
      ) : null}
      {current.frozen ? (
        <Alert variant="destructive">
          <AlertDescription>{messages["compliance.frozen"]}</AlertDescription>
        </Alert>
      ) : null}
      {current.can_review ? (
        <form onSubmit={(event) => void save(event)}>
          <FieldGroup>
            {KYC_CHECKS.map(([key, label]) => (
              <Field key={key} orientation="horizontal">
                <Checkbox
                  id={`kyc-${key}`}
                  checked={form[key]}
                  onCheckedChange={(checked) => setReview({ ...form, [key]: checked === true })}
                />
                <FieldLabel htmlFor={`kyc-${key}`}>{messages[label]}</FieldLabel>
              </Field>
            ))}
            <p>
              {messages["compliance.kycStatus"]}:{" "}
              {messages[KYC_STATUS_LABEL[kycOutcome(form as Parameters<typeof kycOutcome>[0])]]}
            </p>
            <Button type="submit">{messages["compliance.saveKyc"]}</Button>
          </FieldGroup>
        </form>
      ) : null}
      {current.can_review && current.frozen ? (
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="unfreeze-reason">{messages["compliance.unfreezeReason"]}</FieldLabel>
            <Textarea id="unfreeze-reason" value={reason} onChange={(event) => setReason(event.target.value)} />
          </Field>
          <Button type="button" variant="outline" disabled={!reason.trim()} onClick={() => void unfreeze()}>
            {messages["compliance.unfreeze"]}
          </Button>
        </FieldGroup>
      ) : null}
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
    </section>
  );
}

export function ComplianceTab(props: Props) {
  return (
    <div className="flex flex-col gap-6">
      <ConflictSection {...props} />
      <Separator />
      <CounterpartySection {...props} />
      <Separator />
      <KycSection {...props} />
    </div>
  );
}
