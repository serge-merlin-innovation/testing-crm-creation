"use client";

import { useEffect, useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { MessageKey } from "@/lib/i18n/messages";
import { isPermissionMatrix, toggleGrant, type PermissionMatrix } from "@/lib/permission-matrix";
import { apiFetch } from "@/services/api";

const MATRIX_PATH = "/api/v1/roles/matrix";

async function fetchMatrix(): Promise<PermissionMatrix | null> {
  const response = await apiFetch(MATRIX_PATH).catch(() => null);
  const payload: unknown = response?.ok ? await response.json().catch(() => null) : null;
  return isPermissionMatrix(payload) ? payload : null;
}

export function PermissionMatrixEditor({ messages }: { messages: Record<MessageKey, string> }) {
  const [matrix, setMatrix] = useState<PermissionMatrix | null>(null);
  const [error, setError] = useState("");
  const [savedNotice, setSavedNotice] = useState("");
  const [pending, setPending] = useState<string | null>(null);

  const loadFailed = messages["permissions.loadFailed"];

  function apply(loaded: PermissionMatrix | null) {
    setMatrix(loaded ?? matrix);
    setError(loaded ? "" : loadFailed);
  }

  useEffect(() => {
    let active = true;
    void fetchMatrix().then((loaded) => {
      if (active) {
        setMatrix(loaded);
        setError(loaded ? "" : loadFailed);
      }
    });
    return () => {
      active = false;
    };
  }, [loadFailed]);

  async function toggle(permission: string, columnIndex: number) {
    if (!matrix) {
      return;
    }
    const column = matrix.columns[columnIndex];
    setPending(`${permission}:${column.id}`);
    setSavedNotice("");

    const response = await apiFetch(`/api/v1/roles/${column.id}/permissions`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ permissions: toggleGrant(matrix, permission, columnIndex) }),
    }).catch(() => null);

    setPending(null);
    if (!response?.ok) {
      setError(messages["permissions.saveFailed"]);
      return;
    }
    setError("");
    setSavedNotice(messages["permissions.saved"]);
    apply(await fetchMatrix());
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h1>{messages["permissions.title"]}</h1>
        </CardTitle>
        <CardDescription>{messages["permissions.description"]}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div>
          <Button asChild variant="outline">
            <a href={`${MATRIX_PATH}/export`} download>
              {messages["permissions.export"]}
            </a>
          </Button>
        </div>

        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
        {savedNotice ? (
          <Alert>
            <AlertDescription>{savedNotice}</AlertDescription>
          </Alert>
        ) : null}

        {matrix ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{messages["permissions.permission"]}</TableHead>
                {matrix.columns.map((column) => (
                  <TableHead key={column.id}>{column.name}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {matrix.rows.map((row) => (
                <TableRow key={row.permission}>
                  <TableCell>{row.permission}</TableCell>
                  {row.granted.map((granted, columnIndex) => {
                    const column = matrix.columns[columnIndex];
                    return (
                      <TableCell key={column.id}>
                        <Checkbox
                          checked={granted}
                          disabled={pending !== null}
                          aria-label={`${row.permission} / ${column.name}`}
                          onCheckedChange={() => void toggle(row.permission, columnIndex)}
                        />
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </CardContent>
    </Card>
  );
}
