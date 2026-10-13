"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { RecordTimeline } from "@/components/record-timeline";
import { ScrollRegion } from "@/components/scroll-region";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fieldErrors, readDetail } from "@/lib/deals";
import { formatIsoDate } from "@/lib/i18n/format";
import type { Language, MessageKey } from "@/lib/i18n/messages";
import { companyHref, employmentRows, RECORD_LANGUAGES, type Employment } from "@/lib/records";
import { sendJson } from "@/lib/use-api";
import { CompanyPicker, NO_COMPANY } from "../../companies/company-picker";
import { WhoKnows } from "../who-knows";

type Messages = Record<MessageKey, string>;

export type ContactDetail = {
  id: number;
  first_name: string;
  last_name: string;
  email: string | null;
  phone: string | null;
  language: Language;
  salutation: string | null;
  do_not_contact: boolean;
  marketing_opt_out: boolean;
  source: string;
  current_role: Employment | null;
  history: Employment[];
};


type Form = {
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  salutation: string;
  function: string;
};

function formOf(contact: ContactDetail): Form {
  return {
    first_name: contact.first_name,
    last_name: contact.last_name,
    email: contact.email ?? "",
    phone: contact.phone ?? "",
    salutation: contact.salutation ?? "",
    function: contact.current_role?.function ?? "",
  };
}

export function ContactView({ initial, messages, language }: { initial: ContactDetail; messages: Messages; language: Language }) {
  const [contact, setContact] = useState(initial);
  const [form, setForm] = useState<Form>(formOf(initial));
  const [companyId, setCompanyId] = useState(initial.current_role ? String(initial.current_role.company_id) : NO_COMPANY);
  const [recordLanguage, setRecordLanguage] = useState<Language>(initial.language);
  const [doNotContact, setDoNotContact] = useState(initial.do_not_contact);
  const [optOut, setOptOut] = useState(initial.marketing_opt_out);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");

  const currentCompany = contact.current_role
    ? { id: contact.current_role.company_id, name: contact.current_role.company_name }
    : null;

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    setNotice("");
    const result = await sendJson(`/api/v1/contacts/${contact.id}`, "PATCH", {
      first_name: form.first_name,
      last_name: form.last_name,
      email: form.email || null,
      phone: form.phone || null,
      salutation: form.salutation.trim() || null,
      language: recordLanguage,
      do_not_contact: doNotContact,
      marketing_opt_out: optOut,
      company_id: companyId === NO_COMPANY ? null : Number(companyId),
      function: form.function || null,
    });
    if (result.status !== 200) {
      const inline = fieldErrors(result.body);
      setErrors(Object.keys(inline).length ? inline : { form: readDetail(result.body, messages["common.saveFailed"]) });
      return;
    }
    const saved = result.body as ContactDetail;
    setContact(saved);
    setForm(formOf(saved));
    setNotice(messages["contacts.saved"]);
  }

  const textField = (field: keyof Form, label: MessageKey, type = "text") => (
    <Field>
      <FieldLabel htmlFor={`contact-${field}`}>{messages[label]}</FieldLabel>
      <Input
        id={`contact-${field}`}
        type={type}
        value={form[field]}
        onChange={(event) => setForm({ ...form, [field]: event.target.value })}
        aria-invalid={Boolean(errors[field])}
      />
      <FieldError>{errors[field]}</FieldError>
    </Field>
  );

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>
            <h1>
              {contact.first_name} {contact.last_name}
            </h1>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={(event) => void save(event)}>
            <FieldGroup>
              {textField("first_name", "contacts.firstName")}
              {textField("last_name", "contacts.lastName")}
              {textField("email", "contacts.email", "email")}
              {textField("phone", "contacts.phone", "tel")}
              {textField("salutation", "contacts.salutation")}
              <CompanyPicker
                id="contact-company"
                label={messages["contacts.company"]}
                value={companyId}
                onChange={setCompanyId}
                messages={messages}
                current={currentCompany}
                error={errors.company_id}
              />
              {textField("function", "contacts.function")}
              <Field>
                <FieldLabel htmlFor="contact-language">{messages["records.language"]}</FieldLabel>
                <Select value={recordLanguage} onValueChange={(value) => setRecordLanguage(value as Language)}>
                  <SelectTrigger id="contact-language">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {RECORD_LANGUAGES.map((value) => (
                      <SelectItem key={value} value={value}>
                        {messages[`records.language.${value}`]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field orientation="horizontal">
                <Checkbox
                  id="contact-opt-out"
                  checked={optOut}
                  onCheckedChange={(checked) => setOptOut(checked === true)}
                />
                <FieldLabel htmlFor="contact-opt-out">{messages["contacts.marketingOptOut"]}</FieldLabel>
              </Field>
              <Field orientation="horizontal">
                <Checkbox
                  id="contact-do-not-contact"
                  checked={doNotContact}
                  onCheckedChange={(checked) => setDoNotContact(checked === true)}
                />
                <FieldLabel htmlFor="contact-do-not-contact">{messages["contacts.doNotContact"]}</FieldLabel>
              </Field>
              {errors.form ? (
                <Alert variant="destructive">
                  <AlertDescription>{errors.form}</AlertDescription>
                </Alert>
              ) : null}
              <div>
                <Button type="submit">{messages["common.save"]}</Button>
              </div>
              {notice ? <FieldDescription role="status">{notice}</FieldDescription> : null}
            </FieldGroup>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2>{messages["contacts.history"]}</h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ScrollRegion label={messages["a11y.scrollRegion"]}>
            <Table aria-label={messages["contacts.history"]}>
              <TableHeader>
                <TableRow>
                  <TableHead>{messages["contacts.company"]}</TableHead>
                  <TableHead>{messages["contacts.function"]}</TableHead>
                  <TableHead>{messages["contacts.from"]}</TableHead>
                  <TableHead>{messages["contacts.until"]}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {employmentRows(contact.current_role, contact.history).map((role, index) => (
                  <TableRow key={`${role.company_id}-${role.start_date}-${index}`}>
                    <TableCell>
                      <Button asChild variant="link">
                        <Link href={companyHref(role.company_id)}>{role.company_name}</Link>
                      </Button>
                    </TableCell>
                    <TableCell>{role.function ?? ""}</TableCell>
                    <TableCell>{formatIsoDate(role.start_date, language)}</TableCell>
                    <TableCell>{role.end_date ? formatIsoDate(role.end_date, language) : messages["contacts.current"]}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollRegion>
        </CardContent>
      </Card>

      <WhoKnows
        contactId={contact.id}
        contactName={`${contact.first_name} ${contact.last_name}`}
        messages={messages}
        language={language}
      />

      <section aria-label={`${messages["timeline.title"]} ${contact.first_name} ${contact.last_name}`}>
        <RecordTimeline recordType="contact" recordId={contact.id} messages={messages} />
      </section>
    </div>
  );
}
