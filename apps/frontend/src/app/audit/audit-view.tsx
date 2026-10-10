"use client";

import { useState, type FormEvent } from "react";
import { ScrollRegion } from "@/components/scroll-region";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime } from "@/lib/i18n/format";
import { languageOf, type MessageKey } from "@/lib/i18n/messages";
import { useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;
type Entry = {
  id: number;
  action: string;
  created_at: string;
  user_id: number | null;
  record_type: string | null;
  record_id: string | null;
  ip_address: string | null;
};
type Page = { data: Entry[]; total_count: number };

const FILTERS = ["user_id", "record_type", "record_id", "action"] as const;
type Filters = Record<(typeof FILTERS)[number], string>;
const LABEL: Record<(typeof FILTERS)[number], MessageKey> = {
  user_id: "audit.userId",
  record_type: "audit.recordType",
  record_id: "audit.recordId",
  action: "audit.action",
};

function queryOf(filters: Filters): string {
  const params = new URLSearchParams({ items_per_page: "100" });
  for (const key of FILTERS) {
    if (filters[key].trim()) params.set(key, filters[key].trim());
  }
  return `/api/v1/audit/?${params.toString()}`;
}

/** AUD-01 c3: compliance searches the append-only log by user, record and action. */
export function AuditView({ messages }: { messages: Messages }) {
  const language = languageOf(messages);
  const empty: Filters = { user_id: "", record_type: "", record_id: "", action: "" };
  const [filters, setFilters] = useState<Filters>(empty);
  const [path, setPath] = useState(queryOf(empty));
  const result = useApiData<Page>(path);

  function search(event: FormEvent) {
    event.preventDefault();
    setPath(queryOf(filters));
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h1>{messages["audit.title"]}</h1>
        </CardTitle>
        <CardDescription>{messages["audit.description"]}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <form onSubmit={search}>
          <FieldGroup className="grid gap-4 md:grid-cols-4">
            {FILTERS.map((key) => (
              <Field key={key}>
                <FieldLabel htmlFor={`audit-${key}`}>{messages[LABEL[key]]}</FieldLabel>
                <Input
                  id={`audit-${key}`}
                  value={filters[key]}
                  inputMode={key === "user_id" ? "numeric" : undefined}
                  onChange={(event) => setFilters((current) => ({ ...current, [key]: event.target.value }))}
                />
              </Field>
            ))}
          </FieldGroup>
          <Button type="submit" className="mt-4">
            {messages["common.search"]}
          </Button>
        </form>
        {result.failed ? (
          <Alert variant="destructive">
            <AlertDescription>{messages["common.loadFailed"]}</AlertDescription>
          </Alert>
        ) : null}
        {result.data ? (
          <FieldDescription role="status">
            {messages["audit.results"]} {result.data.total_count}
          </FieldDescription>
        ) : null}
        <div className="overflow-x-auto" tabIndex={0}>
          <ScrollRegion label={messages["a11y.scrollRegion"]}>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{messages["audit.when"]}</TableHead>
                  <TableHead>{messages["audit.userId"]}</TableHead>
                  <TableHead>{messages["audit.action"]}</TableHead>
                  <TableHead>{messages["audit.record"]}</TableHead>
                  <TableHead>{messages["audit.ip"]}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(result.data?.data ?? []).map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell>{formatDateTime(entry.created_at, language)}</TableCell>
                    <TableCell>{entry.user_id ?? ""}</TableCell>
                    <TableCell>{entry.action}</TableCell>
                    <TableCell>{entry.record_type ? `${entry.record_type} ${entry.record_id ?? ""}` : ""}</TableCell>
                    <TableCell>{entry.ip_address ?? ""}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollRegion>
        </div>
      </CardContent>
    </Card>
  );
}
