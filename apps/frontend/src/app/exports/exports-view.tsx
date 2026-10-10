"use client";

import { ScrollRegion } from "@/components/scroll-region";
import { useState } from "react";
import { EditAction } from "@/components/session-provider";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { readDetail } from "@/lib/deals";
import type { MessageKey } from "@/lib/i18n/messages";
import { approvalNotice } from "@/lib/offboarding";
import { sendJson, useApiData } from "@/lib/use-api";
import { apiFetch } from "@/services/api";

type Messages = Record<MessageKey, string>;
type Preview = { row_count: number; needs_approval: boolean; limit: number };
type Approval = {
  id: number;
  requested_by_name: string | null;
  filter: { q: string | null };
  row_count: number;
  reason: string;
  status: string;
};

export function ExportsView({ messages, canApprove }: { messages: Messages; canApprove: boolean }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("");
  const qs = filter ? `?q=${encodeURIComponent(filter)}` : "";
  const preview = useApiData<Preview>(`/api/v1/exports/contacts/preview${qs}`);
  const approvals = useApiData<Approval[]>("/api/v1/exports/approvals");
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function download() {
    setError("");
    const response = await apiFetch(`/api/v1/exports/contacts${qs}`).catch(() => null);
    if (!response?.ok) {
      setError(response ? readDetail(await response.json().catch(() => null), messages["common.loadFailed"]) : messages["common.loadFailed"]);
      return;
    }
    const link = document.createElement("a");
    link.href = URL.createObjectURL(await response.blob());
    link.download = "contacts.csv";
    link.click();
    URL.revokeObjectURL(link.href);
    await approvals.reload();
  }

  async function request() {
    setNotice("");
    setError("");
    const result = await sendJson("/api/v1/exports/approvals", "POST", { filter: { q: filter || null }, reason });
    if (result.status === 201) {
      setNotice(messages["exports.requested"]);
      setReason("");
      await approvals.reload();
      return;
    }
    setError(readDetail(result.body, messages["common.saveFailed"]));
  }

  async function decide(id: number, approve: boolean) {
    const result = await sendJson(`/api/v1/exports/approvals/${id}`, "POST", { approve });
    if (result.status !== 200) setError(readDetail(result.body, messages["common.saveFailed"]));
    await approvals.reload();
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>
            <h1>{messages["exports.title"]}</h1>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <FieldGroup>
            <form
              className="flex items-end gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                setFilter(query);
              }}
            >
              <Field>
                <FieldLabel htmlFor="export-filter">{messages["exports.filter"]}</FieldLabel>
                <Input id="export-filter" value={query} onChange={(event) => setQuery(event.target.value)} />
              </Field>
              <Button type="submit" variant="outline">
                {messages["common.search"]}
              </Button>
            </form>
            <p>
              {messages["exports.rows"]}: {preview.data?.row_count ?? "…"}
            </p>
            {preview.data?.needs_approval ? (
              <Alert>
                <AlertDescription>{approvalNotice(messages["exports.needsApproval"], preview.data.limit)}</AlertDescription>
              </Alert>
            ) : null}
            <EditAction>
              <Button className="self-start" onClick={() => void download()}>
                {messages["exports.download"]}
              </Button>
            </EditAction>
            {preview.data?.needs_approval ? (
              <div className="flex items-end gap-2">
                <Field>
                  <FieldLabel htmlFor="export-reason">{messages["exports.reason"]}</FieldLabel>
                  <Input id="export-reason" value={reason} onChange={(event) => setReason(event.target.value)} />
                </Field>
                <Button variant="outline" disabled={reason.trim().length < 3} onClick={() => void request()}>
                  {messages["exports.request"]}
                </Button>
              </div>
            ) : null}
            {error ? (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            ) : null}
            {notice ? (
              <Alert>
                <AlertDescription role="status">{notice}</AlertDescription>
              </Alert>
            ) : null}
          </FieldGroup>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>
            <h2>{messages["exports.requests"]}</h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ScrollRegion label={messages["a11y.scrollRegion"]}>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{messages["common.name"]}</TableHead>
                  <TableHead>{messages["exports.filter"]}</TableHead>
                  <TableHead>{messages["exports.rows"]}</TableHead>
                  <TableHead>{messages["exports.reason"]}</TableHead>
                  <TableHead>{messages["users.status"]}</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(approvals.data ?? []).map((approval) => (
                  <TableRow key={approval.id}>
                    <TableCell>{approval.requested_by_name}</TableCell>
                    <TableCell>{approval.filter.q ?? ""}</TableCell>
                    <TableCell>{approval.row_count}</TableCell>
                    <TableCell>{approval.reason}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{approval.status}</Badge>
                    </TableCell>
                    <TableCell className="flex gap-2">
                      {canApprove && approval.status === "pending" ? (
                        <>
                          <Button size="sm" onClick={() => void decide(approval.id, true)}>
                            {messages["exports.approve"]}
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => void decide(approval.id, false)}>
                            {messages["exports.reject"]}
                          </Button>
                        </>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollRegion>
          {approvals.data?.length === 0 ? <p>{messages["common.empty"]}</p> : null}
        </CardContent>
      </Card>
    </div>
  );
}
