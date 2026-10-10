"use client";

import { useState, type FormEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { fieldErrors, readDetail } from "@/lib/deals";
import type { MessageKey } from "@/lib/i18n/messages";
import {
  MERGE_FIELDS,
  unknownFields,
  type Template,
  type TemplateKind,
} from "@/lib/process";
import { sendJson, useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;
type Language = Template["language"];
const EMPTY = {
  kind: "letter" as TemplateKind,
  name: "",
  language: "en" as Language,
  subject: "",
  body: "",
  references_im: false,
};

export function TemplatesView({ messages }: { messages: Messages }) {
  const templates = useApiData<Template[]>("/api/v1/templates/");
  const [editing, setEditing] = useState<number | null>(null);
  const [values, setValues] = useState(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const unknown = unknownFields(`${values.subject} ${values.body}`);

  function edit(template: Template) {
    setEditing(template.id);
    setValues({
      kind: template.kind,
      name: template.name,
      language: template.language,
      subject: template.subject,
      body: template.body,
      references_im: template.references_im,
    });
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    const response = editing
      ? await sendJson(`/api/v1/templates/${editing}`, "PUT", values)
      : await sendJson("/api/v1/templates/", "POST", values);
    if (response.status !== 200 && response.status !== 201) {
      const found = fieldErrors(response.body);
      setErrors(
        Object.keys(found).length
          ? found
          : { form: readDetail(response.body, messages["common.saveFailed"]) },
      );
      return;
    }
    setEditing(null);
    setValues(EMPTY);
    await templates.reload();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h1>{messages["templates.title"]}</h1>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <form onSubmit={save} aria-label={messages["templates.form"]}>
          <FieldGroup>
            <div className="grid gap-4 md:grid-cols-3">
              <Field>
                <FieldLabel htmlFor="template-kind">
                  {messages["templates.kind"]}
                </FieldLabel>
                <Select
                  value={values.kind}
                  onValueChange={(kind) =>
                    setValues({ ...values, kind: kind as TemplateKind })
                  }
                >
                  <SelectTrigger id="template-kind">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="letter">
                      {messages["templates.kind.letter"]}
                    </SelectItem>
                    <SelectItem value="report">
                      {messages["templates.kind.report"]}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Field>
                <FieldLabel htmlFor="template-name">
                  {messages["templates.name"]}
                </FieldLabel>
                <Input
                  id="template-name"
                  value={values.name}
                  onChange={(event) =>
                    setValues({ ...values, name: event.target.value })
                  }
                  required
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="template-language">
                  {messages["templates.language"]}
                </FieldLabel>
                <Select
                  value={values.language}
                  onValueChange={(language) =>
                    setValues({ ...values, language: language as Language })
                  }
                >
                  <SelectTrigger id="template-language">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="en">EN</SelectItem>
                    <SelectItem value="fr">FR</SelectItem>
                    <SelectItem value="nl">NL</SelectItem>
                  </SelectContent>
                </Select>
                {errors.language ? (
                  <FieldError>{errors.language}</FieldError>
                ) : null}
              </Field>
            </div>
            <Field>
              <FieldLabel htmlFor="template-subject">
                {messages["templates.subject"]}
              </FieldLabel>
              <Input
                id="template-subject"
                value={values.subject}
                onChange={(event) =>
                  setValues({ ...values, subject: event.target.value })
                }
                required
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="template-body">
                {messages["templates.body"]}
              </FieldLabel>
              <Textarea
                id="template-body"
                rows={8}
                value={values.body}
                onChange={(event) =>
                  setValues({ ...values, body: event.target.value })
                }
                required
              />
              <FieldDescription>
                {messages["templates.fields"]}{" "}
                {MERGE_FIELDS.map((name) => `{{${name}}}`).join(" ")}
              </FieldDescription>
              {unknown.length ? (
                <FieldError>{`${messages["templates.unknown"]} ${unknown.join(", ")}`}</FieldError>
              ) : null}
              {errors.body ? <FieldError>{errors.body}</FieldError> : null}
            </Field>
            <Field orientation="horizontal">
              <Checkbox
                id="template-im"
                checked={values.references_im}
                onCheckedChange={(checked) =>
                  setValues({ ...values, references_im: checked === true })
                }
              />
              <FieldLabel htmlFor="template-im">
                {messages["templates.referencesIm"]}
              </FieldLabel>
            </Field>
            {errors.form ? <FieldError>{errors.form}</FieldError> : null}
            <div className="flex gap-2">
              <Button type="submit" disabled={unknown.length > 0}>
                {messages["templates.save"]}
              </Button>
              {editing ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setEditing(null);
                    setValues(EMPTY);
                  }}
                >
                  {messages["templates.cancel"]}
                </Button>
              ) : null}
            </div>
          </FieldGroup>
        </form>
        <Table aria-label={messages["templates.title"]}>
          <TableHeader>
            <TableRow>
              <TableHead>{messages["templates.name"]}</TableHead>
              <TableHead>{messages["templates.kind"]}</TableHead>
              <TableHead>{messages["templates.language"]}</TableHead>
              <TableHead>{messages["templates.subject"]}</TableHead>
              <TableHead>{messages["templates.updated"]}</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {(templates.data ?? []).map((template) => (
              <TableRow key={template.id}>
                <TableCell>
                  {template.name}{" "}
                  {template.references_im ? (
                    <Badge variant="secondary">IM</Badge>
                  ) : null}
                </TableCell>
                <TableCell>
                  {
                    messages[
                      template.kind === "letter"
                        ? "templates.kind.letter"
                        : "templates.kind.report"
                    ]
                  }
                </TableCell>
                <TableCell>{template.language.toUpperCase()}</TableCell>
                <TableCell>{template.subject}</TableCell>
                <TableCell>
                  {template.updated_at.slice(0, 10)}{" "}
                  {template.updated_by_name ?? ""}
                </TableCell>
                <TableCell>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => edit(template)}
                  >
                    {messages["templates.edit"]}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
