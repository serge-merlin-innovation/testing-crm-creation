"use client";

import { useState, type FormEvent } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { fieldErrors, readDetail } from "@/lib/deals";
import {
  feePayload,
  formFromTerms,
  needsAmendment,
  type FeeForm,
  type FeeTerms,
  type Invoice,
  type SuccessFeeKind,
} from "@/lib/fees";
import type { MessageKey } from "@/lib/i18n/messages";
import { sendJson, useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;

function errorsOf(body: unknown, messages: Messages): Record<string, string> {
  const inline = fieldErrors(body);
  return Object.keys(inline).length ? inline : { form: readDetail(body, messages["common.saveFailed"]) };
}

function FormError({ message }: { message?: string }) {
  return message ? (
    <Alert variant="destructive">
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  ) : null;
}

function TermsForm({ terms, onSaved, messages }: { terms: FeeTerms; onSaved: () => Promise<void>; messages: Messages }) {
  const [form, setForm] = useState<FeeForm>(formFromTerms(terms));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const set = <K extends keyof FeeForm>(key: K, value: FeeForm[K]) => setForm((current) => ({ ...current, [key]: value }));
  const amend = needsAmendment(terms, form);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    const result = await sendJson(`/api/v1/mandates/${terms.mandate_id}/fees`, "PUT", feePayload(form));
    if (result.status === 200) {
      await onSaved();
      return;
    }
    setErrors(errorsOf(result.body, messages));
  }

  return (
    <form onSubmit={(event) => void save(event)}>
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="fee-retainer">{messages["fees.retainer"]}</FieldLabel>
          <Input id="fee-retainer" inputMode="decimal" value={form.retainer_monthly} onChange={(e) => set("retainer_monthly", e.target.value)} />
          <FieldError>{errors.retainer_monthly}</FieldError>
        </Field>
        <Field>
          <FieldLabel htmlFor="fee-kind">{messages["fees.kind"]}</FieldLabel>
          <Select value={form.success_fee_kind} onValueChange={(value) => set("success_fee_kind", value as SuccessFeeKind)}>
            <SelectTrigger id="fee-kind">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="percent">{messages["fees.kindPercent"]}</SelectItem>
              <SelectItem value="fixed">{messages["fees.kindFixed"]}</SelectItem>
              <SelectItem value="lehman">{messages["fees.kindLehman"]}</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        {form.success_fee_kind === "percent" ? (
          <Field>
            <FieldLabel htmlFor="fee-percent">{messages["fees.percent"]}</FieldLabel>
            <Input id="fee-percent" inputMode="decimal" value={form.success_fee_percent} onChange={(e) => set("success_fee_percent", e.target.value)} />
            <FieldError>{errors.success_fee_percent}</FieldError>
          </Field>
        ) : null}
        {form.success_fee_kind === "fixed" ? (
          <Field>
            <FieldLabel htmlFor="fee-fixed">{messages["fees.fixed"]}</FieldLabel>
            <Input id="fee-fixed" inputMode="decimal" value={form.success_fee_fixed} onChange={(e) => set("success_fee_fixed", e.target.value)} />
            <FieldError>{errors.success_fee_fixed}</FieldError>
          </Field>
        ) : null}
        {form.success_fee_kind === "lehman" ? (
          <Field>
            <FieldLabel htmlFor="fee-tiers">{messages["fees.tiers"]}</FieldLabel>
            <Input id="fee-tiers" placeholder="10000:3, 20000:2, :1" value={form.lehman_tiers} onChange={(e) => set("lehman_tiers", e.target.value)} />
            <FieldError>{errors.lehman_tiers}</FieldError>
          </Field>
        ) : null}
        <Field>
          <FieldLabel htmlFor="fee-minimum">{messages["fees.minimum"]}</FieldLabel>
          <Input id="fee-minimum" inputMode="decimal" value={form.minimum_fee} onChange={(e) => set("minimum_fee", e.target.value)} />
          <FieldError>{errors.minimum_fee}</FieldError>
        </Field>
        <Field orientation="horizontal">
          <Checkbox
            id="fee-creditable"
            checked={form.retainers_creditable}
            onCheckedChange={(checked) => set("retainers_creditable", checked === true)}
          />
          <FieldLabel htmlFor="fee-creditable">{messages["fees.creditable"]}</FieldLabel>
        </Field>
        {amend ? (
          <>
            <Alert>
              <AlertDescription>{messages["fees.amendmentNeeded"]}</AlertDescription>
            </Alert>
            <Field>
              <FieldLabel htmlFor="fee-reason">{messages["fees.changeReason"]}</FieldLabel>
              <Textarea id="fee-reason" value={form.change_reason} onChange={(e) => set("change_reason", e.target.value)} />
              <FieldError>{errors.change_reason}</FieldError>
            </Field>
            <Field>
              <FieldLabel htmlFor="fee-letter">{messages["fees.amendedLetter"]}</FieldLabel>
              <Input id="fee-letter" type="url" placeholder="https://" value={form.amended_letter_url} onChange={(e) => set("amended_letter_url", e.target.value)} />
              <FieldError>{errors.amended_letter_url}</FieldError>
            </Field>
          </>
        ) : null}
        <FormError message={errors.form ?? errors[""]} />
        <Button type="submit">{messages["fees.save"]}</Button>
      </FieldGroup>
    </form>
  );
}

