"use client";

import { useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { readDetail } from "@/lib/deals";
import type { MessageKey } from "@/lib/i18n/messages";
import { sendJson, useApiData } from "@/lib/use-api";
import { apiFetch } from "@/services/api";

type Messages = Record<MessageKey, string>;
type RecordType = "contact" | "company";
type Merge = { id: number; record_type: RecordType; survivor_id: number; duplicate_id: number; merged_at: string };
type Pick = "survivor" | "duplicate";

const FIELDS: Record<RecordType, string[]> = {
  contact: ["first_name", "last_name", "email", "phone", "language", "salutation", "source"],
  company: ["name", "type", "enterprise_number", "vat_or_registry_number", "legal_form", "nace_code", "address"],
};
const PATH: Record<RecordType, string> = { contact: "/api/v1/contacts/", company: "/api/v1/companies/" };

export function MergeView({ messages }: { messages: Messages }) {
  const [recordType, setRecordType] = useState<RecordType>("contact");
  const [survivorId, setSurvivorId] = useState("");
  const [duplicateId, setDuplicateId] = useState("");
  const [records, setRecords] = useState<{ survivor: Record<string, unknown>; duplicate: Record<string, unknown> } | null>(
    null,
  );
  const [picks, setPicks] = useState<Record<string, Pick>>({});
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const recent = useApiData<Merge[]>("/api/v1/merges/");

  async function load() {
    setError("");
    setNotice("");
    const [survivor, duplicate] = await Promise.all(
      [survivorId, duplicateId].map(async (id) => {
        const response = await apiFetch(`${PATH[recordType]}${id}`).catch(() => null);
        return response?.ok ? ((await response.json()) as Record<string, unknown>) : null;
      }),
    );
    if (!survivor || !duplicate) {
      setRecords(null);
      setError(messages["common.notFound"]);
      return;
    }
    setPicks({});
    setRecords({ survivor, duplicate });
  }

  async function submit() {
    const result = await sendJson("/api/v1/merges/", "POST", {
      record_type: recordType,
      survivor_id: Number(survivorId),
      duplicate_id: Number(duplicateId),
      fields: picks,
    });
    if (result.status === 201) {
      setRecords(null);
      setNotice(messages["merge.done"]);
      await recent.reload();
      return;
    }
    setError(readDetail(result.body, messages["common.saveFailed"]));
  }

  async function undo(merge: Merge) {
    const result = await sendJson(`/api/v1/merges/${merge.id}/undo`, "POST");
    if (result.status === 200) {
      setNotice(messages["merge.undone"]);
      await recent.reload();
      return;
    }
    setError(readDetail(result.body, messages["common.saveFailed"]));
  }

  const show = (value: unknown) => (value === null || value === undefined ? "" : String(value));

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>
            <h1>{messages["merge.title"]}</h1>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <FieldGroup>
            <div className="grid gap-4 md:grid-cols-3">
              <Field>
                <FieldLabel htmlFor="merge-type">{messages["merge.recordType"]}</FieldLabel>
                <Select value={recordType} onValueChange={(value) => setRecordType(value as RecordType)}>
                  <SelectTrigger id="merge-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="contact">{messages["merge.contact"]}</SelectItem>
                    <SelectItem value="company">{messages["merge.company"]}</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Field>
                <FieldLabel htmlFor="merge-survivor">{messages["merge.survivorId"]}</FieldLabel>
                <Input id="merge-survivor" inputMode="numeric" value={survivorId} onChange={(e) => setSurvivorId(e.target.value)} />
              </Field>
              <Field>
                <FieldLabel htmlFor="merge-duplicate">{messages["merge.duplicateId"]}</FieldLabel>
                <Input
                  id="merge-duplicate"
                  inputMode="numeric"
                  value={duplicateId}
                  onChange={(e) => setDuplicateId(e.target.value)}
                />
              </Field>
            </div>
            <Button variant="outline" onClick={() => void load()} disabled={!survivorId || !duplicateId}>
              {messages["merge.load"]}
            </Button>
          </FieldGroup>

          {records ? (
            <>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{messages["merge.field"]}</TableHead>
                      <TableHead>{messages["merge.keep"]}</TableHead>
                      <TableHead>{messages["merge.duplicate"]}</TableHead>
                      <TableHead>{messages["merge.keep"]}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {FIELDS[recordType].map((field) => (
                      <TableRow key={field}>
                        <TableCell>{field}</TableCell>
                        <TableCell>{show(records.survivor[field])}</TableCell>
                        <TableCell>{show(records.duplicate[field])}</TableCell>
                        <TableCell>
                          <Select
                            value={picks[field] ?? "survivor"}
                            onValueChange={(value) => setPicks((current) => ({ ...current, [field]: value as Pick }))}
                          >
                            <SelectTrigger aria-label={`${messages["merge.keep"]} ${field}`}>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="survivor">{show(records.survivor[field]) || "-"}</SelectItem>
                              <SelectItem value="duplicate">{show(records.duplicate[field]) || "-"}</SelectItem>
                            </SelectContent>
                          </Select>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <Button onClick={() => void submit()}>{messages["merge.submit"]}</Button>
            </>
          ) : null}

          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          {notice ? <p role="status">{notice}</p> : null}
        </CardContent>
      </Card>

      {recent.data ? (
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>{messages["merge.recent"]}</h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableBody>
                {recent.data.map((merge) => (
                  <TableRow key={merge.id}>
                    <TableCell>
                      {merge.record_type} {merge.duplicate_id} → {merge.survivor_id}
                    </TableCell>
                    <TableCell>{new Date(merge.merged_at).toLocaleString()}</TableCell>
                    <TableCell>
                      <Button size="sm" variant="outline" onClick={() => void undo(merge)}>
                        {messages["merge.undo"]}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
