"""Generate ticket bodies from docs/specs/ma-crm.md and verify every criterion lands in exactly one ticket."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs/specs/ma-crm.md"
OUT = Path(__file__).resolve().parent / "issues"

text = SPEC.read_text()
stories: dict[str, dict] = {}
order: list[str] = []
cross: list[str] = []
section = None
current = None
for line in text.splitlines():
    if line.startswith("## "):
        section = line[3:].strip()
        current = None
        continue
    if section == "User Stories":
        m = re.match(r"^([A-Z]+-\d+)\. (.*)$", line)
        if m:
            current = m.group(1)
            stories[current] = {"title": m.group(2), "criteria": []}
            order.append(current)
            continue
        c = re.match(r"^- \[ \] (.*)$", line)
        if c and current:
            stories[current]["criteria"].append(c.group(1))
    elif section == "Cross-cutting Acceptance Criteria":
        c = re.match(r"^- \[ \] (.*)$", line)
        if c:
            cross.append(c.group(1))

# Each ticket: key, title, blocked_by (keys), stories: list of "ID" or "ID:n,m" (1-based criteria), what, notes
T = [
    dict(
        key=1,
        title="Foundation: email-only login, one role per user, permission matrix and append-only audit log",
        blocked=[],
        items=["ROLE-01:1", "AUTHZ-01", "ADM-02", "AUD-01"],
        what="""Turn the boilerplate into the CRM's base. Login is by email (no username field) and the Microsoft Entra sign-in is removed end to end (routes, settings, frontend button, user columns). The superuser flag is retired in favour of the Admin role. The six roles from the role table are seeded with a database-stored permission set, enforced server-side on every request (403 plus hidden UI control), and editable by an admin on a permission matrix screen (roles as columns, permissions as rows, exportable). A user has exactly one role.

An append-only audit log records user, time, IP, record and old/new values, written in the same transaction as the change; the database role cannot UPDATE or DELETE it. Compliance can search it by user and by record.

This ticket also lays the shared rails later tickets build on: EN/FR/NL message catalogues with Belgian date and number formatters in frontend and backend, an injectable clock, and a scheduled-job runner with a test-only "run jobs now" trigger.""",
    ),
    dict(
        key=2,
        title="Two-factor login, lockout and suspicious-login alerts",
        blocked=[1],
        items=["AUTH-01:1,2,3,4,5,6,8", "AUTH-02:1,2,3,4,6", "AUTH-06", "AUTH-12"],
        what="""A staff member logs in with email and password, then a 6-digit TOTP code; first-time users enrol an authenticator app by QR code and receive 10 one-time recovery codes. Trust this device skips the code for 30 days (admin can disable). Inactive or role-less users are refused and the attempt is logged. Rate limiting per IP and per account, CSRF protection, 5 failed attempts in 15 minutes lock the account for 15 minutes with an admin alert, and admins can unlock and reset 2FA (audited). Logins from a new country or device email the user and admin, unless the user is flagged as travelling for the current date range. Last login date, IP and device show on the profile.

Geo-IP and outbound email sit behind ports with fakes in tests. The step-up "ask the code again" mechanism is built here so later tickets can call it for sensitive actions.""",
    ),
    dict(
        key=3,
        title="Session timeout, logout everywhere and mobile access",
        blocked=[2],
        items=["AUTH-03", "AUTH-04", "AUTH-07"],
        what="""Server-side cookie sessions get a rolling idle timeout (30 min desktop, 15 min mobile, admin-configurable for new sessions) and an absolute 12-hour lifetime. Activity in any tab keeps the session alive; a warning 2 minutes before expiry offers Stay logged in; re-authentication keeps unsaved form data locally; silent renewal never navigates away. Log out revokes the server-side session and blocks cached pages on Back; Log out everywhere on the profile ends every session on every device; unsaved changes warn before leaving. On phones the responsive app works end to end, and an admin setting makes it read-only below 768 px (edit and export actions hidden).

