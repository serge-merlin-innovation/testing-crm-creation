import type { MessageKey } from "./i18n/messages";
import { audienceFor, satisfiesAudience, type Viewer } from "./page-audience";

export type NavigationItem = {
  label: MessageKey;
  href: string;
  /** Hides the link (not the page) from roles that would only ever find it empty. */
  requires?: string;
};

const PRIMARY_NAVIGATION: NavigationItem[] = [
  { label: "nav.overview", href: "/overview" },
  { label: "nav.search", href: "/search" },
  { label: "nav.deals", href: "/deals", requires: "deals.read_staffed" },
  { label: "nav.origination", href: "/origination", requires: "deals.read_staffed" },
  { label: "nav.fees", href: "/fees" },
  { label: "nav.companies", href: "/companies" },
  { label: "nav.contacts", href: "/contacts" },
  { label: "nav.analytics", href: "/analytics" },
  { label: "nav.users", href: "/users" },
  { label: "nav.permissions", href: "/permissions" },
  { label: "nav.picklists", href: "/picklists" },
  { label: "nav.merge", href: "/merge" },
  { label: "nav.imports", href: "/imports" },
  { label: "nav.privacy", href: "/privacy", requires: "privacy.manage" },
  { label: "nav.exports", href: "/exports" },
  { label: "nav.stageCriteria", href: "/stage-criteria" },
  { label: "nav.conflictReviews", href: "/conflict-reviews" },
];

const ACCOUNT_NAVIGATION: NavigationItem[] = [
  { label: "nav.profile", href: "/profile" },
  { label: "nav.settings", href: "/settings" },
];

// Filtering through the audience manifest hides every link the viewer's permissions do not open.
export function getPrimaryNavigation(viewer: Viewer): NavigationItem[] {
  return PRIMARY_NAVIGATION.filter(
    (item) =>
      satisfiesAudience(audienceFor(item.href), viewer) &&
      (!item.requires || viewer.permissions.includes(item.requires)),
  );
}

export function getAccountNavigation(viewer: Viewer): NavigationItem[] {
  return ACCOUNT_NAVIGATION.filter((item) => satisfiesAudience(audienceFor(item.href), viewer));
}

export function getActiveNavigationLabel(pathname: string, items: NavigationItem[]): MessageKey | undefined {
  return items.find((item) => pathname === item.href || pathname.startsWith(`${item.href}/`))?.label;
}
