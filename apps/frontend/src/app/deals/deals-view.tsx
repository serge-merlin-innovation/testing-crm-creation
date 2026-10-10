"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { fieldErrors, MANDATE_TYPES, readDetail } from "@/lib/deals";
import type { MessageKey } from "@/lib/i18n/messages";
import { sendJson, useApiData } from "@/lib/use-api";
import { Pipeline } from "./pipeline";

type Messages = Record<MessageKey, string>;
type Option = { id: number; name?: string; label?: string };

const NO_TARGET = "none";

function Choice({
  id,
  label,
  value,
  onChange,
  options,
  error,
  extra,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  error?: string;
  extra?: { value: string; label: string };
}) {
  return (
    <Field>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id} aria-invalid={Boolean(error)}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {extra ? <SelectItem value={extra.value}>{extra.label}</SelectItem> : null}
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <FieldError>{error}</FieldError>
    </Field>
  );
}

export function DealsView({ messages }: { messages: Messages }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const partners = useApiData<Option[]>("/api/v1/mandates/lead-partners");
  const companies = useApiData<Option[]>("/api/v1/companies/?limit=200");
  const sectors = useApiData<Option[]>("/api/v1/picklists/?kind=sector");
  const [codeName, setCodeName] = useState("");
  const [clientId, setClientId] = useState("");
  const [targetId, setTargetId] = useState(NO_TARGET);
  const [type, setType] = useState<string>("sell_side");
  const [sectorId, setSectorId] = useState("");
  const [leadId, setLeadId] = useState("");
  const [ev, setEv] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Lead partners come back only to whoever may create mandates.
  const canCreate = partners.data !== null;
  const companyOptions = (companies.data ?? []).map((company) => ({ value: String(company.id), label: company.name ?? "" }));

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    const payload: Record<string, unknown> = {
      code_name: codeName,
      type,
      target_id: targetId === NO_TARGET ? null : Number(targetId),
    };
    if (clientId) payload.client_id = Number(clientId);
    if (sectorId) payload.sector_id = Number(sectorId);
    if (leadId) payload.lead_partner_id = Number(leadId);
    if (ev) payload.estimated_ev = ev;
    const result = await sendJson("/api/v1/mandates/", "POST", payload);
    if (result.status === 201) {
      router.push(`/deals/${(result.body as { id: number }).id}`);
      return;
    }
    const inline = fieldErrors(result.body);
    setErrors(
      Object.keys(inline).length
        ? inline
        : result.status === 409
          ? { code_name: readDetail(result.body, messages["common.saveFailed"]) }
          : { form: readDetail(result.body, messages["common.saveFailed"]) },
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>
            <h1>{messages["deals.title"]}</h1>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              setSearch(query);
            }}
          >
            <Input aria-label={messages["common.search"]} value={query} onChange={(event) => setQuery(event.target.value)} />
            <Button type="submit" variant="outline">
              {messages["common.search"]}
            </Button>
          </form>
          <Pipeline messages={messages} search={search} />
        </CardContent>
      </Card>

      {canCreate ? (
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>{messages["deals.new"]}</h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={(event) => void create(event)}>
              <FieldGroup>
                <Field>
                  <FieldLabel htmlFor="deal-code-name">{messages["deals.codeName"]}</FieldLabel>
                  <Input
                    id="deal-code-name"
                    value={codeName}
                    onChange={(event) => setCodeName(event.target.value)}
                    aria-invalid={Boolean(errors.code_name)}
                  />
                  <FieldError>{errors.code_name}</FieldError>
                </Field>
                <Choice
                  id="deal-client"
                  label={messages["deals.client"]}
                  value={clientId}
                  onChange={setClientId}
                  options={companyOptions}
                  error={errors.client_id}
                />
                <Choice
                  id="deal-target"
                  label={messages["deals.target"]}
                  value={targetId}
                  onChange={setTargetId}
                  options={companyOptions}
                  error={errors.target_id}
                  extra={{ value: NO_TARGET, label: messages["deals.none"] }}
                />
                <Choice
                  id="deal-type"
                  label={messages["deals.type"]}
                  value={type}
                  onChange={setType}
                  options={MANDATE_TYPES.map((value) => ({ value, label: value }))}
                  error={errors.type}
                />
                <Choice
                  id="deal-sector"
                  label={messages["deals.sector"]}
                  value={sectorId}
                  onChange={setSectorId}
                  options={(sectors.data ?? []).map((sector) => ({ value: String(sector.id), label: sector.label ?? "" }))}
                  error={errors.sector_id}
                />
                <Choice
                  id="deal-lead"
                  label={messages["deals.leadPartner"]}
                  value={leadId}
                  onChange={setLeadId}
                  options={(partners.data ?? []).map((partner) => ({ value: String(partner.id), label: partner.name ?? "" }))}
                  error={errors.lead_partner_id}
                />
                <Field>
                  <FieldLabel htmlFor="deal-ev">{messages["deals.ev"]}</FieldLabel>
                  <Input
                    id="deal-ev"
                    inputMode="decimal"
                    value={ev}
                    onChange={(event) => setEv(event.target.value)}
                    aria-invalid={Boolean(errors.estimated_ev)}
                  />
                  <FieldError>{errors.estimated_ev}</FieldError>
                </Field>
                {errors.form ? (
                  <Alert variant="destructive">
                    <AlertDescription>{errors.form}</AlertDescription>
                  </Alert>
                ) : null}
                <Button type="submit">{messages["deals.create"]}</Button>
              </FieldGroup>
            </form>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