Decision: the spec's "access token / refresh token" wording maps onto the server-side session record; no JWTs are introduced for the browser.""",
    ),
    dict(
        key=4,
        title="User onboarding by invitation, password policy and password reset",
        blocked=[2],
        items=["ADM-01", "ADM-04", "AUTH-08", "AUTH-09", "AUTH-10", "AUTH-11"],
        what="""An admin creates a user (first name, last name, email, title, role), one by one or from a CSV, which creates the account as Invited and sends an invitation and a welcome email. The invitee sets a password and enrols 2FA from a single-use link valid 72 hours; admins can resend. Passwords must be 12+ characters, not in breach lists (Have I Been Pwned k-anonymity API behind a port), not containing name or email, and not one of the last 5; only Argon2id (or bcrypt) hashes are stored. Forgot password always shows the same message, sends a single-use 30-minute link, is limited to 3 requests per hour, ends other sessions and sends a confirmation. Users change their password from the profile with current password and a 2FA code. The admin user list filters by role and status, exports to CSV and flags dormant users (90 days).""",
    ),
    dict(
        key=5,
        title="Companies, contacts and reference data",
        blocked=[1],
        items=["CO-01", "CO-02", "CO-03", "CON-01:1,2,4", "ADM-06", "GDPR-01:1"],
        what="""Users create companies with type and country; Belgian companies take an enterprise number validated by checksum and pre-filled from the KBO/BCE register (behind a port, with manual entry on failure), foreign companies take a VAT or registry number. Duplicates by number or similar name are surfaced. Companies carry yearly financials in EUR thousands, importable from NBB filed accounts (behind a port) with manual overrides kept alongside imported values, and original currency plus EUR rate stored. Parent/subsidiary links build a group tree, with loops blocked. Contacts carry function at a company with employment history, language (EN/FR/NL) and salutation, validated email and E.164 phone, duplicate-email warning, Do not contact flag, legal basis (legitimate interest by default, or consent) and source. Admins manage picklists (sectors, deal stages, deal types, countries) with EN required and FR/NL translations; in-use values can be renamed or deactivated but not deleted.""",
    ),
    dict(
        key=6,
        title="Mandates with code names, deal team and the Chinese wall",
        blocked=[1, 5],
        items=["DEAL-01:1,3,5", "DEAL-03:2,3", "DEAL-07", "AUTHZ-02:1,6", "AUTHZ-03", "ROLE-01:2", "AUTH-01:7"],
        what="""A partner creates a mandate with a unique code name (rejected if it contains the client or target name), client, type, sector, lead partner and estimated EV. Every mandate type uses the sell-side stage list. A deal team (membership with role on the deal, added-by, added-at, optional expiry) controls who sees it; partners and directors add and remove members, the last lead partner cannot be removed, and every change lands in the wall-crossing register. Members are notified (introduce a basic in-app and email notification service here).

Build the single deal-access policy module every deal-scoped read and write goes through: role permission AND deal-team membership, hidden deals return 404, forbidden actions 403. Start the deal-access matrix test suite: every deal-scoped endpoint registers in it and a test fails when one is missing. The deal page shows summary, team and history (who, when, old, new) with optimistic concurrency (stale write gets a conflict and the newer version). Document links are labelled https links opening in a new tab, team-only. A deep link to an inaccessible deal lands on Not found after login.""",
    ),
    dict(
        key=7,
        title="Activities, private notes, tasks and notification preferences",
        blocked=[6],
        items=["ACT-01", "ACT-02", "ACT-03", "ACT-06", "AUTHZ-02:2"],
        what="""Users log calls, meetings and emails (type, date, participants, note) against contacts, companies and deals; each activity shows on every linked timeline, is hidden from non-staffed users when deal-linked, shows "edited" after 7 days, and is soft-deleted with 30-day admin restore. Notes can be Private (author only, admins included) or Deal-confidential (deal team only). On a shared company record a non-staffed user sees neither the deal link nor deal notes. Tasks have assignee, due date, linked record and recurrence; deal tasks cannot go to non-staffed users; My tasks lists them and overdue tasks trigger a daily digest. Users choose in-app, email or none per notification event type; deal emails use the code name only. Later tickets create tasks and notifications through this module.""",
    ),
    dict(
        key=8,
        title="Pipeline board, configurable stage gates, milestones and closing",
        blocked=[6, 7],
        items=["DEAL-02", "DEAL-08", "DEAL-04", "DEAL-06", "AUTHZ-02:7,8"],
        what="""Directors see their accessible deals as a Kanban by stage (with a sortable list toggle and partner/type/sector/stage filters). Dragging saves stage and date into deal history; backward moves need a reason; moves are blocked with the reason when the stage's exit criteria are missing. Admins configure exit criteria per stage (required field, required document link label, or the built-in engagement letter / KYC gate). Milestones carry planned and actual dates, show red with days late, and notify the team 3 days before due. Closing as Closed won requires final EV, buyer, EV/EBITDA and closing date plus a tombstone choice; Aborted requires a reason and makes the deal read-only; reopening needs a reason and is audited. Closed deals stay limited to the former team plus compliance (read-only for compliance after 12 months).""",
    ),
    dict(
        key=9,
        title="Conflict check on new mandates and KYC / engagement letter gate",
        blocked=[8],
        items=["AUTHZ-05", "DEAL-01:2,4", "ORI-05"],
        what="""Creating a mandate runs a conflict check of client, target and counterparties (including group entities) against active mandates and those closed or aborted in the last 24 months, using legal-form-stripped, accent-insensitive fuzzy matching (pg_trgm + unaccent). A hit keeps the mandate in Conflict review, where only compliance and the creator can find it and only compliance sees what it conflicts with. Compliance clears or rejects with a logged reason; reviews older than 5 working days remind the lead partner and compliance; adding a counterparty later re-runs the check. The creator is added to the deal team. Compliance records KYC (UBO, ID, PEP/sanctions) to reach Approved; without an engagement letter link and Approved KYC a mandate cannot leave Preparation; KYC older than 12 months creates a refresh task; a sanctions hit freezes the mandate until compliance unfreezes it.""",
    ),
    dict(
        key=10,
        title="Fees, field-level restrictions and invoices",
        blocked=[8, 7],
        items=["DEAL-05", "AUTHZ-06", "REP-07", "ROLE-01:4,5"],
        what="""Partners record retainer (EUR/month) and success-fee terms (% of EV or fixed, minimum fee, Lehman tiers, retainers creditable) and see the expected fee from current EV; at closing the final fee is computed and an invoice task goes to back-office; fee changes after engagement need a reason and an amended letter link. Fee fields are hidden from analysts in UI, exports, API and filters; compliance sees fees but not deal notes; partners edit fees only on their staffed deals; admin changes to field visibility per role are audited. Back-office records invoices (retainer or success fee, amount, sent, paid) on a mandate, which completes the invoice task.""",
    ),
    dict(
        key=11,
        title="Wall-crossing requests, delegation, break-glass and quarterly access review",
        blocked=[9, 7],
        items=["AUTHZ-04", "AUTHZ-07", "AUTHZ-08", "ADM-05", "AUTH-02:5"],
        what="""A user who knows a code name requests access with a reason; the deal partner (comment only) and compliance (decides) get an approval task; approval adds the user with an expiry (default 30 days) recorded in the wall-crossing register, rejection notifies with the reason, and conflicts with the requester's other deals are highlighted. Partners delegate approvals for a date range; the delegate sees only the approval context and approvals record "on behalf of". Admins invoke break-glass with a reason and a fresh 2FA code for 4 hours of read-only, no-export access, notifying compliance and the deal partner. Each quarter every deal partner confirms or removes staffed users within 14 days, else compliance is escalated. Sensitive actions (break-glass, mass export, role change) re-ask the 2FA code.""",
    ),
    dict(
        key=12,
        title="Origination pipeline: opportunities, pitches and win/lose",
        blocked=[9, 10],
        items=["ORI-01", "ORI-02", "ORI-03", "ORI-04"],
        what="""Partners log opportunities on a company (type, trigger, estimated EV, probability) that move through Lead, Contacted, Meeting held, Pitch, Engagement letter sent, Won, Lost, On hold, visible only to the owner and invited colleagues through the same deal-access policy. A company with an active mandate shows a conflict warning. Pitch deck links and credentials (closed deals with tombstone allowed, searchable by sector and size) attach to the opportunity. Won creates a mandate with company, team and fee draft copied and sends it to the conflict check; Lost needs a reason; On hold creates a task on the revisit date; 90 days without activity on a prospect tasks the relationship holder.""",
    ),
    dict(
        key=13,
        title="Investor profiles, buyer long list, buyer status grid and NDA tracking",
        blocked=[8, 9],
        items=["CO-04", "BUY-01", "BUY-02", "BUY-03", "BUY-04", "AUTHZ-02:5", "CON-01:5"],
        what="""Buyer companies carry investment criteria (sectors, geographies, ticket size, EV/EBITDA range, majority/minority), PE funds link portfolio companies as group entities, stale profiles (12 months) are flagged, and past decline reasons from accessible closed deals are listed. Suggest buyers ranks matching companies for a deal and adds them in bulk (skipping duplicates, warning on conflicts or the client's exclusion list, Do not contact contacts blocked), each with an owner and rationale. The list exports to Excel for client approval and only Approved buyers can be contacted. A buyer-by-status grid tracks status with date and user, enforces prerequisites (IM sent needs NDA signed), supports bulk updates, requires decline reasons, and reminds owners after 14 idle days. NDAs track sent, markup, agreed and signed dates with links, remind after 10 pending days, and store standstill/non-solicit end dates on the buyer company. Non-staffed users never see buyer status or offers on a contact.""",
    ),
    dict(
        key=14,
        title="Offers and bid comparison, templates, process letters, funnel and client report",
        blocked=[13, 10],
        items=["BUY-05", "BUY-06", "BUY-07", "ADM-07", "REP-05", "CON-01:3", "GDPR-01:2", "DEAL-03:1"],
        what="""Directors capture versioned indicative and binding offers (EV, equity value, structure, conditions, financing certainty), flagged late after the bid deadline, compared in a table sorted by EV with implied EV/EBITDA; analysts see offer values. Admins manage EN/FR/NL letter and report templates with merge fields. Process letters merge each buyer contact's salutation and language, exclude buyers without a signed NDA when referencing the IM, exclude opted-out contacts, and log an activity. The funnel shows counts and conversion per status and exports to PDF. One click produces the client status report PDF (funnel, timeline vs plan, next steps, no notes or fees) in the client's language, logged as an activity. The deal page now shows every section: summary, team, timeline, buyers, activities, tasks, document links, key dates and fees.""",
    ),
    dict(
        key=15,
        title="Email logging by BCC/forward and private calendar feed",
        blocked=[8, 7],
        items=["ACT-04", "ACT-05", "CON-02:2", "AUTHZ-02:3"],
        what="""Each user has a personal CRM logging address. Inbound mail (a webhook from the mail provider's inbound parse, behind a port) from a known CRM user is matched to contacts by sender and recipients and logged on their timelines, with attachment names only; unknown senders are rejected; unmatched mail lands in the user's Unmatched inbox; a [CodeName] subject links the deal only if the user is staffed. Contacts show last interaction date and count per colleague. Each user copies a private iCal feed URL (regenerable, old URL dies) with their meetings, tasks and milestones; deal events and any non-staffed reference show the code name only.""",
    ),
    dict(
        key=16,
        title="Global search, relationship holders, merge duplicates and Excel import",
        blocked=[7],
        items=["CON-03", "CON-02:1", "CON-04", "CON-05"],
        what="""Global search (3+ characters, under 1 second at 100k records, PostgreSQL full-text with pg_trgm + unaccent) returns companies, contacts and deals grouped by type, fuzzy on typos and accents, excluding inaccessible deals, with create-from-search and saved, shareable filters. Users add themselves as relationship holders with strength 1-3, shown on the contact and in results. Merging duplicates picks field values, moves activities, deals and links to the survivor, is audited and admin-undoable for 30 days, and is blocked (compliance only) when a record sits on a deal the user cannot access. Admins import contacts and companies from Excel with column mapping, a new/duplicate/error preview, a downloadable error file, and background processing with notification above 50,000 rows.""",
    ),
    dict(
        key=17,
        title="Home page, firm pipeline dashboard, fee forecast and win/loss report",
        blocked=[10, 12],
        items=["REP-01", "REP-02", "REP-03", "REP-04", "AUTHZ-02:4", "ROLE-01:3"],
        what="""The home page (under 2 seconds) shows the user's active deals by stage, tasks due this week, upcoming key dates, and guidance for new users. The firm dashboard shows mandates by stage and type and probability-weighted expected fees by quarter, counting non-staffed deals only in aggregates. Back-office sees a 12-month fee forecast of retainers and success fees with actual vs forecast from invoices, exportable to Excel. Partners run a win/loss report per period (pitches, win rate, top lost reasons, average duration, average EV/EBITDA by sector). Reports and exports never include or reveal non-staffed deals. Read-only users get the aggregated dashboards and nothing else.""",
    ),
    dict(
        key=18,
        title="Public API with personal tokens and OAuth client credentials",
        blocked=[6],
        items=["NFR-05"],
        what="""API clients authenticate with personal API tokens issued in the CRM or OAuth 2.0 client credentials (no basic auth or shared keys). The same role, deal-team and field rules apply as in the UI because every endpoint uses the shared deal-access policy; writes are audited like UI changes; clients over 100 requests per minute get 429 with Retry-After. The OpenAPI spec covers every endpoint with examples and a CI check fails when it drifts; versioning keeps old versions alive 6 months after a breaking change. Deal-scoped API endpoints register in the deal-access matrix.""",
    ),
    dict(
        key=19,
        title="Offboarding with ownership hand-over, GDPR rights and export controls",
        blocked=[4, 7, 18],
        items=["AUTH-05", "ADM-03", "GDPR-02", "GDPR-03", "REP-06"],
        what="""Deactivating a user ends all sessions and API tokens immediately, refuses password resets, requires choosing a new owner for their contacts, tasks and deals, and shows the admin a confirmation of sessions ended and records awaiting reassignment; their history stays visible as (inactive), and reactivation restores the role without deal-team memberships. Compliance exports all data about a person as a file and erases (anonymises) it unless a legal hold such as AML 10-year retention applies. A monthly job asks owners to keep or anonymise contacts without interaction for 5 years. Analysts exporting more than 500 contacts need partner approval, and every export logs user, time, filter and row count.""",
    ),
    dict(
        key=20,
        title="Production readiness: languages, accessibility, security, performance and availability",
        blocked=[3, 11, 14, 15, 16, 17, 19],
        items=["NFR-01", "NFR-02", "NFR-03", "NFR-04", "cross"],
        what="""Close out the non-functional requirements across the finished product. Every label, email and error exists in EN, FR and NL; every page works at 375 px without horizontal scroll; an axe-based Playwright run meets WCAG 2.1 AA; dates and numbers use Belgian formats. Security: TLS 1.2+ only, AES-256 at rest, EU-only data and backups asserted in `infra/`, an OWASP ZAP baseline in CI, 35-day backups with a logged quarterly restore test, and a 30-day fix rule for pentest findings. Performance: a k6 load test against a seeded 50-user / 200k-contact dataset and a 10-second all-deals report. Availability: uptime monitoring for 99.5% in business hours, a documented RPO 24 h / RTO 8 h drill, and 48-hour maintenance notices. Finally verify the cross-cutting criteria over the whole product. Nothing is deployed without the user's say-so.""",
    ),
]

