"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fieldErrors, MANDATE_TYPES, readDetail } from "@/lib/deals";
import { type MessageKey, languageOf } from "@/lib/i18n/messages";
import { formatAmount } from "@/lib/i18n/format";
import {
  groupByStage,
  OPPORTUNITY_STAGES,
  stageLabelKey,
  TRIGGERS,
  weightedEv,
  type Opportunity,
} from "@/lib/origination";
import { sendJson, useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;
type Option = { id: number; name?: string; label?: string };

export function Choice({
  id,
  label,
  value,
  onChange,
  options,
  error,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  error?: string;
}) {
  return (
    <Field>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id} aria-invalid={Boolean(error)}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
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

export function OriginationView({ messages, canCreate }: { messages: Messages; canCreate: boolean }) {
  const router = useRouter();
  const opportunities = useApiData<Opportunity[]>("/api/v1/origination/opportunities");
  const companies = useApiData<Option[]>(canCreate ? "/api/v1/companies/?limit=200" : null);
  const sectors = useApiData<Option[]>(canCreate ? "/api/v1/picklists/?kind=sector" : null);
  const [companyId, setCompanyId] = useState("");
  const [type, setType] = useState("sell_side");
  const [trigger, setTrigger] = useState("succession");
  const [sectorId, setSectorId] = useState("");
  const [ev, setEv] = useState("");
  const [probability, setProbability] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  const rows = opportunities.data ?? [];
  const columns = groupByStage(rows);

  // ORI-01 c4: warn while choosing, before the opportunity exists. No deal is named.
  const preview = useApiData<{ conflict_warning: boolean }>(
    companyId ? `/api/v1/origination/conflict-warning?company_id=${companyId}` : null,
  );
  const warning = Boolean(companyId && preview.data?.conflict_warning);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    const payload: Record<string, unknown> = { type, trigger };
    if (companyId) payload.company_id = Number(companyId);
    if (sectorId) payload.sector_id = Number(sectorId);
    if (ev) payload.estimated_ev = ev;
    if (probability) payload.probability = Number(probability);
    const result = await sendJson("/api/v1/origination/opportunities", "POST", payload);
    if (result.status === 201) {
      router.push(`/origination/${(result.body as { id: number }).id}`);
      return;
    }
    const inline = fieldErrors(result.body);
    setErrors(Object.keys(inline).length ? inline : { form: readDetail(result.body, messages["common.saveFailed"]) });
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>
            <h1>{messages["origination.title"]}</h1>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <CardDescription>
            {messages["origination.weighted"]}: {formatAmount(weightedEv(rows), languageOf(messages))}
          </CardDescription>
          {rows.length === 0 ? <p>{messages["origination.empty"]}</p> : null}
          <div className="grid gap-4 md:grid-cols-4">
            {OPPORTUNITY_STAGES.map((stage) => (
              <section key={stage} aria-label={messages[stageLabelKey(stage)]} className="flex flex-col gap-2">
                <CardTitle>
                  <h2>
                    {messages[stageLabelKey(stage)]} <Badge variant="secondary">{columns[stage].length}</Badge>
                  </h2>
                </CardTitle>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{messages["origination.company"]}</TableHead>
                      <TableHead>{messages["origination.probability"]}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {columns[stage].map((row) => (
                      <TableRow key={row.id} data-opportunity={row.company_name}>
                        <TableCell>
                          <Link href={`/origination/${row.id}`}>{row.company_name}</Link>
                          {row.conflict_warning ? (
                            <Badge variant="destructive" className="ml-2">
                              !
                            </Badge>
                          ) : null}
                        </TableCell>
                        <TableCell>{row.probability}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </section>
            ))}
          </div>
        </CardContent>
      </Card>

      {canCreate ? (
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>{messages["origination.new"]}</h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={(event) => void create(event)}>
              <FieldGroup>
                <Choice
                  id="opportunity-company"
                  label={messages["origination.company"]}
                  value={companyId}
                  onChange={setCompanyId}
                  options={(companies.data ?? []).map((company) => ({ value: String(company.id), label: company.name ?? "" }))}
                  error={errors.company_id}
                />
                {warning ? (
                  <Alert variant="destructive">
                    <AlertDescription>{messages["origination.conflictWarning"]}</AlertDescription>
                  </Alert>
                ) : null}
                <Choice
                  id="opportunity-type"
                  label={messages["deals.type"]}
                  value={type}
                  onChange={setType}
                  options={MANDATE_TYPES.map((value) => ({ value, label: messages[`origination.type.${value}`] }))}
                  error={errors.type}
                />
                <Choice
                  id="opportunity-trigger"
                  label={messages["origination.trigger"]}
                  value={trigger}
                  onChange={setTrigger}
                  options={TRIGGERS.map((value) => ({ value, label: messages[`origination.trigger.${value}`] }))}
                  error={errors.trigger}
                />
                <Choice
                  id="opportunity-sector"
                  label={messages["deals.sector"]}
                  value={sectorId}
                  onChange={setSectorId}
                  options={(sectors.data ?? []).map((sector) => ({ value: String(sector.id), label: sector.label ?? "" }))}
                  error={errors.sector_id}
                />
                <Field>
                  <FieldLabel htmlFor="opportunity-ev">{messages["origination.ev"]}</FieldLabel>
                  <Input
                    id="opportunity-ev"
                    inputMode="decimal"
                    value={ev}
                    onChange={(event) => setEv(event.target.value)}
                    aria-invalid={Boolean(errors.estimated_ev)}
                  />
                  <FieldError>{errors.estimated_ev}</FieldError>
                </Field>
                <Field>
                  <FieldLabel htmlFor="opportunity-probability">{messages["origination.probability"]}</FieldLabel>
                  <Input
                    id="opportunity-probability"
                    inputMode="numeric"
                    value={probability}
                    onChange={(event) => setProbability(event.target.value)}
                    aria-invalid={Boolean(errors.probability)}
                  />
                  <FieldError>{errors.probability}</FieldError>
                </Field>
                {errors.form ? (
                  <Alert variant="destructive">
                    <AlertDescription>{errors.form}</AlertDescription>
                  </Alert>
                ) : null}
                <Button type="submit">{messages["origination.create"]}</Button>
              </FieldGroup>
            </form>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
