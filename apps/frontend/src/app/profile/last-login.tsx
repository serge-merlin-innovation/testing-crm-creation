"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableRow } from "@/components/ui/table";
import { formatDate } from "@/lib/i18n/format";
import type { Language, MessageKey } from "@/lib/i18n/messages";
import { readString } from "@/lib/json-field";
import { apiFetch } from "@/services/api";

type LastLogin = { at: string | null; ip: string | null; device: string | null };

async function fetchLastLogin(): Promise<LastLogin | null> {
  const me: unknown = await apiFetch("/api/v1/users/me")
    .then((response) => (response.ok ? response.json() : null))
    .catch(() => null);
  const id = typeof me === "object" && me !== null ? (me as { id?: unknown }).id : undefined;
  if (typeof id !== "number") {
    return null;
  }
  const security: unknown = await apiFetch(`/api/v1/users/${id}/security`)
    .then((response) => (response.ok ? response.json() : null))
    .catch(() => null);
  return {
    at: readString(security, "last_login_at"),
    ip: readString(security, "last_login_ip"),
    device: readString(security, "last_login_device"),
  };
}

export function LastLoginCard({
  messages,
  language,
}: {
  messages: Record<MessageKey, string>;
  language: Language;
}) {
  const [lastLogin, setLastLogin] = useState<LastLogin | null>(null);

  useEffect(() => {
    let active = true;
    void fetchLastLogin().then((loaded) => {
      if (active) {
        setLastLogin(loaded);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  const never = messages["profile.never"];

  return (
    <Card className="max-w-md">
      <CardHeader>
        <CardTitle>
          <h2>{messages["profile.lastLogin"]}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableBody>
            <TableRow>
              <TableHead>{messages["profile.lastLogin"]}</TableHead>
              <TableCell>{lastLogin?.at ? formatDate(new Date(lastLogin.at), language) : never}</TableCell>
            </TableRow>
            <TableRow>
              <TableHead>{messages["profile.lastLoginIp"]}</TableHead>
              <TableCell>{lastLogin?.ip ?? never}</TableCell>
            </TableRow>
            <TableRow>
              <TableHead>{messages["profile.lastLoginDevice"]}</TableHead>
              <TableCell>{lastLogin?.device ?? never}</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
