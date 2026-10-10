"use client";

import { ScrollRegion } from "@/components/scroll-region";
import { useState, type FormEvent } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { RecordTimeline } from "@/components/record-timeline";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Field,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { toggle, type BuyerGrid } from "@/lib/buyers";
import { fieldErrors, readDetail, type Mandate } from "@/lib/deals";
import { type MessageKey, languageOf } from "@/lib/i18n/messages";
import { formatAmount, formatIsoDate } from "@/lib/i18n/format";
import {
  earlierVersions,
  FINANCING,
  FINANCING_LABEL,
  FUNNEL_LABEL,
  localToIso,
  structureAddsUp,
  type Comparison,
  type FinancingCertainty,
  type FunnelStep,
  type LetterResult,
  type OfferRound,
  type TemplateName,
} from "@/lib/process";
import { sendJson, useApiData } from "@/lib/use-api";
import { apiFetch } from "@/services/api";

type Messages = Record<MessageKey, string>;

async function download(
  path: string,
  init: RequestInit,
  filename: string,
): Promise<boolean> {
  const response = await apiFetch(path, init).catch(() => null);
  if (!response?.ok) return false;
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
  return true;
}

function OfferForm({
  mandate,
  onSaved,
  messages,
}: {
  mandate: Mandate;
  onSaved: () => Promise<void>;
  messages: Messages;
}) {
  const grid = useApiData<BuyerGrid>(`/api/v1/mandates/${mandate.id}/buyers`);
  const [buyerId, setBuyerId] = useState("");
  const [round, setRound] = useState<OfferRound>("indicative");
  const [ev, setEv] = useState("");
  const [equity, setEquity] = useState("");
  const [cash, setCash] = useState("100");
  const [earnOut, setEarnOut] = useState("0");
  const [vendorLoan, setVendorLoan] = useState("0");
  const [rollover, setRollover] = useState("0");
  const [conditions, setConditions] = useState("");
  const [financing, setFinancing] = useState<FinancingCertainty>("committed");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const parts = [cash, earnOut, vendorLoan, rollover];

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    if (!structureAddsUp(parts)) {
      setErrors({ cash_pct: messages["offers.structureTotal"] });
      return;
    }
    const response = await sendJson(
      `/api/v1/mandates/${mandate.id}/offers`,
      "POST",
      {
        buyer_id: Number(buyerId),
        round,
        ev,
        equity_value: equity,
        cash_pct: cash,
        earn_out_pct: earnOut,
        vendor_loan_pct: vendorLoan,
        rollover_pct: rollover,
        conditions,
        financing_certainty: financing,
      },
    );
    if (response.status !== 201) {
      const found = fieldErrors(response.body);
      setErrors(
        Object.keys(found).length
          ? found
          : { form: readDetail(response.body, messages["common.saveFailed"]) },
      );
      return;
    }
    setEv("");
    setEquity("");
    await onSaved();
  }

  const percent = (
    id: string,
    label: MessageKey,
    value: string,
    set: (v: string) => void,
  ) => (
    <Field>
      <FieldLabel htmlFor={id}>{messages[label]}</FieldLabel>
      <Input
        id={id}
        inputMode="decimal"
        value={value}
        onChange={(event) => set(event.target.value)}
      />
    </Field>
  );

  return (
    <form onSubmit={save} aria-label={messages["offers.add"]}>
      <FieldGroup>
        <div className="grid gap-4 md:grid-cols-3">
          <Field>
            <FieldLabel htmlFor="offer-buyer">
              {messages["offers.buyer"]}
            </FieldLabel>
            <Select value={buyerId} onValueChange={setBuyerId}>
              <SelectTrigger id="offer-buyer">
                <SelectValue placeholder={messages["offers.pickBuyer"]} />
              </SelectTrigger>
              <SelectContent>
                {(grid.data?.buyers ?? []).map((buyer) => (
                  <SelectItem key={buyer.id} value={String(buyer.id)}>
                    {buyer.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel htmlFor="offer-round">
              {messages["offers.round"]}
            </FieldLabel>
            <Select
              value={round}
              onValueChange={(value) => setRound(value as OfferRound)}
            >
              <SelectTrigger id="offer-round">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="indicative">
                  {messages["offers.round.indicative"]}
                </SelectItem>
                <SelectItem value="binding">
                  {messages["offers.round.binding"]}
                </SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel htmlFor="offer-financing">
              {messages["offers.financing"]}
            </FieldLabel>
            <Select
              value={financing}
              onValueChange={(value) =>
                setFinancing(value as FinancingCertainty)
              }
            >
              <SelectTrigger id="offer-financing">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {FINANCING.map((value) => (
                  <SelectItem key={value} value={value}>
                    {messages[FINANCING_LABEL[value]]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel htmlFor="offer-ev">{messages["offers.ev"]}</FieldLabel>
            <Input
              id="offer-ev"
              inputMode="decimal"
              value={ev}
              onChange={(event) => setEv(event.target.value)}
              required
            />
            {errors.ev ? <FieldError>{errors.ev}</FieldError> : null}
          </Field>
          <Field>
            <FieldLabel htmlFor="offer-equity">
              {messages["offers.equity"]}
            </FieldLabel>
            <Input
              id="offer-equity"
              inputMode="decimal"
              value={equity}
              onChange={(event) => setEquity(event.target.value)}
              required
            />
          </Field>
        </div>
        <div className="grid gap-4 md:grid-cols-4">
          {percent("offer-cash", "offers.cash", cash, setCash)}
          {percent("offer-earn-out", "offers.earnOut", earnOut, setEarnOut)}
          {percent(
            "offer-vendor-loan",
            "offers.vendorLoan",
            vendorLoan,
            setVendorLoan,
          )}
          {percent("offer-rollover", "offers.rollover", rollover, setRollover)}
        </div>
        {errors.cash_pct ? <FieldError>{errors.cash_pct}</FieldError> : null}
        <Field>
          <FieldLabel htmlFor="offer-conditions">
            {messages["offers.conditions"]}
          </FieldLabel>
          <Textarea
            id="offer-conditions"
            value={conditions}
            onChange={(event) => setConditions(event.target.value)}
          />
        </Field>
        {errors.form ? <FieldError>{errors.form}</FieldError> : null}
        <Button type="submit" disabled={!buyerId}>
          {messages["offers.save"]}
        </Button>
      </FieldGroup>
    </form>
  );
}

function Deadlines({
  mandate,
  data,
  onSaved,
  messages,
}: {
  mandate: Mandate;
  data: Comparison;
  onSaved: () => Promise<void>;
  messages: Messages;
}) {
  const [indicative, setIndicative] = useState("");
  const [binding, setBinding] = useState("");

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await sendJson(`/api/v1/mandates/${mandate.id}/bid-deadlines`, "PUT", {
      indicative_at: localToIso(indicative) ?? data.deadlines.indicative_at,
      binding_at: localToIso(binding) ?? data.deadlines.binding_at,
    });
    await onSaved();
  }

  return (
    <form
      onSubmit={save}
      aria-label={messages["offers.deadlines"]}
      className="flex flex-wrap items-end gap-4"
    >
      <Field>
        <FieldLabel htmlFor="deadline-indicative">
          {messages["offers.deadline.indicative"]}
        </FieldLabel>
        <Input
          id="deadline-indicative"
          type="datetime-local"
          value={indicative}
          onChange={(event) => setIndicative(event.target.value)}
        />
      </Field>
      <Field>
        <FieldLabel htmlFor="deadline-binding">
          {messages["offers.deadline.binding"]}
        </FieldLabel>
        <Input
          id="deadline-binding"
          type="datetime-local"
          value={binding}
          onChange={(event) => setBinding(event.target.value)}
        />
      </Field>
      <Button type="submit" variant="outline">
        {messages["offers.deadlines.save"]}
      </Button>
      <p>
        {messages["offers.deadline.indicative"]}:{" "}
        {data.deadlines.indicative_at ?? "-"} /{" "}
        {messages["offers.deadline.binding"]}:{" "}
        {data.deadlines.binding_at ?? "-"}
      </p>
    </form>
  );
}

export function OffersTab({
  mandate,
  messages,
}: {
  mandate: Mandate;
  messages: Messages;
}) {
  const comparison = useApiData<Comparison>(
    `/api/v1/mandates/${mandate.id}/offers`,
  );
  const data = comparison.data;

  return (
    <div className="flex flex-col gap-4">
      {data && mandate.can_edit ? (
        <Deadlines
          mandate={mandate}
          data={data}
          onSaved={comparison.reload}
          messages={messages}
        />
      ) : null}
      {mandate.can_edit ? (
        <OfferForm
          mandate={mandate}
          onSaved={comparison.reload}
          messages={messages}
        />
      ) : null}
      <Separator />
      {data ? (
        <p>
          {data.ebitda
            ? `${messages["offers.ebitda"]} ${data.ebitda_year}: ${data.ebitda}`
            : messages["offers.noEbitda"]}
        </p>
      ) : null}
      {data && data.bids.length === 0 ? (
        <p>{messages["offers.empty"]}</p>
      ) : null}
      {data && data.bids.length > 0 ? (
        <ScrollRegion label={messages["a11y.scrollRegion"]}>
          <Table aria-label={messages["offers.comparison"]}>
            <TableHeader>
              <TableRow>
                <TableHead>{messages["offers.buyer"]}</TableHead>
                <TableHead>{messages["offers.round"]}</TableHead>
                <TableHead>{messages["offers.ev"]}</TableHead>
                <TableHead>{messages["offers.equity"]}</TableHead>
                <TableHead>{messages["offers.multiple"]}</TableHead>
                <TableHead>{messages["offers.structure"]}</TableHead>
                <TableHead>{messages["offers.conditions"]}</TableHead>
                <TableHead>{messages["offers.financing"]}</TableHead>
                <TableHead>{messages["offers.versions"]}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.bids.map((bid) => (
                <TableRow key={bid.id} data-buyer={bid.buyer_name}>
                  <TableCell>
                    {bid.buyer_name}{" "}
                    {bid.late ? (
                      <Badge variant="destructive">
                        {messages["offers.late"]}
                      </Badge>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    {
                      messages[
                        bid.round === "binding"
                          ? "offers.round.binding"
                          : "offers.round.indicative"
                      ]
                    }
                  </TableCell>
                  <TableCell>{formatAmount(bid.ev, languageOf(messages), 1)}</TableCell>
                  <TableCell>{bid.equity_value}</TableCell>
                  <TableCell>
                    {bid.ev_ebitda ? `${formatAmount(bid.ev_ebitda, languageOf(messages), 1)}x` : "-"}
                  </TableCell>
                  <TableCell>
                    {bid.cash_pct}/{bid.earn_out_pct}/{bid.vendor_loan_pct}/
                    {bid.rollover_pct}
                  </TableCell>
                  <TableCell>{bid.conditions}</TableCell>
                  <TableCell>
                    {messages[FINANCING_LABEL[bid.financing_certainty]]}
                  </TableCell>
                  <TableCell>
                    v{bid.version} ({bid.entered_at.slice(0, 10)})
                    {earlierVersions(data.history, bid).map((old) => (
                      <div key={old.id}>
                        v{old.version}: {formatAmount(old.ev, languageOf(messages), 1)} ({formatIsoDate(old.entered_at, languageOf(messages))})
                      </div>
                    ))}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ScrollRegion>
      ) : null}
    </div>
  );
}

export function FunnelPanel({
  mandate,
  messages,
}: {
  mandate: Mandate;
  messages: Messages;
}) {
  const funnel = useApiData<{ steps: FunnelStep[] }>(
    `/api/v1/mandates/${mandate.id}/funnel`,
  );
  const [failed, setFailed] = useState(false);

  async function exportPdf() {
    setFailed(
      !(await download(
        `/api/v1/mandates/${mandate.id}/funnel.pdf`,
        {},
        `${mandate.code_name}-funnel.pdf`,
      )),
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <ScrollRegion label={messages["a11y.scrollRegion"]}>
        <Table aria-label={messages["funnel.title"]}>
          <TableHeader>
            <TableRow>
              <TableHead>{messages["funnel.step"]}</TableHead>
              <TableHead>{messages["funnel.count"]}</TableHead>
              <TableHead>{messages["funnel.conversion"]}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(funnel.data?.steps ?? []).map((step) => (
              <TableRow key={step.key} data-step={step.key}>
                <TableCell>{messages[FUNNEL_LABEL[step.key]]}</TableCell>
                <TableCell>{step.count}</TableCell>
                <TableCell>
                  {step.conversion_pct === null ? "-" : `${step.conversion_pct}%`}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </ScrollRegion>
      <div className="flex gap-2">
        <Button variant="outline" onClick={() => void exportPdf()}>
          {messages["funnel.export"]}
        </Button>
      </div>
      {failed ? <FieldError>{messages["common.saveFailed"]}</FieldError> : null}
    </div>
  );
}

export function LettersTab({
  mandate,
  messages,
}: {
  mandate: Mandate;
  messages: Messages;
}) {
  const grid = useApiData<BuyerGrid>(`/api/v1/mandates/${mandate.id}/buyers`);
  const names = useApiData<TemplateName[]>("/api/v1/templates/names");
  const documents = useApiData<
    {
      id: number;
      kind: string;
      subject: string;
      language: string;
      created_at: string;
    }[]
  >(`/api/v1/mandates/${mandate.id}/documents`);
  const [selected, setSelected] = useState<number[]>([]);
  const [template, setTemplate] = useState("");
  const [result, setResult] = useState<LetterResult | null>(null);
  const [error, setError] = useState("");
  const letters = (names.data ?? []).filter((item) => item.kind === "letter");
  const reports = (names.data ?? []).filter((item) => item.kind === "report");

  async function send() {
    setError("");
    const response = await sendJson(
      `/api/v1/mandates/${mandate.id}/letters`,
      "POST",
      { template_name: template, buyer_ids: selected },
    );
    if (response.status !== 200) {
      setError(readDetail(response.body, messages["common.saveFailed"]));
      return;
    }
    setResult(response.body as LetterResult);
    setSelected([]);
    await documents.reload();
  }

  async function report() {
    setError("");
    const body = reports[0] ? { template_name: reports[0].name } : {};
    const ok = await download(
      `/api/v1/mandates/${mandate.id}/status-report`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
      `${mandate.code_name}-status-report.pdf`,
    );
    if (!ok) setError(messages["common.saveFailed"]);
    await documents.reload();
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-2">
        <Button onClick={() => void report()}>
          {messages["report.generate"]}
        </Button>
      </div>
      <Separator />
      {mandate.can_edit ? (
        <section
          aria-label={messages["letters.title"]}
          className="flex flex-col gap-4"
        >
          <Field>
            <FieldLabel htmlFor="letter-template">
              {messages["letters.template"]}
            </FieldLabel>
            <Select value={template} onValueChange={setTemplate}>
              <SelectTrigger id="letter-template">
                <SelectValue placeholder={messages["letters.pickTemplate"]} />
              </SelectTrigger>
              <SelectContent>
                {letters.map((item) => (
                  <SelectItem key={item.name} value={item.name}>
                    {item.name} ({item.languages.join(", ")})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          {(grid.data?.buyers ?? []).map((buyer) => (
            <Field key={buyer.id} orientation="horizontal">
              <Checkbox
                id={`letter-buyer-${buyer.id}`}
                checked={selected.includes(buyer.id)}
                onCheckedChange={() => setSelected(toggle(selected, buyer.id))}
              />
              <FieldLabel htmlFor={`letter-buyer-${buyer.id}`}>
                {buyer.name}{" "}
                {buyer.contact_name ? `(${buyer.contact_name})` : ""}
              </FieldLabel>
            </Field>
          ))}
          <Button
            onClick={() => void send()}
            disabled={!template || selected.length === 0}
          >
            {messages["letters.send"]}
          </Button>
        </section>
      ) : null}
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {result ? (
        <Alert>
          <AlertTitle>
            {messages["letters.sent"]}:{" "}
            {result.sent
              .map((item) => `${item.buyer_name} (${item.language})`)
              .join(", ") || "-"}
          </AlertTitle>
          {result.excluded.map((item) => (
            <AlertDescription key={item.buyer_id} data-excluded={item.reason}>
              {messages["letters.excluded"]} {item.buyer_name}: {item.message}
            </AlertDescription>
          ))}
        </Alert>
      ) : null}
      <ScrollRegion label={messages["a11y.scrollRegion"]}>
        <Table aria-label={messages["documents.title"]}>
          <TableHeader>
            <TableRow>
              <TableHead>{messages["documents.subject"]}</TableHead>
              <TableHead>{messages["documents.language"]}</TableHead>
              <TableHead>{messages["documents.date"]}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(documents.data ?? []).map((item) => (
              <TableRow key={item.id}>
                <TableCell>{item.subject}</TableCell>
                <TableCell>{item.language}</TableCell>
                <TableCell>{item.created_at.slice(0, 10)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </ScrollRegion>
    </div>
  );
}

type DealTask = {
  id: number;
  title: string;
  due_date: string;
  assignee_name: string;
  completed_at: string | null;
  overdue: boolean;
};

export function ActivitiesTasksTab({
  mandate,
  messages,
}: {
  mandate: Mandate;
  messages: Messages;
}) {
  const tasks = useApiData<DealTask[]>(`/api/v1/mandates/${mandate.id}/tasks`);

  return (
    <div className="flex flex-col gap-4">
      <RecordTimeline recordType="mandate" recordId={mandate.id} messages={messages} />
      <Separator />
      <section aria-label={messages["deal.tasks"]}>
        <h2>{messages["deal.tasks"]}</h2>
        {(tasks.data ?? []).length === 0 ? (
          <p>{messages["deal.noTasks"]}</p>
        ) : null}
        <ul className="flex flex-col gap-2">
          {(tasks.data ?? []).map((task) => (
            <li key={task.id}>
              {task.title}, {task.assignee_name}, {formatIsoDate(task.due_date, languageOf(messages))}
              {task.overdue ? (
                <Badge variant="destructive">{messages["deal.overdue"]}</Badge>
              ) : null}
              {task.completed_at ? (
                <Badge variant="outline">{messages["deal.done"]}</Badge>
              ) : null}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
