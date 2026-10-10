"use client";

import { useState, type FormEvent } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import {
  addDays,
  endOfDay,
  STATUS_LABEL,
  stepUpHeaders,
  type AccessRequestContext,
  type AccessRequestItem,
  type AccessReview,
  type Delegation,
  type MyAccessRequest,
} from "@/lib/access";
import { fillTemplate } from "@/lib/compliance";
import { fieldErrors, readDetail } from "@/lib/deals";
import { type MessageKey, languageOf } from "@/lib/i18n/messages";
import { formatDateTime, formatIsoDate } from "@/lib/i18n/format";
import { sendJson, useApiData } from "@/lib/use-api";
import { apiFetch } from "@/services/api";

type Messages = Record<MessageKey, string>;
type Me = { id: number; permissions: string[] };
type Option = { id: number; name: string };

const day = (iso: string, messages: Messages) => formatIsoDate(iso, languageOf(messages));

function RequestAccess({ messages }: { messages: Messages }) {
  const mine = useApiData<MyAccessRequest[]>("/api/v1/access-requests/mine");
  const [codeName, setCodeName] = useState("");
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [sent, setSent] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    setSent(false);
    const result = await sendJson("/api/v1/access-requests/", "POST", { code_name: codeName, reason });
    if (result.status === 201) {
      setCodeName("");
      setReason("");
      setSent(true);
      await mine.reload();
      return;
    }
    const inline = fieldErrors(result.body);
    setErrors(Object.keys(inline).length ? inline : { form: readDetail(result.body, messages["common.saveFailed"]) });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>{messages["access.requestTitle"]}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <form onSubmit={(event) => void submit(event)}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="access-code-name">{messages["access.codeName"]}</FieldLabel>
              <Input id="access-code-name" value={codeName} onChange={(event) => setCodeName(event.target.value)} />
              <FieldError>{errors.code_name}</FieldError>
            </Field>
            <Field>
              <FieldLabel htmlFor="access-reason">{messages["access.reason"]}</FieldLabel>
              <Textarea id="access-reason" value={reason} onChange={(event) => setReason(event.target.value)} />
              <FieldError>{errors.reason ?? errors.form}</FieldError>
            </Field>
            <div>
              <Button type="submit" disabled={!codeName.trim() || !reason.trim()}>
                {messages["access.send"]}
              </Button>
            </div>
          </FieldGroup>
        </form>
        {sent ? (
          <Alert>
            <AlertDescription>{messages["access.sent"]}</AlertDescription>
          </Alert>
        ) : null}
        {mine.data && mine.data.length > 0 ? (
          <Table aria-label={messages["access.mine"]}>
            <TableHeader>
              <TableRow>
                <TableHead>{messages["access.codeName"]}</TableHead>
                <TableHead>{messages["access.status"]}</TableHead>
                <TableHead>{messages["access.reason"]}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {mine.data.map((request) => (
                <TableRow key={request.id} data-request={request.code_name}>
                  <TableCell>{request.code_name}</TableCell>
                  <TableCell>
                    <Badge variant={request.status === "rejected" ? "destructive" : "secondary"}>
                      {messages[STATUS_LABEL[request.status]]}
                    </Badge>
                    {request.expires_at ? ` ${fillTemplate(messages["access.until"], { date: day(request.expires_at, messages) })}` : null}
                  </TableCell>
                  <TableCell>{request.decision_reason ?? request.reason}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </CardContent>
    </Card>
  );
}

function RequestDetail({ id, messages, onDone }: { id: number; messages: Messages; onDone: () => Promise<void> }) {
  const detail = useApiData<AccessRequestContext>(`/api/v1/access-requests/${id}`);
  const [comment, setComment] = useState("");
  const [reason, setReason] = useState("");
  const [expires, setExpires] = useState(addDays(new Date(), 30));
  const [error, setError] = useState<string | null>(null);
  if (!detail.data) return null;
  const request = detail.data;

  async function addComment(recommendation: "approve" | "reject" | null) {
    setError(null);
    const result = await sendJson(`/api/v1/access-requests/${id}/comments`, "POST", {
      body: comment.trim() || messages[recommendation === "reject" ? "access.recommendReject" : "access.recommendApprove"],
      recommendation,
    });
    if (result.status === 201) {
      setComment("");
      await detail.reload();
      return;
    }
    setError(readDetail(result.body, messages["common.saveFailed"]));
  }

  async function decide(decision: "approve" | "reject") {
    setError(null);
    const body = decision === "approve" ? { decision, reason, expires_at: endOfDay(expires) } : { decision, reason };
    const result = await sendJson(`/api/v1/access-requests/${id}/decision`, "POST", body);
    if (result.status === 200) {
      await detail.reload();
      await onDone();
      return;
    }
    setError(readDetail(result.body, messages["common.saveFailed"]));
  }

  return (
    <section className="flex flex-col gap-3" aria-label={request.code_name}>
      <h3>
        {request.code_name} · {request.requester_name}
      </h3>
      <p>{request.reason}</p>
      <Badge variant="secondary">{messages[STATUS_LABEL[request.status]]}</Badge>
      {request.can_decide ? (
        <div className="flex flex-col gap-2">
          <h4>{messages["access.conflicts"]}</h4>
          {request.conflicts.length === 0 ? (
            <p>{messages["access.noConflicts"]}</p>
          ) : (
            <Alert variant="destructive" data-conflicts={request.code_name}>
              <AlertDescription>
                {request.conflicts.map((c) => `${c.code_name} (${c.company_name})`).join(", ")}
              </AlertDescription>
            </Alert>
          )}
        </div>
      ) : null}
      <h4>{messages["access.comments"]}</h4>
      <ul className="flex flex-col gap-1">
        {request.comments.map((c, index) => (
          <li key={index}>
            <Badge variant="outline">{c.label}</Badge> {c.body}
          </li>
        ))}
      </ul>
      {request.can_comment && !request.can_decide ? <p>{messages["access.partnerHint"]}</p> : null}
      {request.can_comment ? (
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor={`comment-${id}`}>{messages["access.comment"]}</FieldLabel>
            <Textarea id={`comment-${id}`} value={comment} onChange={(event) => setComment(event.target.value)} />
          </Field>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" disabled={!comment.trim()} onClick={() => void addComment(null)}>
              {messages["access.addComment"]}
            </Button>
            {!request.can_decide ? (
              <>
                <Button type="button" variant="outline" onClick={() => void addComment("approve")}>
                  {messages["access.recommendApprove"]}
                </Button>
                <Button type="button" variant="outline" onClick={() => void addComment("reject")}>
                  {messages["access.recommendReject"]}
                </Button>
              </>
            ) : null}
          </div>
        </FieldGroup>
      ) : null}
      {request.can_decide ? (
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor={`expires-${id}`}>{messages["access.expiresOn"]}</FieldLabel>
            <Input id={`expires-${id}`} type="date" value={expires} onChange={(event) => setExpires(event.target.value)} />
          </Field>
          <Field>
            <FieldLabel htmlFor={`decision-${id}`}>{messages["access.reason"]}</FieldLabel>
            <Textarea id={`decision-${id}`} value={reason} onChange={(event) => setReason(event.target.value)} />
          </Field>
          <div className="flex gap-2">
            <Button type="button" onClick={() => void decide("approve")}>
              {messages["access.approve"]}
            </Button>
            <Button type="button" variant="destructive" disabled={!reason.trim()} onClick={() => void decide("reject")}>
              {messages["access.reject"]}
            </Button>
          </div>
        </FieldGroup>
      ) : null}
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
    </section>
  );
}

function ApprovalQueue({ messages }: { messages: Messages }) {
  const queue = useApiData<AccessRequestItem[]>("/api/v1/access-requests/");
  const [open, setOpen] = useState<number | null>(null);

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>{messages["access.queue"]}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {queue.data && queue.data.length === 0 ? <p>{messages["access.queueEmpty"]}</p> : null}
        {queue.data && queue.data.length > 0 ? (
          <Table aria-label={messages["access.queue"]}>
            <TableHeader>
              <TableRow>
                <TableHead>{messages["access.codeName"]}</TableHead>
                <TableHead>{messages["access.requester"]}</TableHead>
                <TableHead>{messages["access.reason"]}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {queue.data.map((request) => (
                <TableRow key={request.id} data-pending={request.code_name}>
                  <TableCell>{request.code_name}</TableCell>
                  <TableCell>{request.requester_name}</TableCell>
                  <TableCell>{request.reason}</TableCell>
                  <TableCell>
                    <Button type="button" variant="outline" size="sm" onClick={() => setOpen(request.id)}>
                      {messages["access.open"]}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
        {open !== null ? <RequestDetail key={open} id={open} messages={messages} onDone={queue.reload} /> : null}
      </CardContent>
    </Card>
  );
}

function Delegations({ messages }: { messages: Messages }) {
  const delegations = useApiData<Delegation[]>("/api/v1/delegations/");
  const partners = useApiData<Option[]>("/api/v1/mandates/lead-partners");
  const me = useApiData<Me>("/api/v1/users/me");
  const [delegate, setDelegate] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    const result = await sendJson("/api/v1/delegations/", "POST", {
      delegate_id: Number(delegate),
      starts_on: from,
      ends_on: to,
    });
    if (result.status === 201) {
      setDelegate("");
      await delegations.reload();
      return;
    }
    const inline = fieldErrors(result.body);
    setErrors(Object.keys(inline).length ? inline : { form: readDetail(result.body, messages["common.saveFailed"]) });
  }

  async function end(id: number) {
    await sendJson(`/api/v1/delegations/${id}`, "DELETE");
    await delegations.reload();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>{messages["access.delegations"]}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ul className="flex flex-col gap-2">
          {(delegations.data ?? []).map((d) => (
            <li key={d.id} className="flex items-center gap-2" data-delegation={d.delegate_name}>
              <Badge variant={d.active ? "default" : "outline"}>{d.delegate_name}</Badge>
              {day(d.starts_on, messages)} – {day(d.ends_on, messages)}
              <Button type="button" variant="ghost" size="sm" onClick={() => void end(d.id)}>
                {messages["access.endDelegation"]}
              </Button>
            </li>
          ))}
        </ul>
        <form onSubmit={(event) => void add(event)}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="delegate">{messages["access.delegate"]}</FieldLabel>
              <Select value={delegate} onValueChange={setDelegate}>
                <SelectTrigger id="delegate">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(partners.data ?? [])
                    .filter((p) => p.id !== me.data?.id)
                    .map((p) => (
                      <SelectItem key={p.id} value={String(p.id)}>
                        {p.name}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
              <FieldError>{errors.delegate_id}</FieldError>
            </Field>
            <div className="flex gap-4">
              <Field>
                <FieldLabel htmlFor="delegate-from">{messages["access.from"]}</FieldLabel>
                <Input id="delegate-from" type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
              </Field>
              <Field>
                <FieldLabel htmlFor="delegate-to">{messages["access.to"]}</FieldLabel>
                <Input id="delegate-to" type="date" value={to} onChange={(event) => setTo(event.target.value)} />
                <FieldError>{errors.ends_on ?? errors.form}</FieldError>
              </Field>
            </div>
            <div>
              <Button type="submit" disabled={!delegate || !from || !to}>
                {messages["access.addDelegation"]}
              </Button>
            </div>
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  );
}

function BreakGlass({ messages }: { messages: Messages }) {
  const [codeName, setCodeName] = useState("");
  const [reason, setReason] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [opened, setOpened] = useState<{ mandate_id: number; expires_at: string } | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const response = await apiFetch("/api/v1/break-glass/", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...stepUpHeaders(code) },
      body: JSON.stringify({ code_name: codeName, reason }),
      bounce: false,
    }).catch(() => null);
    const body: unknown = response ? await response.json().catch(() => null) : null;
    setCode("");
    if (response?.status === 201) {
      setOpened(body as { mandate_id: number; expires_at: string });
      return;
    }
    setError(readDetail(body, messages["common.saveFailed"]));
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>{messages["access.breakGlass"]}</h2>
        </CardTitle>
        <CardDescription>{messages["access.breakGlassHint"]}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <form aria-label={messages["access.breakGlass"]} onSubmit={(event) => void submit(event)}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="glass-code-name">{messages["access.codeName"]}</FieldLabel>
              <Input id="glass-code-name" value={codeName} onChange={(event) => setCodeName(event.target.value)} />
            </Field>
            <Field>
              <FieldLabel htmlFor="glass-reason">{messages["access.reason"]}</FieldLabel>
              <Textarea id="glass-reason" value={reason} onChange={(event) => setReason(event.target.value)} />
            </Field>
            <Field>
              <FieldLabel htmlFor="glass-code">{messages["access.code"]}</FieldLabel>
              <Input
                id="glass-code"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={code}
                onChange={(event) => setCode(event.target.value)}
              />
              <FieldError>{error}</FieldError>
            </Field>
            <div>
              <Button type="submit" variant="destructive" disabled={!codeName.trim() || !reason.trim() || !code.trim()}>
                {messages["access.breakGlassConfirm"]}
              </Button>
            </div>
          </FieldGroup>
        </form>
        {opened ? (
          <Alert>
            <AlertDescription>
              {fillTemplate(messages["access.breakGlassOpened"], { date: formatDateTime(opened.expires_at, languageOf(messages)) })}{" "}
              <Button asChild variant="link">
                <a href={`/deals/${opened.mandate_id}`}>{messages["access.open"]}</a>
              </Button>
            </AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}

function ReviewCard({ review, messages, onDone }: { review: AccessReview; messages: Messages; onDone: () => Promise<void> }) {
  const [removed, setRemoved] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);

  function toggle(userId: number) {
    const next = new Set(removed);
    if (next.has(userId)) next.delete(userId);
    else next.add(userId);
    setRemoved(next);
  }

  async function confirm() {
    setError(null);
    const result = await sendJson(`/api/v1/access-reviews/${review.id}`, "POST", { remove_user_ids: [...removed] });
    if (result.status === 200) {
      await onDone();
      return;
    }
    setError(readDetail(result.body, messages["common.saveFailed"]));
  }

  return (
    <li className="flex flex-col gap-2" data-review={review.code_name}>
      <div className="flex flex-wrap items-center gap-2">
        <strong>{review.code_name}</strong> {review.quarter} · {review.partner_name} ·{" "}
        {fillTemplate(messages["access.due"], { date: day(review.due_at, messages) })}
        {review.completed_at ? <Badge variant="secondary">{messages["access.done"]}</Badge> : null}
        {review.escalated_at ? <Badge variant="destructive">{messages["access.escalated"]}</Badge> : null}
      </div>
      {review.members.length > 0 ? (
        <>
          <ul className="flex flex-col gap-1">
            {review.members.map((member) => (
              <li key={member.user_id}>
                <Field orientation="horizontal">
                <Checkbox
                  id={`remove-${review.id}-${member.user_id}`}
                  checked={removed.has(member.user_id)}
                  onCheckedChange={() => toggle(member.user_id)}
                />
                <FieldLabel htmlFor={`remove-${review.id}-${member.user_id}`}>
                  {messages["access.remove"]} {member.name} ({member.role.replace("_", " ")})
                </FieldLabel>
                </Field>
              </li>
            ))}
          </ul>
          <div>
            <Button type="button" onClick={() => void confirm()}>
              {messages["access.confirmTeam"]}
            </Button>
          </div>
        </>
      ) : null}
      {error ? <FieldError>{error}</FieldError> : null}
    </li>
  );
}

function Reviews({ messages }: { messages: Messages }) {
  const reviews = useApiData<AccessReview[]>("/api/v1/access-reviews/");

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>{messages["access.reviews"]}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {reviews.data && reviews.data.length === 0 ? <p>{messages["access.reviewsEmpty"]}</p> : null}
        <ul className="flex flex-col gap-4">
          {(reviews.data ?? []).map((review) => (
            <ReviewCard key={review.id} review={review} messages={messages} onDone={reviews.reload} />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export function AccessView({ messages }: { messages: Messages }) {
  const me = useApiData<Me>("/api/v1/users/me");
  const permissions = me.data?.permissions ?? [];

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>
            <h1>{messages["access.title"]}</h1>
          </CardTitle>
          <CardDescription>{messages["access.description"]}</CardDescription>
        </CardHeader>
      </Card>
      <RequestAccess messages={messages} />
      <ApprovalQueue messages={messages} />
      {permissions.includes("mandates.create") ? <Delegations messages={messages} /> : null}
      <Reviews messages={messages} />
      {permissions.includes("users.manage") ? <BreakGlass messages={messages} /> : null}
    </div>
  );
}
