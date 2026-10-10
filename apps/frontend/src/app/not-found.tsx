import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DEFAULT_AUTHENTICATED_PATH } from "@/lib/auth-routing";
import { MESSAGES } from "@/lib/i18n/messages";
import { getLanguage } from "@/lib/i18n/server";

export default async function NotFound() {
  const messages = MESSAGES[await getLanguage()];

  return (
    <main className="flex min-h-svh items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>
            <h1>{messages["common.notFound"]}</h1>
          </CardTitle>
          <CardDescription>{messages["common.notFoundDescription"]}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild variant="outline">
            <Link href={DEFAULT_AUTHENTICATED_PATH}>{messages["nav.overview"]}</Link>
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}
