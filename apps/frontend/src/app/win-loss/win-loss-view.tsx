"use client";

import { ScrollRegion } from "@/components/scroll-region";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { MessageKey } from "@/lib/i18n/messages";
import { lostReasonLabelKey, type LostReason } from "@/lib/origination";
import { defaultPeriod, winLossQuery, type WinLoss } from "@/lib/reports";
import { useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;

/** REP-04: pitches, win rate, lost reasons, deal duration and EV/EBITDA by sector for a period. */
export function WinLossView({ messages }: { messages: Messages }) {
  const initial = defaultPeriod(new Date());
  const [from, setFrom] = useState(initial.from);
  const [to, setTo] = useState(initial.to);
  const [query, setQuery] = useState(winLossQuery(initial.from, initial.to));
  const report = useApiData<WinLoss>(`/api/v1/reports/win-loss${query}`);
  const data = report.data;

  function run(event: FormEvent) {
    event.preventDefault();
    setQuery(winLossQuery(from, to));
  }

  function reasonLabel(reason: string) {
    return reason === "unspecified" ? reason : messages[lostReasonLabelKey(reason as LostReason)];
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h1>{messages["winLoss.title"]}</h1>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <form onSubmit={run} className="flex flex-wrap items-end gap-4">
          <Field>
            <FieldLabel htmlFor="wl-from">{messages["winLoss.from"]}</FieldLabel>
            <Input id="wl-from" type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
          </Field>
          <Field>
            <FieldLabel htmlFor="wl-to">{messages["winLoss.to"]}</FieldLabel>
            <Input id="wl-to" type="date" value={to} onChange={(event) => setTo(event.target.value)} />
          </Field>
          <Button type="submit">{messages["winLoss.run"]}</Button>
        </form>
        {data ? (
          <dl className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <dt>{messages["winLoss.pitches"]}</dt>
            <dd>{data.pitches}</dd>
            <dt>{messages["winLoss.winRate"]}</dt>
            <dd>{data.win_rate === null ? "-" : `${data.win_rate} %`}</dd>
            <dt>{messages["winLoss.closedDeals"]}</dt>
            <dd>{data.closed_deals}</dd>
            <dt>{messages["winLoss.duration"]}</dt>
            <dd>{data.average_duration_days ?? "-"}</dd>
          </dl>
        ) : null}
        <CardTitle>
          <h2>{messages["winLoss.lostReasons"]}</h2>
        </CardTitle>
        <ul className="list-disc pl-6">
          {(data?.top_lost_reasons ?? []).map((row) => (
            <li key={row.reason}>
              {reasonLabel(row.reason)}: {row.count}
            </li>
          ))}
        </ul>
        <ScrollRegion label={messages["a11y.scrollRegion"]}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{messages["winLoss.sector"]}</TableHead>
                <TableHead>{messages["dashboard.deals"]}</TableHead>
                <TableHead>{messages["winLoss.evEbitda"]}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data?.ev_ebitda_by_sector ?? []).map((row) => (
                <TableRow key={row.sector_id}>
                  <TableCell>{row.sector}</TableCell>
                  <TableCell>{row.deals}</TableCell>
                  <TableCell>{row.average_ev_ebitda}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ScrollRegion>
      </CardContent>
    </Card>
  );
}
