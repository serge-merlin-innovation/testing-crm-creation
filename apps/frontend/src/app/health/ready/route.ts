import { readiness } from "@/lib/readiness";

export const dynamic = "force-dynamic";

export function GET() {
  return readiness();
}
