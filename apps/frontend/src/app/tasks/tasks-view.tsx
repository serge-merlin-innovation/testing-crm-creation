"use client";

import { useState } from "react";
import { ScrollRegion } from "@/components/scroll-region";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatIsoDate } from "@/lib/i18n/format";
import { languageOf, type MessageKey } from "@/lib/i18n/messages";
import { sendJson, useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;
type Task = {
  id: number;
  title: string;
  due_date: string;
  recurrence: string;
  record_type: string | null;
  completed_at: string | null;
  overdue: boolean;
};

export function TasksView({ messages }: { messages: Messages }) {
  const language = languageOf(messages);
  const [show, setShow] = useState("open");
  const tasks = useApiData<Task[]>(`/api/v1/tasks/mine${show === "all" ? "?include_done=true" : ""}`);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function complete(task: Task) {
    const result = await sendJson(`/api/v1/tasks/${task.id}/complete`, "POST");
    if (result.status !== 200) {
      setNotice("");
      setError(messages["common.saveFailed"]);
      return;
    }
    setError("");
    setNotice(messages["tasks.completed"]);
    await tasks.reload();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h1>{messages["tasks.title"]}</h1>
        </CardTitle>
        <CardDescription>{messages["tasks.description"]}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Field className="max-w-xs">
          <FieldLabel htmlFor="tasks-show">{messages["tasks.show"]}</FieldLabel>
          <Select value={show} onValueChange={setShow}>
            <SelectTrigger id="tasks-show">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="open">{messages["tasks.showOpen"]}</SelectItem>
              <SelectItem value="all">{messages["tasks.showAll"]}</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        {tasks.failed ? (
          <Alert variant="destructive">
            <AlertDescription>{messages["common.loadFailed"]}</AlertDescription>
          </Alert>
        ) : null}
        <div className="overflow-x-auto" tabIndex={0}>
          <ScrollRegion label={messages["a11y.scrollRegion"]}>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{messages["tasks.task"]}</TableHead>
                  <TableHead>{messages["tasks.due"]}</TableHead>
                  <TableHead>{messages["tasks.status"]}</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(tasks.data ?? []).map((task) => (
                  <TableRow key={task.id}>
                    <TableCell>{task.title}</TableCell>
                    <TableCell>{formatIsoDate(task.due_date, language)}</TableCell>
                    <TableCell>
                      {task.completed_at ? (
                        <Badge variant="outline">{messages["tasks.done"]}</Badge>
                      ) : task.overdue ? (
                        <Badge variant="destructive">{messages["tasks.overdue"]}</Badge>
                      ) : (
                        <Badge variant="secondary">{messages["tasks.open"]}</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {task.completed_at ? null : (
                        <Button
                          size="sm"
                          aria-label={`${messages["tasks.complete"]} ${task.title}`}
                          onClick={() => void complete(task)}
                        >
                          {messages["tasks.complete"]}
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollRegion>
        </div>
        {tasks.data?.length === 0 ? <CardDescription>{messages["tasks.empty"]}</CardDescription> : null}
        {notice ? <p role="status">{notice}</p> : null}
        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}
