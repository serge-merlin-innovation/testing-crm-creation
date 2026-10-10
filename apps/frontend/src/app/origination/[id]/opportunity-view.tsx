"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableRow } from "@/components/ui/table";
import { fieldErrors, readDetail } from "@/lib/deals";
import { FEES_READ } from "@/lib/fees";
import { type MessageKey, languageOf } from "@/lib/i18n/messages";
import { formatAmount, formatIsoDate } from "@/lib/i18n/format";
import {
  credentialQuery,
  isClosed,
  LOST_REASONS,
  lostReasonLabelKey,
  MOVABLE_STAGES,
  stageLabelKey,
  stagePayload,
  type Credential,
  type Opportunity,
  type OpportunityStage,
} from "@/lib/origination";
import { sendJson, useApiData } from "@/lib/use-api";
import { apiFetch } from "@/services/api";
import { Choice } from "../origination-view";

type Messages = Record<MessageKey, string>;
type Option = { id: number; label?: string };
type Candidate = { user_id: number; name: string; role_name: string | null };

const ANY = "any";

export function OpportunityView({
  initial,
  permissions,
  messages,
}: {
  initial: Opportunity;
  permissions: string[];
  messages: Messages;
}) {
  const [opportunity, setOpportunity] = useState(initial);
  const base = `/api/v1/origination/opportunities/${opportunity.id}`;
  const closed = isClosed(opportunity);
  const canEdit = !closed && permissions.includes("deals.edit_staffed");
  const isOwner = opportunity.is_owner;

  async function reload() {
    const result = await sendJsonGet(base);
    if (result) setOpportunity(result);
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>
            <h1>{opportunity.company_name}</h1>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {opportunity.conflict_warning ? (
            <Alert variant="destructive">
              <AlertDescription>{messages["origination.conflictWarning"]}</AlertDescription>
            </Alert>
          ) : null}
          <Table>
            <TableBody>
              <Row label={messages["origination.stage"]} value={messages[stageLabelKey(opportunity.stage)]} />
              <Row label={messages["deals.type"]} value={messages[`origination.type.${opportunity.type}` as MessageKey]} />
              <Row
                label={messages["origination.trigger"]}
                value={messages[`origination.trigger.${opportunity.trigger}` as MessageKey]}
              />
              <Row label={messages["origination.ev"]} value={formatAmount(opportunity.estimated_ev, languageOf(messages))} />
              <Row label={messages["origination.probability"]} value={String(opportunity.probability)} />
              <Row label={messages["origination.owner"]} value={opportunity.owner_name} />
              {opportunity.lost_reason ? (
                <Row label={messages["origination.lostReason"]} value={messages[lostReasonLabelKey(opportunity.lost_reason)]} />
              ) : null}
              {opportunity.competitor_advisor ? (
                <Row label={messages["origination.competitor"]} value={opportunity.competitor_advisor} />
              ) : null}
              {opportunity.revisit_date ? (
                <Row label={messages["origination.revisitDate"]} value={formatIsoDate(opportunity.revisit_date, languageOf(messages))} />
              ) : null}
            </TableBody>
          </Table>
          {opportunity.mandate_id ? (
            <Button asChild variant="outline">
              <Link href={`/deals/${opportunity.mandate_id}`}>{messages["origination.openMandate"]}</Link>
            </Button>
          ) : null}
        </CardContent>
      </Card>

      {canEdit ? <StageCard messages={messages} base={base} current={opportunity.stage} onMoved={setOpportunity} /> : null}
      {canEdit && isOwner && permissions.includes("mandates.create") ? (
        <WinCard messages={messages} base={base} onWon={() => void reload()} />
      ) : null}
      <TeamCard messages={messages} base={base} opportunity={opportunity} canInvite={canEdit && isOwner} onChange={setOpportunity} />
      <LinksCard messages={messages} base={base} opportunity={opportunity} canEdit={canEdit} onChange={() => void reload()} />
      <CredentialsCard messages={messages} base={base} opportunity={opportunity} canEdit={canEdit} onChange={() => void reload()} />
      {permissions.includes(FEES_READ) ? (
        <FeeDraftCard messages={messages} base={base} opportunity={opportunity} canEdit={canEdit} />
      ) : null}
    </div>
  );
}

