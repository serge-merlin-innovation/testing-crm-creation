"use client";

import { useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { readDetail } from "@/lib/deals";
import type { MessageKey } from "@/lib/i18n/messages";
import { sendJson } from "@/lib/use-api";
import { apiFetch } from "@/services/api";

type Messages = Record<MessageKey, string>;
type Entity = "contact" | "company";
type Upload = { id: number; headers: string[]; fields: string[]; required_fields: string[]; suggested_mapping: Record<string, string> };
type RowStatus = "new" | "duplicate" | "error";
type Preview = { counts: Record<RowStatus, number>; rows: { row: number; status: RowStatus; errors: string[] }[] };
type Done = { status: string; created: number; counts: Record<RowStatus, number> | null; error_file_url: string | null };

const SKIP = "skip";
const STATUS_LABEL: Record<RowStatus, MessageKey> = { new: "imports.new", duplicate: "imports.duplicate", error: "imports.error" };

export function ImportsView({ messages }: { messages: Messages }) {
  const [entity, setEntity] = useState<Entity>("contact");
  const [file, setFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<Upload | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<Preview | null>(null);
  const [done, setDone] = useState<Done | null>(null);
  const [error, setError] = useState("");

  async function send() {
    if (!file) return;
    setError("");
    setPreview(null);
    setDone(null);
    const body = new FormData();
    body.set("entity", entity);
    body.set("file", file);
    const response = await apiFetch("/api/v1/imports/", { method: "POST", body }).catch(() => null);
    const payload: unknown = await response?.json().catch(() => null);
    if (response?.status !== 201) {
      setError(readDetail(payload, messages["common.saveFailed"]));
      return;
    }
    const uploaded = payload as Upload;
    setUpload(uploaded);
    setMapping(uploaded.suggested_mapping);
  }

  async function runPreview() {
    if (!upload) return;
    setError("");
    const result = await sendJson(`/api/v1/imports/${upload.id}/preview`, "POST", { mapping });
    if (result.status !== 200) {
      setError(readDetail(result.body, messages["common.saveFailed"]));
      return;
    }
    setPreview(result.body as Preview);
  }

  async function confirm() {
    if (!upload) return;
    const result = await sendJson(`/api/v1/imports/${upload.id}/confirm`, "POST");
    if (result.status !== 200) {
      setError(readDetail(result.body, messages["common.saveFailed"]));
      return;
    }
    setDone(result.body as Done);
  }

  function choose(field: string, column: string) {
    setMapping((current) => {
      const next = { ...current };
      if (column === SKIP) delete next[field];
      else next[field] = column;
      return next;
    });
    setPreview(null);
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>
            <h1>{messages["imports.title"]}</h1>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <FieldGroup>
            <div className="grid gap-4 md:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="import-entity">{messages["imports.entity"]}</FieldLabel>
                <Select value={entity} onValueChange={(value) => setEntity(value as Entity)}>
                  <SelectTrigger id="import-entity">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="contact">{messages["search.contacts"]}</SelectItem>
                    <SelectItem value="company">{messages["search.companies"]}</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Field>
                <FieldLabel htmlFor="import-file">{messages["imports.file"]}</FieldLabel>
                <Input
                  id="import-file"
                  type="file"
                  accept=".xlsx"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                />
              </Field>
            </div>
            <Button onClick={() => void send()} disabled={!file}>
              {messages["imports.upload"]}
            </Button>
          </FieldGroup>
        </CardContent>
      </Card>

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {upload && !done ? (
        <Card>
          <CardContent className="flex flex-col gap-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{messages["merge.field"]}</TableHead>
                  <TableHead>{messages["imports.column"]}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {upload.fields.map((field) => (
                  <TableRow key={field}>
                    <TableCell>
                      {field}
                      {upload.required_fields.includes(field) ? " *" : ""}
                    </TableCell>
                    <TableCell>
                      <Select value={mapping[field] ?? SKIP} onValueChange={(column) => choose(field, column)}>
                        <SelectTrigger aria-label={`${messages["imports.column"]} ${field}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={SKIP}>{messages["imports.notMapped"]}</SelectItem>
                          {upload.headers.map((header) => (
                            <SelectItem key={header} value={header}>
                              {header}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Button variant="outline" onClick={() => void runPreview()}>
              {messages["imports.preview"]}
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {preview && !done ? (
        <Card>
          <CardContent className="flex flex-col gap-4">
            <div className="flex gap-2" aria-label={messages["imports.preview"]}>
              {(Object.keys(STATUS_LABEL) as RowStatus[]).map((status) => (
                <Badge key={status} variant={status === "error" ? "destructive" : "secondary"}>
                  {messages[STATUS_LABEL[status]]}: {preview.counts[status]}
                </Badge>
              ))}
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{messages["imports.row"]}</TableHead>
                  <TableHead>{messages["imports.status"]}</TableHead>
                  <TableHead>{messages["imports.details"]}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {preview.rows.map((row) => (
                  <TableRow key={row.row}>
                    <TableCell>{row.row}</TableCell>
                    <TableCell>{messages[STATUS_LABEL[row.status]]}</TableCell>
                    <TableCell>{row.errors.join("; ")}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Button onClick={() => void confirm()}>{messages["imports.confirm"]}</Button>
          </CardContent>
        </Card>
      ) : null}

      {done ? (
        <Card>
          <CardContent className="flex flex-col gap-4">
            <p role="status">
              {done.status === "queued"
                ? messages["imports.queued"]
                : `${messages["imports.completed"]} ${messages["imports.created"]}: ${done.created}`}
            </p>
            {done.error_file_url ? (
              <Button asChild variant="outline">
                <a href={done.error_file_url} download>
                  {messages["imports.errorFile"]}
                </a>
              </Button>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
