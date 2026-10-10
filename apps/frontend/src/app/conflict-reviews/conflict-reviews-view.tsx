"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ConflictReviewItem } from "@/lib/compliance";
import { type MessageKey, languageOf } from "@/lib/i18n/messages";
import { formatIsoDate } from "@/lib/i18n/format";
import { useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;

export function ConflictReviewsView({ messages }: { messages: Messages }) {
  const reviews = useApiData<ConflictReviewItem[]>("/api/v1/conflict-reviews/");

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h1>{messages["compliance.queueTitle"]}</h1>
        </CardTitle>
        <CardDescription>{messages["compliance.queueDescription"]}</CardDescription>
      </CardHeader>
      <CardContent>
        {reviews.data && reviews.data.length === 0 ? (
          <p>{messages["compliance.empty"]}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{messages["deals.codeName"]}</TableHead>
                <TableHead>{messages["compliance.openedAt"]}</TableHead>
                <TableHead>{messages["compliance.hits"]}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(reviews.data ?? []).map((review) => (
                <TableRow key={review.mandate_id} data-review={review.code_name}>
                  <TableCell>
                    <Button asChild variant="link">
                      <Link href={`/deals/${review.mandate_id}`}>{review.code_name}</Link>
                    </Button>
                  </TableCell>
                  <TableCell>{formatIsoDate(review.opened_at, languageOf(messages))}</TableCell>
                  <TableCell>{review.hits}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