async function sendJsonGet(path: string): Promise<Opportunity | null> {
  const response = await apiFetch(path).catch(() => null);
  return response?.ok ? ((await response.json()) as Opportunity) : null;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <TableRow>
      <TableHead>{label}</TableHead>
      <TableCell>{value}</TableCell>
    </TableRow>
  );
}

function StageCard({
  messages,
  base,
  current,
  onMoved,
}: {
  messages: Messages;
  base: string;
  current: OpportunityStage;
  onMoved: (opportunity: Opportunity) => void;
}) {
  const [stage, setStage] = useState<string>(current);
  const [lostReason, setLostReason] = useState("");
  const [competitor, setCompetitor] = useState("");
  const [revisitDate, setRevisitDate] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function move(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    const result = await sendJson(
      `${base}/stage`,
      "POST",
      stagePayload(stage as OpportunityStage, { lostReason, competitor, revisitDate }),
    );
    if (result.status === 200) {
      onMoved(result.body as Opportunity);
      return;
    }
    const inline = fieldErrors(result.body);
    setErrors(Object.keys(inline).length ? inline : { form: readDetail(result.body, messages["common.saveFailed"]) });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>{messages["origination.move"]}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={(event) => void move(event)}>
          <FieldGroup>
            <Choice
              id="opportunity-stage"
              label={messages["origination.stage"]}
              value={stage}
              onChange={setStage}
              options={MOVABLE_STAGES.map((value) => ({ value, label: messages[stageLabelKey(value)] }))}
              error={errors.stage}
            />
            {stage === "lost" ? (
              <>
                <Choice
                  id="opportunity-lost-reason"
                  label={messages["origination.lostReason"]}
                  value={lostReason}
                  onChange={setLostReason}
                  options={LOST_REASONS.map((value) => ({ value, label: messages[lostReasonLabelKey(value)] }))}
                  error={errors.lost_reason}
                />
                <Field>
                  <FieldLabel htmlFor="opportunity-competitor">{messages["origination.competitor"]}</FieldLabel>
                  <Input id="opportunity-competitor" value={competitor} onChange={(event) => setCompetitor(event.target.value)} />
                </Field>
              </>
            ) : null}
            {stage === "on_hold" ? (
              <Field>
                <FieldLabel htmlFor="opportunity-revisit">{messages["origination.revisitDate"]}</FieldLabel>
                <Input
                  id="opportunity-revisit"
                  type="date"
                  value={revisitDate}
                  onChange={(event) => setRevisitDate(event.target.value)}
                  aria-invalid={Boolean(errors.revisit_date)}
                />
                <FieldError>{errors.revisit_date}</FieldError>
              </Field>
            ) : null}
            {errors.form ? (
              <Alert variant="destructive">
                <AlertDescription>{errors.form}</AlertDescription>
              </Alert>
            ) : null}
            <Button type="submit">{messages["origination.move"]}</Button>
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  );
}

function WinCard({ messages, base, onWon }: { messages: Messages; base: string; onWon: () => void }) {
  const [codeName, setCodeName] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function win(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    const result = await sendJson(`${base}/win`, "POST", { code_name: codeName });
    if (result.status === 201) {
      onWon();
      return;
    }
    const inline = fieldErrors(result.body);
    setErrors(Object.keys(inline).length ? inline : { code_name: readDetail(result.body, messages["common.saveFailed"]) });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>{messages["origination.win"]}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={(event) => void win(event)}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="opportunity-code-name">{messages["origination.winCodeName"]}</FieldLabel>
              <Input
                id="opportunity-code-name"
                value={codeName}
                onChange={(event) => setCodeName(event.target.value)}
                aria-invalid={Boolean(errors.code_name)}
              />
              <FieldError>{errors.code_name ?? errors.sector_id}</FieldError>
            </Field>
            <Button type="submit">{messages["origination.win"]}</Button>
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  );
}

