"use client";

import { useState, type FormEvent } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fieldErrors, readDetail } from "@/lib/deals";
import type { Language, MessageKey } from "@/lib/i18n/messages";
import { sendJson, useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;
type Value = {
  id: number;
  kind: string;
  code: string;
  label: string;
  label_en: string;
  label_fr: string | null;
  label_nl: string | null;
  is_active: boolean;
  translated: boolean;
};

const KINDS = ["sector", "deal_stage", "deal_type", "country"];

export function PicklistsView({ messages, language }: { messages: Messages; language: Language }) {
  const [kind, setKind] = useState("sector");
  const values = useApiData<Value[]>(`/api/v1/picklists/?kind=${kind}&lang=${language}&include_inactive=true`);
  const [form, setForm] = useState({ code: "", label_en: "", label_fr: "", label_nl: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    const result = await sendJson("/api/v1/picklists/", "POST", {
      kind,
      code: form.code,
      label_en: form.label_en,
      label_fr: form.label_fr || null,
      label_nl: form.label_nl || null,
    });
    if (result.status === 201) {
      setForm({ code: "", label_en: "", label_fr: "", label_nl: "" });
      await values.reload();
      return;
    }
    const inline = fieldErrors(result.body);
    setErrors(Object.keys(inline).length ? inline : { form: readDetail(result.body, messages["common.saveFailed"]) });
  }

  async function toggle(value: Value) {
    const result = await sendJson(`/api/v1/picklists/${value.id}`, "PATCH", { is_active: !value.is_active });
    setErrors(result.status === 200 ? {} : { form: readDetail(result.body, messages["common.saveFailed"]) });
    await values.reload();
  }

  async function remove(value: Value) {
    const result = await sendJson(`/api/v1/picklists/${value.id}`, "DELETE");
    setErrors(result.status === 204 ? {} : { form: readDetail(result.body, messages["common.saveFailed"]) });
    await values.reload();
  }

  const textField = (field: keyof typeof form, label: MessageKey) => (
    <Field>
      <FieldLabel htmlFor={`picklist-${field}`}>{messages[label]}</FieldLabel>
      <Input
        id={`picklist-${field}`}
        value={form[field]}
        onChange={(event) => setForm((current) => ({ ...current, [field]: event.target.value }))}
      />
      <FieldError>{errors[field]}</FieldError>
    </Field>
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h1>{messages["picklists.title"]}</h1>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Field>
          <FieldLabel htmlFor="picklist-kind">{messages["picklists.kind"]}</FieldLabel>
          <Select value={kind} onValueChange={setKind}>
            <SelectTrigger id="picklist-kind">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {KINDS.map((value) => (
                <SelectItem key={value} value={value}>
                  {value}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        {errors.form ? (
          <Alert variant="destructive">
            <AlertDescription>{errors.form}</AlertDescription>
          </Alert>
        ) : null}
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{messages["picklists.code"]}</TableHead>
                <TableHead>{messages["picklists.labelEn"]}</TableHead>
                <TableHead>{messages["picklists.labelFr"]}</TableHead>
                <TableHead>{messages["picklists.labelNl"]}</TableHead>
                <TableHead>{messages["picklists.active"]}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(values.data ?? []).map((value) => (
                <TableRow key={value.id}>
                  <TableCell>{value.code}</TableCell>
                  <TableCell>{value.label_en}</TableCell>
                  <TableCell>{value.label_fr ?? ""}</TableCell>
                  <TableCell>{value.label_nl ?? ""}</TableCell>
                  <TableCell>
                    {value.translated ? null : <Badge variant="outline">{messages["picklists.untranslated"]}</Badge>}
                  </TableCell>
                  <TableCell className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={() => void toggle(value)}>
                      {value.is_active ? messages["picklists.deactivate"] : messages["picklists.activate"]}
                    </Button>
                    <Button size="sm" variant="destructive" onClick={() => void remove(value)}>
                      {messages["common.remove"]}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <form onSubmit={(event) => void create(event)}>
          <FieldGroup>
            {textField("code", "picklists.code")}
            {textField("label_en", "picklists.labelEn")}
            {textField("label_fr", "picklists.labelFr")}
            {textField("label_nl", "picklists.labelNl")}
            <Button type="submit">{messages["common.add"]}</Button>
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  );
}
