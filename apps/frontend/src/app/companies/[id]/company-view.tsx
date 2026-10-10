"use client";

import Link from "next/link";
import { useState } from "react";
import { RecordTimeline } from "@/components/record-timeline";
import { ScrollRegion } from "@/components/scroll-region";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fillTemplate } from "@/lib/compliance";
import { fieldErrors, readDetail } from "@/lib/deals";
import { formatAmount } from "@/lib/i18n/format";
import type { Language, MessageKey } from "@/lib/i18n/messages";
import {
  companyHref,
  financialPayload,
  groupIds,
  METRICS,
  type CompanyRef,
  type FinancialForm,
  type FinancialYear,
  type GroupNode,
  type MetricFigures,
} from "@/lib/records";
import { sendJson, useApiData } from "@/lib/use-api";
import { apiFetch } from "@/services/api";
import { CompanyPicker, NO_COMPANY as NO_PARENT } from "../company-picker";
import { InvestorProfilePanel } from "../investor-profile";

type Messages = Record<MessageKey, string>;

export type CompanyDetail = {
  id: number;
  name: string;
  type: string;
  enterprise_number: string | null;
  vat_or_registry_number: string | null;
  legal_form: string | null;
  nace_code: string | null;
  address: string | null;
  parent_id: number | null;
  group: GroupNode;
};

const BUYER_TYPES = new Set(["strategic_buyer", "financial_investor"]);
const EMPTY_FORM: FinancialForm = { revenue: "", ebitda: "", net_debt: "", fte: "", currency: "EUR", eurRate: "" };

