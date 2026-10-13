"use client";

import { ScrollRegion } from "@/components/scroll-region";
import { StepUpExport } from "@/components/step-up-export";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { MessageKey } from "@/lib/i18n/messages";
import type { FeeForecast } from "@/lib/reports";
import { useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;

const EXPORT_PATH = "/api/v1/reports/fee-forecast/export";

/** REP-03: forecast vs actual per month, exportable to Excel. */
export function ForecastView({ messages }: { messages: Messages }) {
  const forecast = useApiData<FeeForecast>("/api/v1/reports/fee-forecast");

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h1>{messages["forecast.title"]}</h1>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div>
          <StepUpExport path={EXPORT_PATH} filename="fee-forecast.xlsx" label={messages["forecast.export"]} messages={messages} />
        </div>
        <ScrollRegion label={messages["a11y.scrollRegion"]}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{messages["forecast.month"]}</TableHead>
                <TableHead>{messages["forecast.retainers"]}</TableHead>
                <TableHead>{messages["forecast.successFees"]}</TableHead>
                <TableHead>{messages["forecast.total"]}</TableHead>
                <TableHead>{messages["forecast.invoiced"]}</TableHead>
                <TableHead>{messages["forecast.paid"]}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(forecast.data?.months ?? []).map((row) => (
                <TableRow key={row.month} data-month={row.month}>
                  <TableCell>{row.month}</TableCell>
                  <TableCell>{row.retainers}</TableCell>
                  <TableCell>{row.success_fees}</TableCell>
                  <TableCell>{row.forecast_total}</TableCell>
                  <TableCell>{row.actual_invoiced}</TableCell>
                  <TableCell>{row.actual_paid}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ScrollRegion>
      </CardContent>
    </Card>
  );
}
