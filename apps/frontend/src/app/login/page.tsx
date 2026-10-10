import { LoginForm } from "./login-form";
import { sanitizeReturnTo } from "@/lib/auth-routing";
import { describeOAuthError } from "@/services/auth";

type LoginPageProps = {
  searchParams: Promise<{
    next?: string | string[];
    error?: string | string[];
    provider?: string | string[];
    reason?: string | string[];
  }>;
};

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function LoginPage({
  searchParams,
}: LoginPageProps) {
  const params = await searchParams;
  const requestedReturnTo = first(params.next);

  // The OAuth callback runs on the API origin and cannot render anything, so it
  // bounces back here with error/provider/reason. Without this the browser would
  // land on a login page that looks like nothing had happened.
  const oauthError = first(params.error)
    ? describeOAuthError(first(params.reason), first(params.provider))
    : "";

  return (
    <LoginForm
      returnTo={sanitizeReturnTo(requestedReturnTo)}
      initialError={oauthError}
    />
  );
}