function GroupTree({ node, currentId }: { node: GroupNode; currentId: number }) {
  return (
    <li role="treeitem" aria-label={node.name} aria-selected={node.id === currentId} aria-expanded={node.children.length ? true : undefined}>
      {node.id === currentId ? (
        node.name
      ) : (
        <Button asChild variant="link" size="sm">
          <Link href={companyHref(node.id)}>{node.name}</Link>
        </Button>
      )}
      {node.children.length ? (
        <ul role="group" className="flex flex-col gap-1 pl-4">
          {node.children.map((child) => (
            <GroupTree key={child.id} node={child} currentId={currentId} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

function FigureCell({ figures, messages, language }: { figures: MetricFigures | undefined; messages: Messages; language: Language }) {
  if (!figures) return <TableCell />;
  const override = figures.override;
  return (
    <TableCell>
      {formatAmount(figures.value, language)}
      {override && figures.imported ? (
        <FieldDescription>
          {fillTemplate(messages["companies.imported"], { value: formatAmount(figures.imported.value, language) })}
        </FieldDescription>
      ) : null}
      {override?.original_value && override.eur_rate ? (
        <FieldDescription>
          {fillTemplate(messages["companies.original"], {
            value: formatAmount(override.original_value, language),
            currency: override.original_currency,
            rate: override.eur_rate,
          })}
        </FieldDescription>
      ) : null}
    </TableCell>
  );
}

function Financials({ company, messages, language }: { company: CompanyDetail; messages: Messages; language: Language }) {
  const years = useApiData<FinancialYear[]>(`/api/v1/companies/${company.id}/financials`);
  const [year, setYear] = useState("");
  const [form, setForm] = useState<FinancialForm>(EMPTY_FORM);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");

  async function importNbb() {
    setErrors({});
    setNotice("");
    const response = await sendJson(`/api/v1/companies/${company.id}/financials/import`, "POST");
    if (response.status !== 200) {
      setErrors({ form: readDetail(response.body, messages["common.saveFailed"]) });
      return;
    }
    setNotice(messages["companies.imported.done"]);
    await years.reload();
  }

  async function saveYear() {
    setErrors({});
    setNotice("");
    if (!/^\d{4}$/.test(year.trim())) {
      setErrors({ year: messages["common.saveFailed"] });
      return;
    }
    const response = await sendJson(`/api/v1/companies/${company.id}/financials/${year.trim()}`, "PUT", financialPayload(form));
    if (response.status !== 200) {
      const inline = fieldErrors(response.body);
      setErrors(Object.keys(inline).length ? inline : { form: readDetail(response.body, messages["common.saveFailed"]) });
      return;
    }
    setForm(EMPTY_FORM);
    setNotice(messages["companies.yearSaved"]);
    await years.reload();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>{messages["companies.financials"]}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {company.enterprise_number ? (
          <div>
            <Button type="button" variant="outline" onClick={() => void importNbb()}>
              {messages["companies.importNbb"]}
            </Button>
          </div>
        ) : null}
        <ScrollRegion label={messages["a11y.scrollRegion"]}>
          <Table aria-label={messages["companies.financials"]}>
            <TableHeader>
              <TableRow>
                <TableHead>{messages["companies.year"]}</TableHead>
                {METRICS.map((metric) => (
                  <TableHead key={metric}>{messages[`companies.metric.${metric}`]}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {(years.data ?? []).map((row) => (
                <TableRow key={row.year}>
                  <TableCell>{row.year}</TableCell>
                  {METRICS.map((metric) => (
                    <FigureCell key={metric} figures={row.metrics[metric]} messages={messages} language={language} />
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ScrollRegion>
        <FieldGroup>
          <div className="grid gap-2 md:grid-cols-4">
            <Field>
              <FieldLabel htmlFor="financial-year">{messages["companies.year"]}</FieldLabel>
              <Input id="financial-year" inputMode="numeric" value={year} onChange={(event) => setYear(event.target.value)} />
              <FieldError>{errors.year}</FieldError>
            </Field>
            {METRICS.map((metric) => (
              <Field key={metric}>
                <FieldLabel htmlFor={`financial-${metric}`}>{messages[`companies.metric.${metric}`]}</FieldLabel>
                <Input
                  id={`financial-${metric}`}
                  inputMode="decimal"
                  value={form[metric]}
                  onChange={(event) => setForm({ ...form, [metric]: event.target.value })}
                />
                <FieldError>{errors[metric]}</FieldError>
              </Field>
            ))}
            <Field>
              <FieldLabel htmlFor="financial-currency">{messages["companies.currency"]}</FieldLabel>
              <Input
                id="financial-currency"
                value={form.currency}
                onChange={(event) => setForm({ ...form, currency: event.target.value })}
              />
              <FieldError>{errors.currency}</FieldError>
            </Field>
            <Field>
              <FieldLabel htmlFor="financial-rate">{messages["companies.eurRate"]}</FieldLabel>
              <Input
                id="financial-rate"
                inputMode="decimal"
                value={form.eurRate}
                onChange={(event) => setForm({ ...form, eurRate: event.target.value })}
              />
              <FieldError>{errors.eur_rate}</FieldError>
            </Field>
          </div>
          {errors.form ? (
            <Alert variant="destructive">
              <AlertDescription>{errors.form}</AlertDescription>
            </Alert>
          ) : null}
          <div>
            <Button type="button" onClick={() => void saveYear()}>
              {messages["companies.saveYear"]}
            </Button>
          </div>
          {notice ? <FieldDescription role="status">{notice}</FieldDescription> : null}
        </FieldGroup>
      </CardContent>
    </Card>
  );
}

function Group({ company, onSaved, messages }: { company: CompanyDetail; onSaved: (next: CompanyDetail) => void; messages: Messages }) {
  const [parentId, setParentId] = useState(company.parent_id ? String(company.parent_id) : NO_PARENT);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const below = groupIds(findNode(company.group, company.id) ?? company.group);
  const parent = company.parent_id ? findParent(company.group, company.id) : null;

  async function save() {
    setError("");
    setNotice("");
    const response = await sendJson(`/api/v1/companies/${company.id}`, "PATCH", {
      parent_id: parentId === NO_PARENT ? null : Number(parentId),
    });
    if (response.status !== 200) {
      setError(readDetail(response.body, messages["common.saveFailed"]));
      return;
    }
    const fresh = await apiFetch(`/api/v1/companies/${company.id}`).catch(() => null);
    if (fresh?.ok) onSaved((await fresh.json()) as CompanyDetail);
    setNotice(messages["companies.parentSaved"]);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>{messages["companies.group"]}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ul role="tree" aria-label={messages["companies.group"]} className="flex flex-col gap-1">
          <GroupTree node={company.group} currentId={company.id} />
        </ul>
        <FieldGroup>
          <CompanyPicker
            id="company-parent"
            label={messages["companies.parent"]}
            value={parentId}
            onChange={setParentId}
            messages={messages}
            exclude={below}
            current={parent}
            error={error}
          />
          <div>
            <Button type="button" onClick={() => void save()}>
              {messages["companies.saveParent"]}
            </Button>
          </div>
          {notice ? <FieldDescription role="status">{notice}</FieldDescription> : null}
        </FieldGroup>
      </CardContent>
    </Card>
  );
}

function findParent(node: GroupNode, id: number): CompanyRef | null {
  for (const child of node.children) {
    if (child.id === id) return { id: node.id, name: node.name };
    const found = findParent(child, id);
    if (found) return found;
  }
  return null;
}

function findNode(node: GroupNode, id: number): GroupNode | null {
  if (node.id === id) return node;
  for (const child of node.children) {
    const found = findNode(child, id);
    if (found) return found;
  }
  return null;
}

export function CompanyView({ initial, messages, language }: { initial: CompanyDetail; messages: Messages; language: Language }) {
  const [company, setCompany] = useState(initial);
  const details: [MessageKey, string | null][] = [
    ["companies.type", company.type],
    ["companies.enterpriseNumber", company.enterprise_number],
    ["companies.registryNumber", company.vat_or_registry_number],
    ["companies.legalForm", company.legal_form],
    ["companies.naceCode", company.nace_code],
    ["companies.address", company.address],
  ];

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>
            <h1>{company.name}</h1>
          </CardTitle>
          <CardDescription>{messages["companies.details"]}</CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollRegion label={messages["a11y.scrollRegion"]}>
            <Table aria-label={messages["companies.details"]}>
              <TableBody>
                {details
                  .filter(([, value]) => value)
                  .map(([label, value]) => (
                    <TableRow key={label}>
                      <TableHead>{messages[label]}</TableHead>
                      <TableCell>{value}</TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </ScrollRegion>
        </CardContent>
      </Card>
      <Financials company={company} messages={messages} language={language} />
      <Group company={company} onSaved={setCompany} messages={messages} />
      {BUYER_TYPES.has(company.type) ? (
        <Card>
          <CardContent>
            <InvestorProfilePanel companyId={company.id} messages={messages} />
          </CardContent>
        </Card>
      ) : null}
      <section aria-label={`${messages["timeline.title"]} ${company.name}`}>
        <RecordTimeline recordType="company" recordId={company.id} messages={messages} />
      </section>
    </div>
  );
}
