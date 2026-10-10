"use client";

import { useState, type FormEvent } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { formatDateTime } from "@/lib/i18n/format";
import { languageOf, type MessageKey } from "@/lib/i18n/messages";
import { sendJson, useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;
export type TimelineRecordType = "contact" | "company" | "mandate";
type ActivityType = "call" | "meeting" | "email";
type Activity = {
  id: number;
  type: ActivityType;
  occurred_at: string;
  participants: string[];
  note: string;
  author_id: number;
  author_name: string | null;
  edited_at: string | null;
};
type Note = { id: number; body: string; visibility: string; author_name: string | null; created_at: string };
type Timeline = { activities: Activity[]; notes: Note[] };
type Deleted = { id: number; type: ActivityType; occurred_at: string; deleted_at: string };
type Me = { id: number; permissions?: string[] };

const TYPES: ActivityType[] = ["call", "meeting", "email"];
const TYPE_LABEL: Record<ActivityType, MessageKey> = {
  call: "timeline.call",
  meeting: "timeline.meeting",
  email: "timeline.email",
};
const VISIBILITY_LABEL: Record<string, MessageKey> = {
  shared: "timeline.shared",
  private: "timeline.private",
  deal_confidential: "timeline.dealConfidential",
};
const RESTORER = "settings.manage";

function nowLocal(): string {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16);
}