function TeamCard({
  messages,
  base,
  opportunity,
  canInvite,
  onChange,
}: {
  messages: Messages;
  base: string;
  opportunity: Opportunity;
  canInvite: boolean;
  onChange: (opportunity: Opportunity) => void;
}) {
  const candidates = useApiData<Candidate[]>(canInvite ? `${base}/candidates` : null);
  const [userId, setUserId] = useState("");

  async function invite() {
    if (!userId) return;
    const result = await sendJson(`${base}/members`, "POST", { user_id: Number(userId) });
    if (result.status === 201) {
      onChange(result.body as Opportunity);
      setUserId("");
      await candidates.reload();
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>{messages["origination.team"]}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ul className="flex flex-col gap-1" aria-label={messages["origination.team"]}>
          {(opportunity.members ?? []).map((member) => (
            <li key={member.user_id}>
              {member.name} {member.role_name ? <Badge variant="secondary">{member.role_name}</Badge> : null}
            </li>
          ))}
        </ul>
        {canInvite ? (
          <div className="flex flex-wrap items-end gap-2">
            <Choice
              id="opportunity-colleague"
              label={messages["origination.colleague"]}
              value={userId}
              onChange={setUserId}
              options={(candidates.data ?? []).map((user) => ({ value: String(user.user_id), label: user.name }))}
            />
            <Button type="button" variant="outline" onClick={() => void invite()}>
              {messages["origination.invite"]}
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function LinksCard({
  messages,
  base,
  opportunity,
  canEdit,
  onChange,
}: {
  messages: Messages;
  base: string;
  opportunity: Opportunity;
  canEdit: boolean;
  onChange: () => void;
}) {
  const [label, setLabel] = useState("Pitch deck");
  const [url, setUrl] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    const result = await sendJson(`${base}/links`, "POST", { label, url });
    if (result.status === 201) {
      setUrl("");
      onChange();
      return;
    }
    setErrors(fieldErrors(result.body));
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>{messages["origination.links"]}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ul className="flex flex-col gap-1">
          {(opportunity.links ?? []).map((link) => (
            <li key={link.id}>
              {link.label}:{" "}
              <a href={link.url} target="_blank" rel="noreferrer">
                {link.url}
              </a>
            </li>
          ))}
        </ul>
        {canEdit ? (
          <form onSubmit={(event) => void add(event)}>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="opportunity-link-label">{messages["origination.linkLabel"]}</FieldLabel>
                <Input id="opportunity-link-label" value={label} onChange={(event) => setLabel(event.target.value)} />
              </Field>
              <Field>
                <FieldLabel htmlFor="opportunity-link-url">{messages["origination.linkUrl"]}</FieldLabel>
                <Input
                  id="opportunity-link-url"
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  aria-invalid={Boolean(errors.url)}
                />
                <FieldError>{errors.url}</FieldError>
              </Field>
              <Button type="submit" variant="outline">
                {messages["origination.addLink"]}
              </Button>
            </FieldGroup>
          </form>
        ) : null}
      </CardContent>
    </Card>
  );
}

function CredentialsCard({
  messages,
  base,
  opportunity,
  canEdit,
  onChange,
}: {
  messages: Messages;
  base: string;
  opportunity: Opportunity;
  canEdit: boolean;
  onChange: () => void;
}) {
  const sectors = useApiData<Option[]>(canEdit ? "/api/v1/picklists/?kind=sector" : null);
  const [sectorId, setSectorId] = useState(ANY);
  const [evMin, setEvMin] = useState("");
  const [evMax, setEvMax] = useState("");
  const [query, setQuery] = useState<string | null>(null);
  const results = useApiData<Credential[]>(query === null ? null : `/api/v1/origination/credentials${query}`);
  const cited = new Set((opportunity.credentials ?? []).map((credential) => credential.id));

  async function cite(mandateId: number) {
    const result = await sendJson(`${base}/credentials`, "POST", { mandate_id: mandateId });
    if (result.status === 201) onChange();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>{messages["origination.credentials"]}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ul className="flex flex-col gap-1" aria-label={messages["origination.credentials"]}>
          {(opportunity.credentials ?? []).map((credential) => (
            <li key={credential.id} data-credential={credential.code_name}>
              {credential.code_name} {credential.ev ? `(${formatAmount(credential.ev, languageOf(messages))})` : ""}
            </li>
          ))}
        </ul>
        {canEdit ? (
          <>
            <div className="flex flex-wrap items-end gap-2">
              <Choice
                id="credential-sector"
                label={messages["deals.sector"]}
                value={sectorId}
                onChange={setSectorId}
                options={[
                  { value: ANY, label: messages["origination.anySector"] },
                  ...(sectors.data ?? []).map((sector) => ({ value: String(sector.id), label: sector.label ?? "" })),
                ]}
              />
              <Field>
                <FieldLabel htmlFor="credential-ev-min">{messages["origination.evMin"]}</FieldLabel>
                <Input id="credential-ev-min" inputMode="decimal" value={evMin} onChange={(event) => setEvMin(event.target.value)} />
              </Field>
              <Field>
                <FieldLabel htmlFor="credential-ev-max">{messages["origination.evMax"]}</FieldLabel>
                <Input id="credential-ev-max" inputMode="decimal" value={evMax} onChange={(event) => setEvMax(event.target.value)} />
              </Field>
              <Button
                type="button"
                variant="outline"
                onClick={() => setQuery(credentialQuery({ sectorId: sectorId === ANY ? "" : sectorId, evMin, evMax }))}
              >
                {messages["origination.searchCredentials"]}
              </Button>
            </div>
            <Table>
              <TableBody>
                {(results.data ?? []).map((credential) => (
                  <TableRow key={credential.id} data-credential-result={credential.code_name}>
                    <TableCell>{credential.code_name}</TableCell>
                    <TableCell>{credential.ev ?? messages["deals.none"]}</TableCell>
                    <TableCell>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={cited.has(credential.id)}
                        onClick={() => void cite(credential.id)}
                      >
                        {messages["origination.cite"]}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

function FeeDraftCard({
  messages,
  base,
  opportunity,
  canEdit,
}: {
  messages: Messages;
  base: string;
  opportunity: Opportunity;
  canEdit: boolean;
}) {
  const draft = opportunity.fee_draft ?? {};
  const [retainer, setRetainer] = useState(String(draft.retainer_monthly ?? ""));
  const [percent, setPercent] = useState(String(draft.success_fee_percent ?? ""));
  const [minimum, setMinimum] = useState(String(draft.minimum_fee ?? ""));
  const [saved, setSaved] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    setSaved(false);
    const result = await sendJson(`${base}/fee-draft`, "PUT", {
      retainer_monthly: retainer || "0",
      success_fee_kind: "percent",
      success_fee_percent: percent || "0",
      minimum_fee: minimum || "0",
    });
    if (result.status === 200) {
      setSaved(true);
      return;
    }
    const inline = fieldErrors(result.body);
    setErrors(Object.keys(inline).length ? inline : { form: readDetail(result.body, messages["common.saveFailed"]) });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>{messages["origination.feeDraft"]}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={(event) => void save(event)}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="draft-retainer">{messages["fees.retainer"]}</FieldLabel>
              <Input
                id="draft-retainer"
                inputMode="decimal"
                disabled={!canEdit}
                value={retainer}
                onChange={(event) => setRetainer(event.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="draft-percent">{messages["fees.percent"]}</FieldLabel>
              <Input
                id="draft-percent"
                inputMode="decimal"
                disabled={!canEdit}
                value={percent}
                onChange={(event) => setPercent(event.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="draft-minimum">{messages["fees.minimum"]}</FieldLabel>
              <Input
                id="draft-minimum"
                inputMode="decimal"
                disabled={!canEdit}
                value={minimum}
                onChange={(event) => setMinimum(event.target.value)}
              />
            </Field>
            {errors.form ? (
              <Alert variant="destructive">
                <AlertDescription>{errors.form}</AlertDescription>
              </Alert>
            ) : null}
            {saved ? <p className="text-muted-foreground text-sm">{messages["origination.draftSaved"]}</p> : null}
            {canEdit ? <Button type="submit">{messages["origination.saveFeeDraft"]}</Button> : null}
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  );
}
