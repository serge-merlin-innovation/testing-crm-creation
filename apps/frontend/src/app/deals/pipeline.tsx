"use client";

import { useState } from "react";
import Link from "next/link";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { DEAL_STAGES, MANDATE_TYPES } from "@/lib/deals";
import { type MessageKey, languageOf } from "@/lib/i18n/messages";
import { formatAmount } from "@/lib/i18n/format";
import {
  ANY,
  BOARD_STAGES,
  blockedReasons,
  dealsQuery,
  firstError,
  groupByStage,
  isBackward,
  NO_FILTERS,
  partnerOptions,
  sortDeals,
  stageLabel,
  toggleSort,
  type DealFilters,
  type DealListItem,
  type Sort,
  type SortKey,
} from "@/lib/pipeline";
import { sendJson, useApiData } from "@/lib/use-api";
import { apiFetch } from "@/services/api";

type Messages = Record<MessageKey, string>;
type Option = { id: number; label?: string };
type Pending = { deal: DealListItem; stage: string };

function Filter({
  id,
  label,
  value,
  onChange,
  options,
  anyLabel,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  anyLabel: string;
}) {
  return (
    <Field>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>{anyLabel}</SelectItem>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  );
}

export function Pipeline({ messages, search }: { messages: Messages; search: string }) {
  const [filters, setFilters] = useState<DealFilters>(NO_FILTERS);
  const deals = useApiData<DealListItem[]>(`/api/v1/mandates/${dealsQuery(filters, search)}`);
  const everything = useApiData<DealListItem[]>("/api/v1/mandates/");
  const sectors = useApiData<Option[]>("/api/v1/picklists/?kind=sector");
  const [sort, setSort] = useState<Sort>({ key: "code_name", descending: false });
  const [pending, setPending] = useState<Pending | null>(null);
  const [reason, setReason] = useState("");
  const [blocked, setBlocked] = useState<{ codeName: string; reasons: string[] } | null>(null);

  const visible = deals.data ?? [];
  const columns = groupByStage(visible);
  const set = (key: keyof DealFilters) => (value: string) => setFilters({ ...filters, [key]: value });

  async function move(deal: DealListItem, stage: string, why?: string) {
    setBlocked(null);
    const fresh = await fetchVersion(deal.id);
    const result = await sendJson(`/api/v1/mandates/${deal.id}/stage`, "POST", {
      version: fresh,
      stage,
      ...(why ? { reason: why } : {}),
    });
    if (result.status !== 200) {
      setBlocked({
        codeName: deal.code_name,
        reasons: blockedReasons(result.body) ?? [firstError(result.body) ?? messages["common.saveFailed"]],
      });
    }
    await deals.reload();
  }

  function drop(stage: string, id: number) {
    const deal = visible.find((item) => item.id === id);
    if (!deal || deal.stage === stage) return;
    if (isBackward(deal.stage, stage)) {
      setReason("");
      setPending({ deal, stage });
      return;
    }
    void move(deal, stage);
  }

  const header = (key: SortKey, label: string) => (
    <TableHead>
      <Button type="button" variant="ghost" size="sm" onClick={() => setSort(toggleSort(sort, key))}>
        {label}
        {sort.key === key ? (sort.descending ? " ↓" : " ↑") : ""}
      </Button>
    </TableHead>
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Filter
          id="filter-partner"
          label={messages["pipeline.partner"]}
          value={filters.partner_id}
          onChange={set("partner_id")}
          options={partnerOptions(everything.data ?? [])}
          anyLabel={messages["pipeline.any"]}
        />
        <Filter
          id="filter-type"
          label={messages["deals.type"]}
          value={filters.type}
          onChange={set("type")}
          options={MANDATE_TYPES.map((value) => ({ value, label: stageLabel(value) }))}
          anyLabel={messages["pipeline.any"]}
        />
        <Filter
          id="filter-sector"
          label={messages["deals.sector"]}
          value={filters.sector_id}
          onChange={set("sector_id")}
          options={(sectors.data ?? []).map((sector) => ({ value: String(sector.id), label: sector.label ?? "" }))}
          anyLabel={messages["pipeline.any"]}
        />
        <Filter
          id="filter-stage"
          label={messages["deals.stage"]}
          value={filters.stage}
          onChange={set("stage")}
          options={DEAL_STAGES.map((value) => ({ value, label: stageLabel(value) }))}
          anyLabel={messages["pipeline.any"]}
        />
      </div>

      {blocked ? (
        <Alert variant="destructive">
          <AlertTitle>
            {messages["pipeline.blocked"]} {blocked.codeName}
          </AlertTitle>
          <AlertDescription>
            <ul className="flex flex-col gap-1">
              {blocked.reasons.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      ) : null}

      <Tabs defaultValue="board">
        <TabsList>
          <TabsTrigger value="board">{messages["pipeline.board"]}</TabsTrigger>
          <TabsTrigger value="list">{messages["pipeline.list"]}</TabsTrigger>
        </TabsList>
        <TabsContent value="board">
          <div className="flex gap-2 overflow-x-auto pb-2">
            {BOARD_STAGES.map((stage) => (
              <section
                key={stage}
                aria-label={stageLabel(stage)}
                data-stage={stage}
                className="flex w-56 shrink-0 flex-col gap-2"
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault();
                  drop(stage, Number(event.dataTransfer.getData("text/plain")));
                }}
              >
                <h2 className="text-sm font-medium">
                  {stageLabel(stage)} <Badge variant="outline">{columns[stage]?.length ?? 0}</Badge>
                </h2>
                {(columns[stage] ?? []).map((deal) => (
                  <Card
                    key={deal.id}
                    draggable
                    data-deal={deal.code_name}
                    onDragStart={(event) => {
                      event.dataTransfer.setData("text/plain", String(deal.id));
                    }}
                    className="cursor-grab"
                  >
                    <CardHeader>
                      <CardTitle>
                        <Button asChild variant="link">
                          <Link href={`/deals/${deal.id}`}>{deal.code_name}</Link>
                        </Button>
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="text-muted-foreground text-xs">{deal.lead_partner_name}</CardContent>
                  </Card>
                ))}
              </section>
            ))}
          </div>
        </TabsContent>
        <TabsContent value="list">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  {header("code_name", messages["deals.codeName"])}
                  {header("stage", messages["deals.stage"])}
                  {header("lead_partner_name", messages["deals.leadPartner"])}
                  {header("estimated_ev", messages["deals.ev"])}
                  {header("stage_changed_at", messages["pipeline.since"])}
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortDeals(visible, sort).map((deal) => (
                  <TableRow key={deal.id}>
                    <TableCell>
                      <Button asChild variant="link">
                        <Link href={`/deals/${deal.id}`}>{deal.code_name}</Link>
                      </Button>
                    </TableCell>
                    <TableCell>{stageLabel(deal.stage)}</TableCell>
                    <TableCell>{deal.lead_partner_name}</TableCell>
                    <TableCell>{formatAmount(deal.estimated_ev, languageOf(messages))}</TableCell>
                    <TableCell>{deal.stage_changed_at?.slice(0, 10) ?? ""}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
      </Tabs>
      {deals.data?.length === 0 ? <p>{messages["deals.empty"]}</p> : null}

      <AlertDialog open={pending !== null} onOpenChange={(open) => (open ? null : setPending(null))}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{messages["pipeline.backTitle"]}</AlertDialogTitle>
            <AlertDialogDescription>
              {pending ? `${pending.deal.code_name}: ${stageLabel(pending.deal.stage)} → ${stageLabel(pending.stage)}` : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Field>
            <FieldLabel htmlFor="move-reason">{messages["pipeline.reason"]}</FieldLabel>
            <Textarea id="move-reason" value={reason} onChange={(event) => setReason(event.target.value)} />
          </Field>
          <AlertDialogFooter>
            <AlertDialogCancel>{messages["pipeline.cancel"]}</AlertDialogCancel>
            <Button
              type="button"
              disabled={!reason.trim()}
              onClick={() => {
                if (!pending) return;
                const { deal, stage } = pending;
                setPending(null);
                void move(deal, stage, reason.trim());
              }}
            >
              {messages["pipeline.move"]}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

async function fetchVersion(id: number): Promise<number | null> {
  const response = await apiFetch(`/api/v1/mandates/${id}`).catch(() => null);
  if (!response?.ok) return null;
  return ((await response.json()) as { version: number }).version;
}
