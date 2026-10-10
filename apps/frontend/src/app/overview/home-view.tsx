"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { type MessageKey, languageOf } from "@/lib/i18n/messages";
import { formatIsoDate } from "@/lib/i18n/format";
import { stageLabel } from "@/lib/pipeline";
import type { Home } from "@/lib/reports";
import { useApiData } from "@/lib/use-api";

type Messages = Record<MessageKey, string>;

/** REP-01: my active deals by stage, tasks due this week, upcoming key dates; guidance when empty. */
export function HomeView({ records, messages }: { records: boolean; messages: Messages }) {
  const home = useApiData<Home>(records ? "/api/v1/reports/home" : null);

  if (!records) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>
            <h1>{messages["home.title"]}</h1>
          </CardTitle>
          <CardDescription>{messages["home.dashboardsOnly"]}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild>
            <Link href="/analytics">{messages["home.openDashboards"]}</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  const data = home.data;
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>
            <h1>{messages["home.title"]}</h1>
          </CardTitle>
        </CardHeader>
      </Card>
      {data?.is_new ? (
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>{messages["home.welcome"]}</h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="flex list-decimal flex-col gap-2 pl-6">
              <li>
                <Link href="/companies">{messages["home.step1"]}</Link>
              </li>
              <li>
                <Link href="/origination">{messages["home.step2"]}</Link>
              </li>
              <li>{messages["home.step3"]}</li>
            </ol>
          </CardContent>
        </Card>
      ) : null}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>{messages["home.myDeals"]}</h2>
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {data && data.deals_by_stage.length === 0 ? <p>{messages["home.none"]}</p> : null}
            {(data?.deals_by_stage ?? []).map((group) => (
              <section key={group.stage} aria-label={stageLabel(group.stage)} className="flex flex-col gap-1">
                <CardTitle>
                  <h3>
                    {stageLabel(group.stage)} <Badge variant="outline">{group.deals.length}</Badge>
                  </h3>
                </CardTitle>
                {group.deals.map((deal) => (
                  <Link key={deal.id} href={`/deals/${deal.id}`}>
                    {deal.code_name}
                  </Link>
                ))}
              </section>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>{messages["home.tasksThisWeek"]}</h2>
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-1">
            {data && data.tasks_due_this_week.length === 0 ? <p>{messages["home.none"]}</p> : null}
            {(data?.tasks_due_this_week ?? []).map((task) => (
              <p key={task.id}>
                {formatIsoDate(task.due_date, languageOf(messages))} {task.title} {task.overdue ? <Badge variant="destructive">!</Badge> : null}
              </p>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>{messages["home.keyDates"]}</h2>
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-1">
            {data && data.key_dates.length === 0 ? <p>{messages["home.none"]}</p> : null}
            {(data?.key_dates ?? []).map((key) => (
              <p key={`${key.mandate_id}-${key.name}-${key.planned_date}`}>
                {formatIsoDate(key.planned_date, languageOf(messages))} <Link href={`/deals/${key.mandate_id}`}>{key.code_name}</Link>: {key.name}
              </p>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
