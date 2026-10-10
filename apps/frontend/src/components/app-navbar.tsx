"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Alert, AlertDescription } from "@/components/ui/alert";
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
  const viewer = { isAuthenticated: true, roleName, permissions };
  const navigationItems = getPrimaryNavigation(viewer);
  const accountItems = getAccountNavigation(viewer);
  const activeItem = getActiveNavigationLabel(pathname, navigationItems);

  const handleLogout = async () => {
    setIsLoggingOut(true);
    setLogoutError("");

    try {
      await logout();
      router.replace("/login");
    } catch (error) {
      // Rendered inline beside the control that failed — there is no toast surface.
      setLogoutError(
        error instanceof Error ? error.message : "We could not log you out.",
      );
      setIsLoggingOut(false);
    }
  };

  return (
    <header className="flex flex-col gap-2 border-b px-6 py-3">
      <div className="flex items-center gap-4">
        <Button asChild variant="link">
          <Link href={DEFAULT_AUTHENTICATED_PATH} prefetch={false}>
            M&amp;A CRM
          </Link>
        </Button>

        <nav aria-label="Primary" className="flex items-center gap-1">
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

        <Separator orientation="vertical" className="ml-auto" />

        <nav aria-label="Account" className="flex items-center gap-1">
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
          onClick={() => void handleLogout()}
        >
          {isLoggingOut ? messages["nav.loggingOut"] : messages["nav.logout"]}
        </Button>
      </div>

      {logoutError ? (
        <Alert variant="destructive">
          <AlertDescription>{logoutError}</AlertDescription>
        </Alert>
      ) : null}
    </header>
  );
}
