"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { MessageKey } from "@/lib/i18n/messages";
import { stageLabel } from "@/lib/pipeline";
import { pivot, type Dashboard } from "@/lib/reports";
import { useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;

/** REP-02: counts only; deals the reader is not staffed on never appear by name (AUTHZ-02 c4). */
export function DashboardView({ messages }: { messages: Messages }) {
  const dashboard = useApiData<Dashboard>("/api/v1/reports/dashboard");
  const data = dashboard.data;
  const grid = pivot(data?.by_stage_and_type ?? []);

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>
            <h1>{messages["dashboard.title"]}</h1>
          </CardTitle>
          <CardDescription>{messages["dashboard.hiddenNote"]}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p>
            {messages["dashboard.total"]}: {data?.total_mandates ?? ""}
          </p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{messages["dashboard.stage"]}</TableHead>
                {grid.types.map((type) => (
                  <TableHead key={type}>{stageLabel(type)}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {grid.stages.map((stage) => (
                <TableRow key={stage}>
                  <TableCell>{stageLabel(stage)}</TableCell>
                  {grid.types.map((type) => (
                    <TableCell key={type}>{grid.cell(stage, type)}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      {data?.weighted_fees_by_quarter ? (
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>{messages["dashboard.feesByQuarter"]}</h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{messages["dashboard.quarter"]}</TableHead>
                  <TableHead>{messages["dashboard.deals"]}</TableHead>
                  <TableHead>{messages["dashboard.expected"]}</TableHead>
                  <TableHead>{messages["dashboard.weighted"]}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.weighted_fees_by_quarter.map((row) => (
                  <TableRow key={row.quarter} data-quarter={row.quarter}>
                    <TableCell>{row.quarter}</TableCell>
                    <TableCell>{row.deals}</TableCell>
                    <TableCell>{row.expected_fees}</TableCell>
                    <TableCell>{row.weighted_fees}</TableCell>
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