function Invoices({ mandateId, canRecord, onChanged, messages }: { mandateId: number; canRecord: boolean; onChanged: () => Promise<void>; messages: Messages }) {
  const path = `/api/v1/mandates/${mandateId}/invoices`;
  const invoices = useApiData<Invoice[]>(path);
  const [type, setType] = useState<Invoice["type"]>("retainer");
  const [amount, setAmount] = useState("");
  const [sent, setSent] = useState("");
  const [paid, setPaid] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function record(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    const result = await sendJson(path, "POST", { type, amount, sent_date: sent, paid_date: paid || null });
    if (result.status === 201) {
      setAmount("");
      setSent("");
      setPaid("");
      await invoices.reload();
      await onChanged();
      return;
    }
    setErrors(errorsOf(result.body, messages));
  }

  async function markPaid(invoice: Invoice, value: string) {
    await sendJson(`${path}/${invoice.id}`, "PATCH", { paid_date: value || null });
    await invoices.reload();
    await onChanged();
  }

  return (
    <div className="flex flex-col gap-4">
      <h2>{messages["invoices.title"]}</h2>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{messages["invoices.type"]}</TableHead>
            <TableHead>{messages["invoices.amount"]}</TableHead>
            <TableHead>{messages["invoices.sent"]}</TableHead>
            <TableHead>{messages["invoices.paid"]}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {(invoices.data ?? []).map((invoice) => (
            <TableRow key={invoice.id} data-invoice={invoice.id}>
              <TableCell>{invoice.type === "retainer" ? messages["invoices.retainer"] : messages["invoices.successFee"]}</TableCell>
              <TableCell>{invoice.amount}</TableCell>
              <TableCell>{invoice.sent_date}</TableCell>
              <TableCell>
                {canRecord ? (
                  <Input
                    type="date"
                    aria-label={messages["invoices.paid"]}
                    defaultValue={invoice.paid_date ?? ""}
                    onBlur={(e) => void markPaid(invoice, e.target.value)}
                  />
                ) : (
                  (invoice.paid_date ?? "")
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {canRecord ? (
        <form onSubmit={(event) => void record(event)}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="invoice-type">{messages["invoices.type"]}</FieldLabel>
              <Select value={type} onValueChange={(value) => setType(value as Invoice["type"])}>
                <SelectTrigger id="invoice-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="retainer">{messages["invoices.retainer"]}</SelectItem>
                  <SelectItem value="success_fee">{messages["invoices.successFee"]}</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field>
              <FieldLabel htmlFor="invoice-amount">{messages["invoices.amount"]}</FieldLabel>
              <Input id="invoice-amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} required />
              <FieldError>{errors.amount}</FieldError>
            </Field>
            <Field>
              <FieldLabel htmlFor="invoice-sent">{messages["invoices.sent"]}</FieldLabel>
              <Input id="invoice-sent" type="date" value={sent} onChange={(e) => setSent(e.target.value)} required />
              <FieldError>{errors.sent_date}</FieldError>
            </Field>
            <Field>
              <FieldLabel htmlFor="invoice-paid">{messages["invoices.paid"]}</FieldLabel>
              <Input id="invoice-paid" type="date" value={paid} onChange={(e) => setPaid(e.target.value)} />
              <FieldError>{errors.paid_date}</FieldError>
            </Field>
            <FormError message={errors.form} />
            <Button type="submit">{messages["invoices.record"]}</Button>
          </FieldGroup>
        </form>
      ) : null}
    </div>
  );
}

/** Rendered only for fees.read holders; the API refuses everyone else (AUTHZ-06). */
export function FeesTab({ mandateId, canRecordInvoices, messages }: { mandateId: number; canRecordInvoices: boolean; messages: Messages }) {
  const terms = useApiData<FeeTerms>(`/api/v1/mandates/${mandateId}/fees`);
  const data = terms.data;

  return (
    <div className="flex flex-col gap-6">
      {data ? (
        <>
          <Table>
            <TableBody>
              <TableRow>
                <TableHead>{messages["fees.expected"]}</TableHead>
                <TableCell>{data.expected_fee}</TableCell>
              </TableRow>
              <TableRow>
                <TableHead>{messages["fees.retainersPaid"]}</TableHead>
                <TableCell>{data.retainers_paid}</TableCell>
              </TableRow>
              <TableRow>
                <TableHead>{messages["fees.final"]}</TableHead>
                <TableCell>{data.final_fee ?? messages["deals.none"]}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
          {data.can_edit ? <TermsForm key={JSON.stringify(data)} terms={data} onSaved={terms.reload} messages={messages} /> : null}
        </>
      ) : null}
      <Invoices mandateId={mandateId} canRecord={canRecordInvoices} onChanged={terms.reload} messages={messages} />
    </div>
  );
}
