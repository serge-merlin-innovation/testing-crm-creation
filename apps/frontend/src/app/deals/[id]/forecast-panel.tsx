"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import type { MessageKey } from "@/lib/i18n/messages";
import { sendJson, useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;
type Forecast = { probability: number; probability_is_default: boolean; expected_closing_date: string | null };

/** Close probability and expected closing date, the inputs of the dashboard and fee forecast (REP-02/03). */
export function ForecastPanel({ mandateId, canEdit, messages }: { mandateId: number; canEdit: boolean; messages: Messages }) {
  const forecast = useApiData<Forecast>(`/api/v1/mandates/${mandateId}/forecast`);
  return forecast.data ? (
    <ForecastForm
      key={JSON.stringify(forecast.data)}
      mandateId={mandateId}
      initial={forecast.data}
      canEdit={canEdit}
      onSaved={forecast.reload}
      messages={messages}
    />
  ) : null;
}

function ForecastForm({
  mandateId,
  initial,
  canEdit,
  onSaved,
  messages,
}: {
  mandateId: number;
  initial: Forecast;
  canEdit: boolean;
  onSaved: () => Promise<void>;
  messages: Messages;
}) {
  const [probability, setProbability] = useState(initial.probability_is_default ? "" : String(initial.probability));
  const [closing, setClosing] = useState(initial.expected_closing_date ?? "");

  async function save(event: FormEvent) {
    event.preventDefault();
    await sendJson(`/api/v1/mandates/${mandateId}/forecast`, "PUT", {
      probability: probability === "" ? null : Number(probability),
      expected_closing_date: closing === "" ? null : closing,
    });
    await onSaved();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>{messages["forecast.dealTitle"]}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={save}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="forecast-probability">{messages["forecast.probability"]}</FieldLabel>
              <Input
                id="forecast-probability"
                inputMode="numeric"
                placeholder={`${messages["forecast.stageDefault"]}: ${initial.probability}`}
                value={probability}
                disabled={!canEdit}
                onChange={(event) => setProbability(event.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="forecast-closing">{messages["forecast.closingDate"]}</FieldLabel>
              <Input
                id="forecast-closing"
                type="date"
                value={closing}
                disabled={!canEdit}
                onChange={(event) => setClosing(event.target.value)}
              />
            </Field>
            {canEdit ? <Button type="submit">{messages["forecast.save"]}</Button> : null}
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  );
}
