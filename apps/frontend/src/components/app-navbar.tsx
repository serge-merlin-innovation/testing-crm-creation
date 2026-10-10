"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { DEFAULT_AUTHENTICATED_PATH } from "@/lib/auth-routing";
import {
  getAccountNavigation,
  getActiveNavigationLabel,
  getPrimaryNavigation,
} from "@/lib/app-navigation";
import type { MessageKey } from "@/lib/i18n/messages";
import type { SessionIdentity } from "@/lib/page-audience";
import { unsavedChanges } from "@/lib/unsaved-changes";
import { logout } from "@/services/auth";

/** Only ever rendered for a signed-in reader, hence the hardcoded `isAuthenticated`. Role and
 *  permissions arrive as props from the proxy's headers — nothing about the session is readable here. */
export function AppNavbar({
  roleName,
  permissions,
  messages,
}: SessionIdentity & { messages: Record<MessageKey, string> }) {
  const pathname = usePathname();
  const router = useRouter();
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const [confirmingLogout, setConfirmingLogout] = useState(false);
  const viewer = { isAuthenticated: true, roleName, permissions };
  const navigationItems = getPrimaryNavigation(viewer);
  const accountItems = getAccountNavigation(viewer);
  const activeItem = getActiveNavigationLabel(pathname, navigationItems);

  const requestLogout = () => {
    if (unsavedChanges.any()) {
      setConfirmingLogout(true);
      return;
    }
    void handleLogout();
  };

  const handleLogout = async () => {
    setConfirmingLogout(false);
    setIsLoggingOut(true);
    setLogoutError("");

    try {
      await logout();
      unsavedChanges.clear();
      // replace, not push: Back must not return to the signed-in page just left.
      router.replace("/login");
      router.refresh();
    } catch (error) {
      // Rendered inline beside the control that failed — there is no toast surface.
      setLogoutError(
        error instanceof Error ? error.message : "We could not log you out.",
      );
      setIsLoggingOut(false);
    }
  };

  return (
    <header className="flex flex-col gap-2 border-b px-4 py-3 md:px-6">
      <div className="flex flex-wrap items-center gap-2 md:gap-4">
        <Button asChild variant="link">
          <Link href={DEFAULT_AUTHENTICATED_PATH} prefetch={false}>
            M&amp;A CRM
          </Link>
        </Button>

        <nav aria-label={messages["nav.primary"]} className="flex flex-wrap items-center gap-1">
          {navigationItems.map((item) => {
            const isActive = item.label === activeItem;
            return (
              <Button
                key={item.href}
                asChild
                variant={isActive ? "secondary" : "ghost"}
              >
                <Link
                  href={item.href}
                  aria-current={isActive ? "page" : undefined}
                >
                  {messages[item.label]}
                </Link>
              </Button>
            );
          })}
        </nav>

        <Separator orientation="vertical" className="hidden md:ml-auto md:block" />

        <nav aria-label={messages["nav.account"]} className="flex items-center gap-1">
          {accountItems.map((item) => (
            <Button key={item.href} asChild variant="ghost">
              <Link href={item.href}>{messages[item.label]}</Link>
            </Button>
          ))}
        </nav>

        <Button
          type="button"
          variant="outline"
          disabled={isLoggingOut}
          onClick={requestLogout}
        >
          {isLoggingOut ? messages["nav.loggingOut"] : messages["nav.logout"]}
        </Button>
      </div>

      <AlertDialog open={confirmingLogout} onOpenChange={setConfirmingLogout}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{messages["logout.unsavedTitle"]}</AlertDialogTitle>
            <AlertDialogDescription>{messages["logout.unsavedDescription"]}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{messages["logout.cancel"]}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={() => void handleLogout()}>
              {messages["logout.confirm"]}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {logoutError ? (
        <Alert variant="destructive">
          <AlertDescription>{logoutError}</AlertDescription>
        </Alert>
      ) : null}
    </header>
  );
}
