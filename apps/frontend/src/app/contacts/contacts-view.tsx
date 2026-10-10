"use client";

import { useState, type FormEvent } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fieldErrors, readDetail } from "@/lib/deals";
import type { Language, MessageKey } from "@/lib/i18n/messages";
import { contactPayload, RECORD_LANGUAGES } from "@/lib/records";
import { sendJson, useApiData } from "@/lib/use-api";
import { RecordTimeline } from "@/components/record-timeline";
import { WhoKnows } from "./who-knows";

type Messages = Record<MessageKey, string>;
type Role = { function: string | null; company_id: number };
type Contact = {
  id: number;
  first_name: string;
  last_name: string;
  email: string | null;
  phone: string | null;
  current_role: Role | null;
  relationship_holders: { user_id: number; name: string; strength: number }[];
};
type Company = { id: number; name: string };

const NO_COMPANY = "none";

export function ContactsView({ messages, language }: { messages: Messages; language: Language }) {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const contacts = useApiData<Contact[]>(`/api/v1/contacts/?q=${encodeURIComponent(search)}`);
  const companies = useApiData<Company[]>("/api/v1/companies/?limit=200");
  const [form, setForm] = useState({ first_name: "", last_name: "", email: "", phone: "", source: "", function: "" });
  const [companyId, setCompanyId] = useState(NO_COMPANY);
  const [recordLanguage, setRecordLanguage] = useState<Language>("en");
  const [optOut, setOptOut] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<Contact | null>(null);
  const [timelineFor, setTimelineFor] = useState<Contact | null>(null);

  const companyName = (id: number | undefined) => companies.data?.find((company) => company.id === id)?.name ?? "";

  function update(field: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    setNotice("");
    const result = await sendJson(
      "/api/v1/contacts/",
      "POST",
      contactPayload(form, {
        companyId: companyId === NO_COMPANY ? null : Number(companyId),
        language: recordLanguage,
        marketingOptOut: optOut,
      }),
    );
    if (result.status === 201) {
      const warnings = (result.body as { warnings?: string[] }).warnings ?? [];
      setNotice(
        warnings.includes("duplicate_email")
          ? `${messages["contacts.created"]} ${messages["contacts.duplicateEmail"]}`
          : messages["contacts.created"],
      );
      setForm({ first_name: "", last_name: "", email: "", phone: "", source: "", function: "" });
      setOptOut(false);
      await contacts.reload();
      return;
    }
    const inline = fieldErrors(result.body);
    setErrors(Object.keys(inline).length ? inline : { form: readDetail(result.body, messages["common.saveFailed"]) });
  }

  const textField = (field: keyof typeof form, label: MessageKey, type = "text") => (
    <Field>
      <FieldLabel htmlFor={`contact-${field}`}>{messages[label]}</FieldLabel>
      <Input
        id={`contact-${field}`}
        type={type}
        value={form[field]}
        onChange={(event) => update(field, event.target.value)}
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
            <h1>{messages["contacts.title"]}</h1>
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
          {contacts.failed ? (
            <Alert variant="destructive">
              <AlertDescription>{messages["common.loadFailed"]}</AlertDescription>
            </Alert>
          ) : null}
          <div className="overflow-x-auto" tabIndex={0}>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{messages["common.name"]}</TableHead>
                  <TableHead>{messages["contacts.email"]}</TableHead>
                  <TableHead>{messages["contacts.company"]}</TableHead>
                  <TableHead>{messages["contacts.function"]}</TableHead>
                  <TableHead>{messages["search.knownBy"]}</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(contacts.data ?? []).map((contact) => (
                  <TableRow key={contact.id}>
                    <TableCell>
                      {contact.first_name} {contact.last_name}
                    </TableCell>
                    <TableCell>{contact.email ?? ""}</TableCell>
                    <TableCell>{companyName(contact.current_role?.company_id)}</TableCell>
                    <TableCell>{contact.current_role?.function ?? ""}</TableCell>
                    <TableCell>
                      {contact.relationship_holders
                        .map((holder) => `${holder.name} (${holder.strength}/3)`)
                        .join(", ")}
                    </TableCell>
                    <TableCell className="flex gap-2">
                      <Button size="sm" variant="outline" onClick={() => setSelected(contact)}>
                        {messages["contacts.relationships"]}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setTimelineFor(contact)}
                      >
                        {messages["timeline.open"]}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {contacts.data?.length === 0 ? <p>{messages["common.empty"]}</p> : null}
        </CardContent>
      </Card>

      {timelineFor ? (
        <section aria-label={`${messages["timeline.title"]} ${timelineFor.first_name} ${timelineFor.last_name}`}>
          <RecordTimeline key={timelineFor.id} recordType="contact" recordId={timelineFor.id} messages={messages} />
        </section>
      ) : null}

      {selected ? (
        <WhoKnows
          key={selected.id}
          contactId={selected.id}
          contactName={`${selected.first_name} ${selected.last_name}`}
          messages={messages}
          language={language}
        />
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>
            <h2>{messages["contacts.new"]}</h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={(event) => void create(event)}>
            <FieldGroup>
              {textField("first_name", "contacts.firstName")}
              {textField("last_name", "contacts.lastName")}
              {textField("email", "contacts.email", "email")}
              {textField("phone", "contacts.phone", "tel")}
              {textField("source", "contacts.source")}
              <Field>
                <FieldLabel htmlFor="contact-company">{messages["contacts.company"]}</FieldLabel>
                <Select value={companyId} onValueChange={setCompanyId}>
                  <SelectTrigger id="contact-company">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NO_COMPANY}>{messages["deals.none"]}</SelectItem>
                    {(companies.data ?? []).map((company) => (
                      <SelectItem key={company.id} value={String(company.id)}>
                        {company.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
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
              {errors.form ? (
                <Alert variant="destructive">
                  <AlertDescription>{errors.form}</AlertDescription>
                </Alert>
              ) : null}
              <Button type="submit">{messages["common.save"]}</Button>
              {notice ? <p role="status">{notice}</p> : null}
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
