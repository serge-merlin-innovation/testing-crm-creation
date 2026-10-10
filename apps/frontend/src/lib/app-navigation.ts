import type { MessageKey } from "./i18n/messages";
import { audienceFor, satisfiesAudience, type Viewer } from "./page-audience";

export type NavigationItem = {
  label: MessageKey;
  href: string;
};

const PRIMARY_NAVIGATION: NavigationItem[] = [
  { label: "nav.overview", href: "/overview" },
  { label: "nav.analytics", href: "/analytics" },
  { label: "nav.users", href: "/users" },
  { label: "nav.permissions", href: "/permissions" },
];

const ACCOUNT_NAVIGATION: NavigationItem[] = [
  { label: "nav.profile", href: "/profile" },
  { label: "nav.settings", href: "/settings" },
];

// Filtering through the audience manifest hides every link the viewer's permissions do not open.
export function getPrimaryNavigation(viewer: Viewer): NavigationItem[] {
  return PRIMARY_NAVIGATION.filter((item) => satisfiesAudience(audienceFor(item.href), viewer));
}

export function getAccountNavigation(viewer: Viewer): NavigationItem[] {
  return ACCOUNT_NAVIGATION.filter((item) => satisfiesAudience(audienceFor(item.href), viewer));
}

export function getActiveNavigationLabel(pathname: string, items: NavigationItem[]): MessageKey | undefined {
  return items.find((item) => pathname === item.href || pathname.startsWith(`${item.href}/`))?.label;
}
