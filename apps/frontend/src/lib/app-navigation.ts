import { audienceFor, satisfiesAudience, type Viewer } from "./page-audience";

export type NavigationItem = {
  label: string;
  href: string;
};

const PRIMARY_NAVIGATION: NavigationItem[] = [
  { label: "Overview", href: "/overview" },
  { label: "Analytics", href: "/analytics" },
  { label: "Users", href: "/users" },
];

const ACCOUNT_NAVIGATION: NavigationItem[] = [
  { label: "Profile", href: "/profile" },
  { label: "Workspace settings", href: "/settings" },
];

// Filtering through the proxy's audience manifest prevents links to pages the viewer cannot enter.
export function getPrimaryNavigation(viewer: Viewer): NavigationItem[] {
  return PRIMARY_NAVIGATION.filter((item) =>
    satisfiesAudience(audienceFor(item.href), viewer),
  );
}

export function getAccountNavigation(viewer: Viewer): NavigationItem[] {
  return ACCOUNT_NAVIGATION.filter((item) =>
    satisfiesAudience(audienceFor(item.href), viewer),
  );
}

export function getActiveNavigationLabel(
  pathname: string,
  items: NavigationItem[],
): string | undefined {
  return items.find(
    (item) => pathname === item.href || pathname.startsWith(`${item.href}/`),
  )?.label;
}