assigned: dict[tuple[str, int], int] = {}
errors = []
for t in T:
    t["criteria"] = []
    t["covers"] = []
    for item in t["items"]:
        if item == "cross":
            t["covers"].append("cross-cutting")
            for i, c in enumerate(cross, 1):
                key = ("CROSS", i)
                if key in assigned:
                    errors.append(f"dup {key}")
                assigned[key] = t["key"]
                t["criteria"].append(("Cross-cutting", c))
            continue
        sid, _, idx = item.partition(":")
        if sid not in stories:
            errors.append(f"unknown story {sid}")
            continue
        crit = stories[sid]["criteria"]
        nums = [int(n) for n in idx.split(",")] if idx else list(range(1, len(crit) + 1))
        t["covers"].append(sid if not idx else f"{sid} (criteria {idx})")
        for n in nums:
            key = (sid, n)
            if key in assigned:
                errors.append(f"dup {key} in {t['key']} and {assigned[key]}")
            assigned[key] = t["key"]
            t["criteria"].append((sid, crit[n - 1]))

for sid in order:
    for n in range(1, len(stories[sid]["criteria"]) + 1):
        if (sid, n) not in assigned:
            errors.append(f"missing {sid}:{n}")
for i in range(1, len(cross) + 1):
    if ("CROSS", i) not in assigned:
        errors.append(f"missing cross {i}")