/** Activities and notes of one contact, company or deal (ACT-01, ACT-02). Mountable on any record page. */
export function RecordTimeline({
  recordType,
  recordId,
  messages,
}: {
  recordType: TimelineRecordType;
  recordId: number;
  messages: Messages;
}) {
  const language = languageOf(messages);
  const timeline = useApiData<Timeline>(`/api/v1/timeline/${recordType}/${recordId}`);
  const me = useApiData<Me>("/api/v1/users/me");
  const canRestore = me.data?.permissions?.includes(RESTORER) ?? false;
  const bin = useApiData<Deleted[]>(canRestore ? "/api/v1/activities/deleted" : null);
  const [type, setType] = useState<ActivityType>("call");
  const [occurredAt, setOccurredAt] = useState(nowLocal);
  const [participants, setParticipants] = useState("");
  const [note, setNote] = useState("");
  const [noteBody, setNoteBody] = useState("");
  const [visibility, setVisibility] = useState("shared");
  const [editing, setEditing] = useState<Activity | null>(null);
  const [editNote, setEditNote] = useState("");
  const [editType, setEditType] = useState<ActivityType>("call");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function done(ok: boolean, message: MessageKey) {
    setError(ok ? "" : messages["common.saveFailed"]);
    setNotice(ok ? messages[message] : "");
    if (ok) {
      await Promise.all([timeline.reload(), bin.reload()]);
    }
    return ok;
  }

  async function logActivity(event: FormEvent) {
    event.preventDefault();
    const result = await sendJson("/api/v1/activities/", "POST", {
      type,
      occurred_at: new Date(occurredAt).toISOString(),
      participants: participants
        .split(",")
        .map((name) => name.trim())
        .filter(Boolean),
      note,
      links: [{ record_type: recordType, record_id: recordId }],
    });
    if (await done(result.status === 201, "timeline.logged")) {
      setNote("");
      setParticipants("");
    }
  }

  async function addNote(event: FormEvent) {
    event.preventDefault();
    const result = await sendJson("/api/v1/notes/", "POST", {
      record_type: recordType,
      record_id: recordId,
      body: noteBody,
      visibility,
    });
    if (await done(result.status === 201, "timeline.noteAdded")) {
      setNoteBody("");
    }
  }

  async function saveEdit() {
    if (!editing) return;
    const result = await sendJson(`/api/v1/activities/${editing.id}`, "PATCH", { type: editType, note: editNote });
    if (await done(result.status === 200, "timeline.saved")) {
      setEditing(null);
    }
  }

  async function remove(activity: Activity) {
    const result = await sendJson(`/api/v1/activities/${activity.id}`, "DELETE");
    await done(result.status === 204, "timeline.deleted");
  }

  async function restore(item: Deleted) {
    const result = await sendJson(`/api/v1/activities/${item.id}/restore`, "POST");
    await done(result.status === 200 || result.status === 201 || result.status === 204, "timeline.restored");
  }

  const activities = timeline.data?.activities ?? [];
  const notes = timeline.data?.notes ?? [];
  const visibilities = recordType === "mandate" ? ["shared", "private", "deal_confidential"] : ["shared", "private"];

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>{messages["timeline.title"]}</h2>
        </CardTitle>
        <CardDescription>{messages["timeline.description"]}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {timeline.failed ? (
          <Alert variant="destructive">
            <AlertDescription>{messages["common.loadFailed"]}</AlertDescription>
          </Alert>
        ) : null}
        <section aria-label={messages["timeline.activities"]} className="flex flex-col gap-2">
          <CardTitle>
            <h3>{messages["timeline.activities"]}</h3>
          </CardTitle>
          {activities.length === 0 ? <CardDescription>{messages["timeline.noActivities"]}</CardDescription> : null}
          <ul className="flex flex-col gap-3">
            {activities.map((activity) => (
              <li key={activity.id} className="flex flex-col gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary">{messages[TYPE_LABEL[activity.type]]}</Badge>
                  <CardDescription>
                    {formatDateTime(activity.occurred_at, language)} {activity.author_name ?? ""}
                  </CardDescription>
                  {activity.edited_at ? (
                    <Badge variant="outline">
                      {messages["timeline.edited"]} {formatDateTime(activity.edited_at, language)}
                    </Badge>
                  ) : null}
                </div>
                <p>{activity.note}</p>
                {activity.participants.length > 0 ? (
                  <CardDescription>{activity.participants.join(", ")}</CardDescription>
                ) : null}
                <div className="flex gap-2">
                  {me.data?.id === activity.author_id ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setEditing(activity);
                        setEditNote(activity.note);
                        setEditType(activity.type);
                      }}
                    >
                      {messages["timeline.edit"]}
                    </Button>
                  ) : null}
                  {me.data?.id === activity.author_id || canRestore ? (
                    <Button size="sm" variant="destructive" onClick={() => void remove(activity)}>
                      {messages["timeline.delete"]}
                    </Button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section aria-label={messages["timeline.notes"]} className="flex flex-col gap-2">
          <CardTitle>
            <h3>{messages["timeline.notes"]}</h3>
          </CardTitle>
          {notes.length === 0 ? <CardDescription>{messages["timeline.noNotes"]}</CardDescription> : null}
          <ul className="flex flex-col gap-3">
            {notes.map((item) => (
              <li key={item.id} className="flex flex-col gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{messages[VISIBILITY_LABEL[item.visibility] ?? "timeline.shared"]}</Badge>
                  <CardDescription>
                    {formatDateTime(item.created_at, language)} {item.author_name ?? ""}
                  </CardDescription>
                </div>
                <p>{item.body}</p>
              </li>
            ))}
          </ul>
        </section>

        <form onSubmit={(event) => void logActivity(event)} aria-label={messages["timeline.logActivity"]}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor={`activity-type-${recordType}`}>{messages["timeline.type"]}</FieldLabel>
              <Select value={type} onValueChange={(value) => setType(value as ActivityType)}>
                <SelectTrigger id={`activity-type-${recordType}`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TYPES.map((item) => (
                    <SelectItem key={item} value={item}>
                      {messages[TYPE_LABEL[item]]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field>
              <FieldLabel htmlFor={`activity-when-${recordType}`}>{messages["timeline.when"]}</FieldLabel>
              <Input
                id={`activity-when-${recordType}`}
                type="datetime-local"
                value={occurredAt}
                onChange={(event) => setOccurredAt(event.target.value)}
                required
              />
            </Field>
            <Field>
              <FieldLabel htmlFor={`activity-participants-${recordType}`}>{messages["timeline.participants"]}</FieldLabel>
              <Input
                id={`activity-participants-${recordType}`}
                value={participants}
                onChange={(event) => setParticipants(event.target.value)}
              />
              <FieldDescription>{messages["timeline.participantsHint"]}</FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor={`activity-note-${recordType}`}>{messages["timeline.activityNote"]}</FieldLabel>
              <Textarea
                id={`activity-note-${recordType}`}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                required
              />
            </Field>
            <Button type="submit">{messages["timeline.logActivity"]}</Button>
          </FieldGroup>
        </form>

        <form onSubmit={(event) => void addNote(event)} aria-label={messages["timeline.addNote"]}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor={`note-body-${recordType}`}>{messages["timeline.noteBody"]}</FieldLabel>
              <Textarea
                id={`note-body-${recordType}`}
                value={noteBody}
                onChange={(event) => setNoteBody(event.target.value)}
                required
              />
            </Field>
            <Field>
              <FieldLabel htmlFor={`note-visibility-${recordType}`}>{messages["timeline.visibility"]}</FieldLabel>
              <Select value={visibility} onValueChange={setVisibility}>
                <SelectTrigger id={`note-visibility-${recordType}`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {visibilities.map((item) => (
                    <SelectItem key={item} value={item}>
                      {messages[VISIBILITY_LABEL[item]]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Button type="submit">{messages["timeline.addNote"]}</Button>
          </FieldGroup>
        </form>

        {canRestore ? (
          <section aria-label={messages["timeline.bin"]} className="flex flex-col gap-2">
            <CardTitle>
              <h3>{messages["timeline.bin"]}</h3>
            </CardTitle>
            <CardDescription>{messages["timeline.binDescription"]}</CardDescription>
            <div className="overflow-x-auto" tabIndex={0}>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{messages["timeline.type"]}</TableHead>
                    <TableHead>{messages["timeline.when"]}</TableHead>
                    <TableHead>{messages["timeline.deletedAt"]}</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(bin.data ?? []).map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>{messages[TYPE_LABEL[item.type]]}</TableCell>
                      <TableCell>{formatDateTime(item.occurred_at, language)}</TableCell>
                      <TableCell>{formatDateTime(item.deleted_at, language)}</TableCell>
                      <TableCell>
                        <Button size="sm" variant="outline" onClick={() => void restore(item)}>
                          {messages["timeline.restore"]}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </section>
        ) : null}

        {notice ? <p role="status">{notice}</p> : null}
        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
      </CardContent>

      <Dialog open={editing !== null} onOpenChange={(open) => (open ? null : setEditing(null))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{messages["timeline.editTitle"]}</DialogTitle>
            <DialogDescription>{messages["timeline.editDescription"]}</DialogDescription>
          </DialogHeader>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="edit-activity-type">{messages["timeline.type"]}</FieldLabel>
              <Select value={editType} onValueChange={(value) => setEditType(value as ActivityType)}>
                <SelectTrigger id="edit-activity-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TYPES.map((item) => (
                    <SelectItem key={item} value={item}>
                      {messages[TYPE_LABEL[item]]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field>
              <FieldLabel htmlFor="edit-activity-note">{messages["timeline.activityNote"]}</FieldLabel>
              <Textarea id="edit-activity-note" value={editNote} onChange={(event) => setEditNote(event.target.value)} />
            </Field>
          </FieldGroup>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>
              {messages["timeline.cancel"]}
            </Button>
            <Button onClick={() => void saveEdit()} disabled={editNote.trim() === ""}>
              {messages["common.save"]}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
