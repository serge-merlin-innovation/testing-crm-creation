"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { feesQuery, type FeeTerms } from "@/lib/fees";
import { type MessageKey, languageOf } from "@/lib/i18n/messages";
import { formatAmount } from "@/lib/i18n/format";
import { useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;

/** Fee readers only (nav and page gate on fees.read). The fee filter lives here and nowhere else (AUTHZ-06 c3). */
export function FeesView({ messages }: { messages: Messages }) {
  const [minimum, setMinimum] = useState("");
  const query = feesQuery(minimum);
  const rows = useApiData<FeeTerms[]>(`/api/v1/fees/${query}`);

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h1>{messages["fees.pageTitle"]}</h1>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end gap-4">
          <Field>
            <FieldLabel htmlFor="fees-min">{messages["fees.minExpected"]}</FieldLabel>
            <Input id="fees-min" inputMode="decimal" value={minimum} onChange={(event) => setMinimum(event.target.value)} />
          </Field>
          <Button asChild variant="outline">
            <a href={`/api/v1/fees/export${query}`}>{messages["fees.export"]}</a>
          </Button>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{messages["deals.codeName"]}</TableHead>
              <TableHead>{messages["fees.retainer"]}</TableHead>
              <TableHead>{messages["fees.expected"]}</TableHead>
              <TableHead>{messages["fees.final"]}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(rows.data ?? []).map((row) => (
              <TableRow key={row.mandate_id} data-fee-row={row.code_name}>
                <TableCell>
                  <Link href={`/deals/${row.mandate_id}`}>{row.code_name}</Link>
                </TableCell>
                <TableCell>{row.retainer_monthly}</TableCell>
                <TableCell>{formatAmount(row.expected_fee, languageOf(messages))}</TableCell>
                <TableCell>{row.final_fee ?? messages["deals.none"]}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