keys = {t["key"] for t in T}
for t in T:
    for b in t["blocked"]:
        if b not in keys or b >= t["key"]:
            errors.append(f"bad blocker {b} on {t['key']}")

total = sum(len(s["criteria"]) for s in stories.values()) + len(cross)
print(f"stories={len(stories)} criteria={total} assigned={len(assigned)}")
if errors:
    print("\n".join(errors))
    sys.exit(1)

OUT.mkdir(exist_ok=True)
manifest = []
for t in T:
    lines = ["## What to build", "", t["what"], "", "## User stories covered", ""]
    lines += [f"- {c}" for c in t["covers"]]
    lines += ["", "## Acceptance criteria", ""]
    last = None
    for sid, c in t["criteria"]:
        if sid != last:
            label = sid if sid == "Cross-cutting" else f"{sid}: {stories[sid]['title']}"
            lines += ["", f"**{label}**", ""] if last else [f"**{label}**", ""]
            last = sid
        lines.append(f"- [ ] {c}")
    lines += ["", "## Blocked by", "", "{{BLOCKED_BY}}", ""]
    lines += ["## Notes", "", "Source spec: `docs/specs/ma-crm.md` (kept local). Criteria above are copied verbatim from it; `(derived)` marks wording not in the original requirements document.", ""]
    body = "\n".join(lines)
    path = OUT / f"{t['key']:02d}.md"
    path.write_text(body)
    manifest.append(dict(key=t["key"], title=t["title"], blocked=t["blocked"], file=str(path)))
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
print("ok", len(T), "tickets")
