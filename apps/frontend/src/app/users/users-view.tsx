"use client";

import { useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatIsoDate } from "@/lib/i18n/format";
import { type MessageKey, languageOf } from "@/lib/i18n/messages";
import { useApiData } from "@/lib/use-api";
import { UserPanel, type DirectoryUser } from "./user-panel";

type Messages = Record<MessageKey, string>;
type Page = { data: DirectoryUser[] };

export function UsersView({ messages }: { messages: Messages }) {
  const [tab, setTab] = useState<"current" | "inactive">("current");
  const listPath = tab === "inactive" ? "/api/v1/users/?status=inactive&items_per_page=100" : "/api/v1/users/?items_per_page=100";
  const users = useApiData<Page>(listPath);
  const everyone = useApiData<Page>("/api/v1/users/?status=active&items_per_page=100");
  // The user object, not just its id: after a deactivation the list no longer holds them, and the
  // confirmation must stay on screen.
  const [current, setCurrent] = useState<DirectoryUser | null>(null);
  const selected = current?.id ?? null;

  async function refresh() {
    await Promise.all([users.reload(), everyone.reload()]);
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>
            <h1>{messages["users.title"]}</h1>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Tabs
            value={tab}
            onValueChange={(value) => {
              setTab(value === "inactive" ? "inactive" : "current");
              setCurrent(null);
            }}
          >
            <TabsList>
              <TabsTrigger value="current">{messages["users.all"]}</TabsTrigger>
              <TabsTrigger value="inactive">{messages["users.inactive"]}</TabsTrigger>
            </TabsList>
            {/* Each tab needs the panel its aria-controls names (WCAG 4.1.2); the table below is shared. */}
            <TabsContent value="current" />
            <TabsContent value="inactive" />
          </Tabs>
          {users.failed ? (
            <Alert variant="destructive">
              <AlertDescription>{messages["common.loadFailed"]}</AlertDescription>
            </Alert>
          ) : null}
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{messages["common.name"]}</TableHead>
                  <TableHead>{messages["login.email"]}</TableHead>
                  <TableHead>{messages["users.role"]}</TableHead>
                  <TableHead>{messages["users.status"]}</TableHead>
                  <TableHead>{messages["users.lastLogin"]}</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(users.data?.data ?? []).map((user) => (
                  <TableRow key={user.id}>
                    <TableCell>{user.name}</TableCell>
                    <TableCell>{user.email}</TableCell>
                    <TableCell>{user.role_name ?? ""}</TableCell>
                    <TableCell>
                      <Badge variant={user.status === "active" ? "secondary" : "outline"}>{user.status}</Badge>
                    </TableCell>
                    <TableCell>{formatIsoDate(user.last_login_at, languageOf(messages))}</TableCell>
                    <TableCell>
                      <Button
                        size="sm"
                        variant={selected === user.id ? "default" : "outline"}
                        aria-label={`${messages["users.manage"]} ${user.email}`}
                        onClick={() => setCurrent(selected === user.id ? null : user)}
                      >
                        {messages["users.manage"]}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {users.data?.data.length === 0 ? <p>{messages["common.empty"]}</p> : null}
        </CardContent>
      </Card>
      {current ? (
        <UserPanel
          key={current.id}
          user={current}
          everyone={everyone.data?.data ?? []}
          messages={messages}
          onChanged={refresh}
        />
      ) : null}
    </div>
  );
}
