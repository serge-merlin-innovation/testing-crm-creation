"use client";

import { ScrollRegion } from "@/components/scroll-region";
import { useState, type FormEvent } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fieldErrors, readDetail } from "@/lib/deals";
import type { MessageKey } from "@/lib/i18n/messages";
import { BOARD_STAGES, CRITERION_FIELDS, stageLabel } from "@/lib/pipeline";
import { sendJson, useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;
type Criterion = { id: number; stage: string; kind: string; value: string | null; description: string };

const PATH = "/api/v1/stage-criteria/";

export function StageCriteriaView({ messages }: { messages: Messages }) {
  const criteria = useApiData<Criterion[]>(PATH);
  const [stage, setStage] = useState<string>(BOARD_STAGES[0]);
  const [kind, setKind] = useState("link_label");
  const [label, setLabel] = useState("");
  const [field, setField] = useState<string>(CRITERION_FIELDS[0].value);
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    const value = kind === "link_label" ? label : kind === "field" ? field : null;
    const result = await sendJson(PATH, "POST", { stage, kind, value });
    if (result.status === 201) {
      setLabel("");
      await criteria.reload();
      return;
    }
    const inline = fieldErrors(result.body);
    setErrors(Object.keys(inline).length ? inline : { form: readDetail(result.body, messages["common.saveFailed"]) });
  }

  async function remove(id: number) {
    await sendJson(`${PATH}${id}`, "DELETE");
    await criteria.reload();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h1>{messages["criteria.title"]}</h1>
        </CardTitle>
        <CardDescription>{messages["criteria.description"]}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ScrollRegion label={messages["a11y.scrollRegion"]}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{messages["deals.stage"]}</TableHead>
                <TableHead>{messages["criteria.criterion"]}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(criteria.data ?? []).map((criterion) => (
                <TableRow key={criterion.id}>
                  <TableCell>{stageLabel(criterion.stage)}</TableCell>
                  <TableCell>{criterion.description}</TableCell>
                  <TableCell>
                    <Button type="button" variant="outline" size="sm" onClick={() => void remove(criterion.id)}>
                      {messages["criteria.remove"]}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ScrollRegion>
        <form onSubmit={(event) => void add(event)}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="criterion-stage">{messages["deals.stage"]}</FieldLabel>
              <Select value={stage} onValueChange={setStage}>
                <SelectTrigger id="criterion-stage">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {BOARD_STAGES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {stageLabel(value)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field>
              <FieldLabel htmlFor="criterion-kind">{messages["criteria.kind"]}</FieldLabel>
              <Select value={kind} onValueChange={setKind}>
                <SelectTrigger id="criterion-kind">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="link_label">{messages["criteria.linkLabel"]}</SelectItem>
                  <SelectItem value="field">{messages["criteria.field"]}</SelectItem>
                  <SelectItem value="kyc_engagement">{messages["criteria.kyc"]}</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            {kind === "link_label" ? (
              <Field>
                <FieldLabel htmlFor="criterion-label">{messages["criteria.label"]}</FieldLabel>
                <Input id="criterion-label" value={label} onChange={(event) => setLabel(event.target.value)} />
                <FieldError>{errors.value}</FieldError>
              </Field>
            ) : null}
            {kind === "field" ? (
              <Field>
                <FieldLabel htmlFor="criterion-field">{messages["criteria.field"]}</FieldLabel>
                <Select value={field} onValueChange={setField}>
                  <SelectTrigger id="criterion-field">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CRITERION_FIELDS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldError>{errors.value}</FieldError>
              </Field>
            ) : null}
            {errors.form ? (
              <Alert variant="destructive">
                <AlertDescription>{errors.form}</AlertDescription>
              </Alert>
            ) : null}
            <Button type="submit">{messages["criteria.add"]}</Button>
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  );
}
