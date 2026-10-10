# Spec: M&A CRM

Source: "M&A CRM – User Stories & Acceptance Criteria", Oct 10, 2026, @Serge. Story and criterion wording below is copied verbatim from that source. Anything marked `(derived)` was written during spec synthesis and accepted by the user.

## Problem Statement

An M&A advisory firm runs origination, mandates and buyer processes across partners, deal teams, compliance and back-office. Confidential deal information must stay inside the deal team (a Chinese wall), conflicts between mandates must be caught before work starts, AML/KYC and GDPR obligations must be provable, and fee income must be forecastable. Today none of this lives in one system, so access control, conflict checks, buyer tracking and reporting depend on spreadsheets and memory.

## Solution

A web CRM, usable on desktop and phone, in EN, FR and NL, where every user has exactly one role and sees only the deals they are staffed on. It covers authentication with mandatory 2FA, role and deal-team authorization, user administration, companies and contacts, origination and pitches, the mandate pipeline, the buyer process, activities and tasks, reporting and fee forecasting, and GDPR, audit and non-functional requirements. Access is enforced server-side on every request, including API, search, exports, notifications and calendar feeds.

### Roles

| Role | Purpose | Default access |
|---|---|---|
| Admin | IT / ops configuration | Users, roles, settings, audit log; no deal content unless staffed |
| Partner | Owns relationships and mandates | Create mandates, approve conflicts, fees of own deals, firm-wide aggregated dashboard |
| Director / Manager | Runs deal execution | Full edit on staffed deals, assign team, manage buyer list |
| Analyst / Associate | Executes work | Edit on staffed deals, no fee editing |
| Compliance / Back-office | KYC, conflicts, invoicing | Conflict register, KYC, fee and invoice fields; read-only deal summary |
| Read-only | Oversight | Aggregated dashboards only |

Format: Given context / When action / Then result. A non-staffed user is any user not on the deal team.

## User Stories

Stories are numbered by their stable ID. Tickets reference these IDs.

### Epic 0: Roles (derived)

ROLE-01. (derived) As an admin, I want the six roles of the role table seeded with their default access, so that the firm can start without configuring permissions by hand
- [ ] (derived) Given a fresh install, when the system starts, then the roles Admin, Partner, Director / Manager, Analyst / Associate, Compliance / Back-office and Read-only exist with the default access described in the role table.
- [ ] (derived) Given role Admin, when they are not staffed and not using break-glass (AUTHZ-08), then no deal content is visible to them.
- [ ] (derived) Given role Read-only, when they use the CRM, then only aggregated dashboards are available and every deal, company, contact and record endpoint returns Not found or 403.
- [ ] (derived) Given role Compliance / Back-office, when they open a deal they are not staffed on, then they see a read-only deal summary, the conflict register, KYC, fee and invoice fields.
- [ ] (derived) Given role Partner, when they open fee fields, then they can edit fees only on deals where they are on the deal team.

### Epic 1: Authentication

Login flow: user enters email and password, the CRM verifies the password, asks for a 6-digit code from an authenticator app, checks the user is active and has a role, then opens the home page. No external identity provider is used.

AUTH-01. As a staff member, I want to log in with my email and password so that only I can access my account.
- [ ] Given I am not logged in, when I open any CRM URL, then I am redirected to the CRM login page.
- [ ] Given a correct email and password, when I submit, then I am asked for my second factor (AUTH-02) and then land on the page I originally requested.
- [ ] Given a wrong email or password, when I submit, then I see Invalid email or password, without saying which one was wrong.
- [ ] Given my account is deactivated or has no role, when I log in with correct credentials, then access is denied and the attempt is logged.
- [ ] Given the login form, when submitted, then it is protected against brute force (rate limit per IP and per account) and CSRF.
- [ ] Given a successful login, when it completes, then last login date, IP and device are stored and shown on my profile.
- [ ] Given a deep link to a deal I cannot access, when I log in, then I land on Not found, not on the deal.
- [ ] Given the login service has an error, when I submit, then I see a clear error with retry and no technical details.

AUTH-02. As compliance, I want a second factor on every login so that a leaked password alone does not expose deal data.
- [ ] Given my first login, when my password is set, then I must enrol an authenticator app (TOTP, any standard app) by scanning a QR code and confirming a code.
- [ ] Given enrolment, when completed, then I get 10 one-time recovery codes to download once.
- [ ] Given a correct password, when I enter a wrong code 5 times, then the account is locked 15 minutes (see AUTH-06).
- [ ] Given I tick Trust this device, when I log in again from it within 30 days, then the code is not asked (admin can disable this).
- [ ] Given a sensitive action (break-glass, mass export, role change), when triggered, then the code is asked again even within an active session.
- [ ] Given I lost my phone, when an admin resets my 2FA, then I must re-enrol at next login and the reset is audited.

AUTH-03. As compliance, I want idle sessions to expire so that an unattended laptop does not expose deals.
- [ ] Given I am inactive for 30 minutes (configurable), when I next act, then I am asked to re-authenticate and unsaved form data is kept locally.
- [ ] Given 2 minutes before timeout, when I am inactive, then I see a warning with a Stay logged in button.
- [ ] Given an absolute session age of 12 hours, when reached, then re-authentication is required regardless of activity.
- [ ] Given I have the CRM open in two tabs, when one tab is active, then the other does not time out.
- [ ] Given an admin, when they change the timeout values, then the new values apply to sessions created after the change.
- [ ] Given the access token expires, when a refresh token is valid, then the session renews silently without losing my page.

AUTH-04. As a user, I want to log out so that nobody else can use my session.
- [ ] Given I am logged in, when I click Log out, then my CRM session and refresh token are revoked and I see the login page.
- [ ] Given I logged out, when I press the browser Back button, then no cached deal page is shown.
- [ ] Given I click Log out everywhere on my profile, when confirmed, then all my sessions on all devices end.
- [ ] Given unsaved changes, when I click Log out, then I am warned before leaving.

AUTH-05. As an admin, I want access cut when someone leaves so that ex-employees cannot see deals.
- [ ] Given a user is deactivated in the CRM, when they are logged in, then all their sessions end immediately and their next request is refused.
- [ ] Given a deactivated user, when they try to reset their password, then no reset email is sent.
- [ ] Given a leaver has active API tokens, when they are deactivated, then all tokens are revoked.
- [ ] Given offboarding, when completed, then the admin sees a confirmation listing sessions ended and records awaiting reassignment (ADM-03).

AUTH-06. As compliance, I want unusual logins flagged so that breaches are caught early.
- [ ] Given a login from a new country or device, when it succeeds, then the user and admin get an email alert.
- [ ] Given 5 failed or denied attempts in 15 minutes, when the 6th occurs, then the account is locked 15 minutes and the admin is alerted.
- [ ] Given a locked account, when an admin unlocks it, then the user can log in immediately and the unlock is audited.
- [ ] Given a login from an IP outside the EU while the user is flagged as travelling, when it succeeds, then no alert is sent.

AUTH-07. As a partner, I want to use the CRM on my phone so that I can check a deal between meetings.
- [ ] Given any phone browser, when I log in with password and code, then I get the responsive web app.
- [ ] Given an admin setting, when mobile access is set to read-only, then edit and export actions are hidden on screens under 768 px.
- [ ] Given a lost phone, when I or an admin click Log out everywhere, then all sessions on that device are revoked.
- [ ] Given a mobile session, when idle 15 minutes, then it times out (shorter than desktop).

AUTH-08. As a new user, I want to set my own password from an invitation so that nobody else knows it.
- [ ] Given an admin created my account (ADM-01), when I open the invitation link, then I can set a password and enrol 2FA.
- [ ] Given the link, when older than 72 hours or already used, then it is refused and I can ask the admin to resend.
- [ ] Given passwords are stored, when saved, then only a salted hash (Argon2id or bcrypt) is kept, never the plain password.

AUTH-09. As compliance, I want strong passwords so that accounts are hard to guess.
- [ ] Given I set a password, when it is shorter than 12 characters, then it is rejected with the rule shown.
- [ ] Given a password found in known breach lists or containing my name or email, when submitted, then it is rejected.
- [ ] Given my last 5 passwords, when I reuse one, then it is rejected.
- [ ] Given the policy, when an admin changes it, then existing users must comply at their next password change (no forced periodic expiry, per NIST guidance).

AUTH-10. As a user, I want to reset my password by email so that I can get back in without calling IT.
- [ ] Given I click Forgot password and enter an email, when submitted, then I always see the same message whether or not the account exists.
- [ ] Given a valid account, when the email is sent, then the reset link is single-use and expires in 30 minutes.
- [ ] Given I reset my password, when done, then all my other sessions end, 2FA is still required, and I get a confirmation email.
- [ ] Given 3 reset requests in 1 hour, when a 4th is made, then it is refused.

AUTH-11. As a user, I want to change my password from my profile so that I can rotate it if I suspect a leak.
- [ ] Given I am logged in, when I enter current password, new password (meeting AUTH-09) and a 2FA code, then the password changes and other sessions end.

AUTH-12. (derived) As a user travelling outside the EU, I want to be flagged as travelling for a date range, so that my logins abroad do not raise false alerts
- [ ] (derived) Given my profile or an admin on my user record, when a travelling date range is set, then the flag is active during that range and ends automatically after it.

### Epic 2: Authorization

Access = role (what you can do) AND deal team (which deals you see). Both are checked server-side on every request, including API, search, exports and notifications.

AUTHZ-01. As an admin, I want each role to map to a permission set so that users only do what their job needs.
- [ ] Given the roles in the context table, when a user calls an action outside their permissions, then the server returns 403 and the UI hides the control.
- [ ] Given an admin edits a role's permissions, when saved, then the change applies at the next request and is logged in the audit log.
- [ ] Given a user has no role, when they log in, then they are denied (see AUTH-01).
- [ ] Given a permission matrix screen, when an admin opens it, then roles are columns, permissions are rows, and it is exportable for audit.
- [ ] Given a user with two roles is not allowed, when an admin assigns a second role, then the action is blocked (one role per user in v1).

AUTHZ-02. As a partner, I want only the deal team to see a mandate so that confidential information does not leak inside the firm.
- [ ] Given I am not on the deal team, when I search, list or open by URL, then the deal does not appear and a direct URL returns Not found (not Forbidden, to avoid confirming existence).
- [ ] Given I am not staffed, when I view a shared company record linked to the deal, then the deal link and deal notes are hidden.
- [ ] Given a deal has a code name, when non-staffed users see any reference to it (e.g. in a calendar), then only the code name shows, never the target name.
- [ ] Given I am not staffed, when I run any report or export, then rows from that deal are excluded and totals do not reveal it.
- [ ] Given I am not staffed, when I open a contact who is a buyer on that deal, then I do not see their buyer status or offers.
- [ ] Given an automated test suite, when each release is built, then access tests for every deal-scoped endpoint pass (UI, API, search, export, notifications).
- [ ] Given a deal is closed, when 12 months pass, then access remains limited to the former deal team plus compliance.
- [ ] (derived) Given a deal closed for more than 12 months, when compliance opens it, then compliance has read-only access and no other user gains access.

AUTHZ-03. As the deal partner or director, I want to add and remove team members so that access follows staffing.
- [ ] Given I am deal partner or director, when I add a user, then they get access immediately and are notified.
- [ ] Given I remove a user, when they next request the deal, then access is gone; their past notes stay attributed to them.
- [ ] Given an analyst, when they try to add someone, then the action is not available.
- [ ] Given a deal, when the last partner is removed from the team, then the save is blocked: every deal needs one lead partner.
- [ ] Given a team change, when saved, then it appears in the wall-crossing register with who, when and by whom.

AUTHZ-04. As a user, I want to request access to a deal so that I can contribute when needed.
- [ ] Given I know the code name, when I request access with a reason, then the deal partner and compliance get an approval task.
- [ ] Given compliance approves, when saved, then I am added with an expiry date (default 30 days) and the crossing is recorded in the wall-crossing register.
- [ ] Given access expires, when the date passes, then I lose access automatically.
- [ ] Given a request is rejected, when saved, then I am notified with the reason and the deal stays invisible.
- [ ] Given the requester is on a conflicting deal, when compliance reviews, then the conflict is highlighted.
- [ ] (derived) Given a wall-crossing approval task, when the deal partner acts on it, then they can only add a comment; the approve or reject decision belongs to compliance.

AUTHZ-05. As compliance, I want a conflict check on every new mandate so that we do not advise both sides.
- [ ] Given a new mandate is created, when the target, client and known counterparties are entered, then the system checks all companies (including group entities) against active and 24-month historic mandates.
- [ ] Given a potential conflict, when found, then the mandate stays in status Conflict review and only compliance sees what it conflicts with.
- [ ] Given compliance clears or rejects, when saved, then the decision, reason and approver are logged and the mandate moves to Active or Rejected.
- [ ] Given fuzzy name matching, when a name differs only by legal form or accents (e.g. NV vs SA), then it is still flagged.
- [ ] Given a conflict review older than 5 working days, when not decided, then the lead partner and compliance get a reminder.
- [ ] Given a new counterparty is added to an active deal later, when saved, then the conflict check re-runs for that party.

AUTHZ-06. As a partner, I want fee fields hidden from analysts so that commercial terms stay need-to-know.
- [ ] Given role Analyst, when viewing a mandate, then fee, retainer and success-fee fields are hidden in UI, exports and API.
- [ ] Given role Compliance, when viewing, then fee fields are visible but deal notes are not.
- [ ] Given a hidden field, when the user searches or filters by it, then the filter is not offered.
- [ ] Given an admin, when they change field visibility per role, then the change is audited.

AUTHZ-07. As a partner going on holiday, I want to delegate my approvals so that deals are not blocked.
- [ ] Given I set a delegate and date range, when an approval arrives in that range, then it goes to my delegate and to me.
- [ ] Given the range ends, when the date passes, then delegation stops automatically.
- [ ] Given a delegate, when they approve, then the record shows approved by delegate on behalf of the partner.
- [ ] Given a delegate is not staffed on the deal, when an approval arrives, then they see only the approval context, not the full deal.

AUTHZ-08. As an admin, I want emergency access to a deal so that I can fix data issues.
- [ ] Given I invoke break-glass with a reason, when confirmed, then I get read access for 4 hours and compliance plus the deal partner are notified immediately.
- [ ] Given break-glass is used, when 4 hours pass, then access is removed automatically.
- [ ] Given break-glass, when active, then the access is read-only: no edits or exports.

### Epic 3: User administration

ADM-01. As an admin, I want to create users and invite them by email so that onboarding takes minutes.
- [ ] Given I enter first name, last name, email, title and role, when I save, then the account is created as Invited and an invitation email is sent (AUTH-08).
- [ ] Given an invited user has not accepted after 72 hours, when I view the user list, then I can resend the invitation.
- [ ] Given an email already exists in the CRM, when I create the user, then I am told the user exists.
- [ ] Given a CSV of users, when I import it, then each row is validated and invitations are sent in bulk.
- [ ] Given a user is created, when saved, then they get a welcome email with the CRM link and their role.

ADM-02. As an admin, I want to change a user's role so that promotions are reflected.
- [ ] Given I change Analyst to Director, when saved, then permissions change at the next request and the change is audited with old and new value.
- [ ] Given I try to remove the last Admin, when saving, then it is blocked.

ADM-03. As an admin, I want to deactivate a leaver and hand over their records so that nothing is orphaned.
- [ ] Given I deactivate a user, when they own contacts, tasks or deals, then I must choose a new owner before confirming.
- [ ] Given a deactivated user, when anyone views their history, then it stays visible with the label (inactive).
- [ ] Given a deactivated user, when reactivated, then they get their role back but no deal team memberships (re-staffing needed).

ADM-04. As an admin, I want to see all users with role, status and last login so that I can review access.
- [ ] Given the list, when filtered by role or status, then results update and can be exported to CSV.
- [ ] Given a user has not logged in for 90 days, when the list loads, then they are flagged as dormant.

ADM-05. As compliance, I want partners to confirm their teams' access each quarter so that stale access is removed.
- [ ] Given a new quarter starts, when the review opens, then each deal partner gets a list of staffed users to confirm or remove within 14 days.
- [ ] Given no response after 14 days, when the deadline passes, then compliance is escalated.

ADM-06. As an admin, I want to manage picklists (sectors, deal stages, deal types, countries) so that data is consistent.
- [ ] Given I edit a picklist value, when it is in use, then I can rename or deactivate it but not delete it.
- [ ] Given I add a value, when saved, then it appears in all three languages once translations are filled (EN required).

ADM-07. (derived) As an admin, I want to manage letter and report templates in EN, FR and NL, so that process letters and client reports use the firm's wording
- [ ] (derived) Given the templates screen, when I create or edit a template with merge fields (contact, salutation, code name, deal fields), then it is stored per language (EN, FR, NL) and available to BUY-06 and REP-05.
- [ ] (derived) Given a template change, when saved, then the change is audited and earlier generated documents are unaffected.

### Epic 4: Companies & contacts

CO-01. As a user, I want to create a company with its Belgian enterprise number so that records are reliable.
- [ ] Given I enter an enterprise number (BE0xxx.xxx.xxx), when it is valid, then legal name, address, NACE code and legal form are pre-filled from the KBO/BCE register.
- [ ] Given a company with the same number or a similar name exists, when I save, then I see the duplicate and can open it instead.
- [ ] Required: name, country, type (Target, Strategic buyer, Financial investor / PE, Lender, Advisor, Other).
- [ ] Given an invalid enterprise number (checksum fails), when I save, then an inline error is shown.
- [ ] Given a foreign company, when I pick a country other than Belgium, then the enterprise number is optional and a VAT or registry number field appears.
- [ ] Given the KBO/BCE lookup fails, when I save, then I can continue with manual entry.

CO-02. As an analyst, I want key financials per year so that I can screen targets and buyers.
- [ ] Given a company, when I add a year, then I can enter revenue, EBITDA, net debt, FTE, all in EUR thousands.
- [ ] Given filed accounts exist at the National Bank (NBB), when I click Import, then the latest 3 years are loaded with source and date.
- [ ] Given a manual value overrides an imported one, when saved, then both are kept and the override is labelled with user and date.
- [ ] Given figures in another currency, when entered, then the original currency and the EUR rate used are stored.

CO-03. As a user, I want to link parent and subsidiaries so that conflict checks and buyer lists see the whole group.
- [ ] Given I set a parent, when saved, then the group tree shows on both companies and AUTHZ-05 includes all group entities.
- [ ] Given I set a parent that would create a loop (A parent of B parent of A), when I save, then it is blocked.

CO-04. As a director, I want PE funds and strategics to carry their investment criteria so that buyer lists are faster to build.
- [ ] Given a buyer company, when I fill sectors, geographies, ticket size (min/max EUR m), EV/EBITDA range and majority/minority, then it is searchable in BUY-01.
- [ ] Given a PE fund, when I link portfolio companies, then they show as group entities.
- [ ] Given a profile not updated for 12 months, when shown, then it is flagged as possibly outdated.
- [ ] Given a buyer declined in past deals, when viewed, then decline reasons from closed deals I can access are listed.

CON-01. As a user, I want to store a person with their role at a company so that I know who to call.
- [ ] Given I enter name, email, company, function, when an email already exists, then I am warned of a duplicate.
- [ ] Given a contact changes employer, when I update the company, then the old role is kept as history with end date.
- [ ] Given a contact, when I set language (EN, FR, NL) and salutation, then templates use them.
- [ ] Given an invalid email or phone format, when I save, then an inline error is shown; phone stored in E.164.
- [ ] Given a contact marked Do not contact, when anyone tries to add them to a mailing or buyer outreach, then a warning blocks it.

CON-02. As a partner, I want to see who in the firm knows a contact and how well so that we pick the right person for outreach.
- [ ] Given a contact, when I add myself as relationship holder with strength (1-3), then it shows on the contact and in search results.
- [ ] Given emails and meetings are synced (ACT-04), when computed, then last interaction date and count per colleague are shown.

CON-03. As a user, I want global search across companies, contacts and deals so that I find anything in seconds.
- [ ] Given I type 3+ characters, when results return (under 1 second for 100k records), then they are grouped by type and exclude deals I cannot access (AUTHZ-02).
- [ ] Given saved filters (e.g. PE funds, Benelux, ticket 10-50m), when I save one, then I can reuse and share it.
- [ ] Given no results, when the search returns, then I can create the record from the search box.
- [ ] Given a typo or missing accent, when I search, then fuzzy matching still finds it.

CON-04. As a user, I want to merge two records so that history is in one place.
- [ ] Given two duplicates, when I merge and pick field values, then all activities, deals and links move to the survivor and the merge is audited.
- [ ] Given a merge, when done within 30 days, then an admin can undo it.
- [ ] Given one of the records is on a deal I cannot access, when I try to merge, then merge is blocked and compliance must do it.

CON-05. As an admin, I want to import contacts and companies from Excel so that we migrate the legacy data.
- [ ] Given a file, when I map columns, then a preview shows new, duplicate and error rows before I confirm.
- [ ] Given errors, when import completes, then an error file is downloadable.
- [ ] Given a file over 50,000 rows, when uploaded, then it is processed in the background and I am notified on completion.

### Epic 5: Origination & pitches

ORI-01. As a partner, I want to log a potential mandate before it is signed so that the origination pipeline is visible.
- [ ] Given a company, when I create an opportunity with type (sell-side, buy-side, fundraising, debt advisory), trigger (succession, growth, carve-out, distress), estimated EV and probability, then it appears in the origination pipeline.
- [ ] Stages: Lead, Contacted, Meeting held, Pitch, Engagement letter sent, Won, Lost, On hold.
- [ ] Given an opportunity, when created, then it is visible only to its owner and invited colleagues (same wall logic as deals).
- [ ] Given an opportunity on a company with an active mandate, when created, then a conflict warning is shown.

ORI-02. As a director, I want to attach pitch materials and credentials to an opportunity so that the team reuses past work.
- [ ] Given an opportunity, when I link a pitch deck (document link) and select relevant past deals as credentials, then they are listed on the opportunity.
- [ ] Given I search credentials by sector and size, when results show, then only closed deals marked public (tombstone allowed) appear.

ORI-03. As a partner, I want to record the outcome so that we learn why we win or lose.
- [ ] Given stage Won, when I confirm, then a mandate is created with company, team and fee draft copied, and it goes to conflict check (AUTHZ-05).
- [ ] Given stage Lost, when I save, then a lost reason is required (fee, competitor, timing, client decided not to sell) and competitor advisor is optional.
- [ ] Given an opportunity is On hold, when the revisit date arrives, then the owner gets a task.

ORI-04. As a partner, I want reminders for dormant prospects so that relationships do not go cold.
- [ ] Given no activity on a prospect for 90 days (configurable), when the threshold passes, then the relationship holder gets a task to reconnect.

ORI-05. As compliance, I want the signed engagement letter and KYC done before work starts so that we meet anti-money-laundering rules.
- [ ] Given a mandate, when engagement letter is not uploaded or KYC status is not Approved, then the mandate cannot move past Preparation.
- [ ] Given KYC, when compliance records UBO check, ID check and PEP/sanctions screening, then status becomes Approved with date and reviewer.
- [ ] Given KYC is older than 12 months on a running mandate, when the date passes, then compliance gets a refresh task.
- [ ] Given a sanctions hit, when recorded, then the mandate is frozen and only compliance can unfreeze it.

### Epic 6: Mandates / deal pipeline

Sell-side stages: Conflict review, Preparation, Marketing (teaser/NDA), Information memorandum, Indicative offers, Due diligence, Binding offers, SPA negotiation, Signing, Closing, Closed won / Aborted.

DEAL-01. As a partner, I want to create a mandate with a code name so that the client stays confidential.
- [ ] Given I create a mandate, when I save, then code name, client, type, sector, lead partner and estimated EV are required, and the code name must be unique.
- [ ] Given creation, when saved, then the conflict check runs (AUTHZ-05) and the creator is added to the deal team.
- [ ] Given a code name, when saved, then it cannot contain the client or target name (checked against linked companies).
- [ ] Given a mandate in Conflict review, when anyone other than compliance and the creator searches, then it is invisible.
- [ ] (derived) Given a mandate of type buy-side, fundraising or debt advisory, when created, then it uses the same stage list as sell-side in v1.

DEAL-02. As a director, I want a Kanban of my deals by stage so that I see where everything stands.
- [ ] Given the board, when I drag a deal to a new stage, then the stage and date are saved and the move is in the deal history.
- [ ] Given a stage with exit criteria (e.g. Due diligence needs a data room link), when criteria are missing, then the move is blocked with the reason.
- [ ] Given filters (partner, type, sector, stage), when applied, then only accessible deals show.
- [ ] Given a stage moves backwards, when saved, then a reason is required.
- [ ] Given a list view toggle, when I switch, then the same deals show as a sortable table.

DEAL-03. As a team member, I want one page per deal so that everything is in one place.
- [ ] Given a deal, when opened, then I see summary, team, timeline, buyers (Epic 7), activities, tasks, documents links, key dates and fees (per AUTHZ-06).
- [ ] Given two users edit the same field, when the second saves, then they see a conflict message and the newer version, not a silent overwrite.
- [ ] Given a deal history tab, when opened, then every change shows who, when, old and new value.

DEAL-04. As a director, I want planned vs actual dates per milestone so that slippage is visible.
- [ ] Given planned dates, when an actual date is later, then the milestone is shown in red with days late.
- [ ] Given a milestone is due in 3 days, when the date approaches, then the deal team is notified.

DEAL-05. As a partner, I want to record retainer and success-fee terms so that revenue is forecastable.
- [ ] Given the fee section, when I enter retainer (EUR/month), success fee (% of EV or fixed, minimum fee, Lehman scale tiers), then expected fee is calculated from current estimated EV.
- [ ] Given closing, when final EV is entered, then the final success fee is calculated and an invoice task goes to back-office.
- [ ] Given a fee change after engagement, when saved, then the partner must add a reason and attach the amended letter link.
- [ ] Given retainers are creditable against the success fee, when the box is ticked, then the final fee deducts retainers paid.

DEAL-06. As a partner, I want to close a deal with outcome data so that we build credentials and statistics.
- [ ] Given Closed won, when I confirm, then final EV, buyer, multiple (EV/EBITDA) and closing date are required, and I choose whether a public tombstone is allowed.
- [ ] Given Aborted, when I confirm, then an abort reason is required and the deal becomes read-only.
- [ ] Given a closed deal, when a partner reopens it, then a reason is required and the reopen is audited.

DEAL-07. As a team member, I want to link the deal's file folder and the virtual data room so that documents are not duplicated in the CRM.
- [ ] Given a deal, when I paste any https URL (file server, VDR), then it opens in a new tab; the CRM stores links, not files.
- [ ] Given a link, when saved, then it has a label (e.g. IM, Financials, VDR) and is visible only to the deal team.

DEAL-08. (derived) As an admin, I want to configure exit criteria per stage, so that stage gates match the firm's process
- [ ] (derived) Given the stage settings, when I set an exit criterion on a stage (required field, required document link label, or KYC/engagement letter gate), then DEAL-02 enforces it on the next move.

### Epic 7: Buyer process

Buyer status per deal: Long list, Client approved, Contacted, Teaser sent, NDA sent, NDA signed, IM sent, Indicative offer, Data room access, Binding offer, Preferred bidder, Declined / Dropped.

BUY-01. As an analyst, I want to generate a buyer long list from investor profiles so that I start from data, not memory.
- [ ] Given the target's sector, size and geography, when I run Suggest buyers, then companies matching CO-04 criteria are ranked and I can add them in bulk.
- [ ] Given a buyer is already on the list, when I add it again, then it is skipped.
- [ ] Given a buyer linked to a conflict or on the client's exclusion list, when added, then a warning is shown.
- [ ] Given each buyer on the list, when added, then an owner (team member) and a rationale are required.

BUY-02. As a director, I want to export the list for client approval so that we only approach agreed parties.
- [ ] Given the long list, when I export, then an Excel with buyer, type, rationale and contact is produced, without internal notes.
- [ ] Given client feedback, when I mark buyers Approved or Excluded, then only Approved buyers can be contacted.

BUY-03. As a team member, I want a buyer-by-status grid so that I know where each party is.
- [ ] Given the grid, when I change a buyer status, then the date and user are stored and the funnel counts update.
- [ ] Given a status requires a prerequisite (IM sent requires NDA signed), when missing, then the change is blocked.
- [ ] Given bulk select, when I update 20 buyers to Teaser sent, then all get the same date.
- [ ] Given a buyer drops out, when set to Declined, then a reason is required (price, fit, timing, no response).
- [ ] Given no buyer activity for 14 days during an active phase, when the threshold passes, then the buyer owner is reminded.

BUY-04. As an analyst, I want NDA versions and markups tracked so that legal follows up.
- [ ] Given an NDA, when I log sent date, markup received, agreed and signed date with document link, then the buyer moves to NDA signed only when signed date is set.
- [ ] Given an NDA pending more than 10 days, when the threshold passes, then the buyer owner gets a reminder.
- [ ] Given a signed NDA with a standstill or non-solicit period, when entered, then its end date is stored and shown on the buyer company.

BUY-05. As a director, I want indicative and binding offers captured in a standard way so that I can compare bids.
- [ ] Given an offer, when I enter EV (EUR m), equity value, structure (cash, earn-out, vendor loan, rollover %), conditions and financing certainty, then it shows in the bid comparison table.
- [ ] Given two or more offers, when I open the comparison, then bids sort by EV with implied EV/EBITDA multiple.
- [ ] Given role Analyst, when they view offers, then values are visible (offers are not fee fields).
- [ ] Given a buyer revises its offer, when a new version is saved, then previous versions stay visible with dates.
- [ ] Given the bid deadline has passed, when an offer is entered, then it is flagged as late.

BUY-06. As a director, I want to send process letters to all active buyers so that communication is consistent.
- [ ] Given selected buyers, when I generate a letter from a template, then each buyer's contact, salutation and language are merged and the send is logged as an activity.
- [ ] Given a buyer has not signed an NDA, when the letter references the IM, then that buyer is excluded and I am told why.

BUY-07. As a partner, I want a funnel of the process so that I report progress to the client.
- [ ] Given a deal, when I open the funnel, then counts per status (approached, NDA, IM, offers, binding) and conversion % are shown and exportable to PDF.

### Epic 8: Activities, tasks, notes, email logging

ACT-01. As a user, I want to log calls, meetings and emails against contacts, companies and deals so that the history is shared.
- [ ] Given any record, when I log an activity with type, date, participants and note, then it shows on every linked record's timeline.
- [ ] Given an activity linked to a deal, when a non-staffed user views the contact, then that activity is hidden (AUTHZ-02).
- [ ] Given an activity, when edited after 7 days, then the edit is shown as edited with date.
- [ ] Given I delete an activity, when confirmed, then it is soft-deleted and restorable by an admin for 30 days.

ACT-02. As a partner, I want to mark a note private so that sensitive views stay with me.
- [ ] Given a note marked Private, when anyone else views the record, then the note is not shown, including to admins.
- [ ] (derived) Given a note marked Deal-confidential, when anyone not on the deal team views a shared contact or company record, then the note is not shown.

ACT-03. As a director, I want to assign tasks with due dates so that work is tracked.
- [ ] Given I create a task with assignee, due date and linked record, when saved, then the assignee is notified and it appears in My tasks.
- [ ] Given a task is overdue, when the day starts, then the assignee gets a daily digest.
- [ ] Given a task linked to a deal, when assigned to a non-staffed user, then assignment is blocked.
- [ ] Given a recurring task (e.g. weekly client update), when completed, then the next one is created.

ACT-04. As a user, I want to log an email by BCC or forwarding it to a CRM address so that it works with any mail program.
- [ ] Given I BCC or forward to my personal CRM logging address, when the email arrives, then it is matched to known contacts by sender and recipients and logged on their timeline.
- [ ] Given the email comes from an address not linked to a CRM user, when received, then it is rejected.
- [ ] Given no known contact matches, when received, then it goes to my Unmatched inbox to link or discard.
- [ ] Given a deal code name in the subject (e.g. [Falcon]), when logged, then it is linked to that deal only if I am on the deal team.
- [ ] Given attachments, when logged, then only names are stored, not files.

ACT-05. As a user, I want CRM meetings and key dates in my calendar so that I do not enter them twice.
- [ ] Given my profile, when I copy my private calendar feed (iCal URL), then any calendar app shows my CRM meetings, tasks and deal milestones.
- [ ] Given a deal event in the feed, when shown, then only the code name appears.
- [ ] Given I regenerate the feed URL, when saved, then the old URL stops working.

ACT-06. As a user, I want to control notifications so that I am not flooded.
- [ ] Given my settings, when I choose in-app, email or none per event type, then notifications follow that choice.
- [ ] Given a notification about a deal, when sent by email, then it uses the code name only.

### Epic 9: Reporting, fees & dashboards

REP-01. As a user, I want a home page with my deals, tasks and recent activity so that I start the day focused.
- [ ] Given I log in, when the home page loads (under 2 seconds), then I see my active deals by stage, tasks due this week and upcoming key dates.
- [ ] Given an empty state (new user), when the home page loads, then it shows guidance on how to start.

REP-02. As a partner, I want firm-wide pipeline numbers so that I steer the business.
- [ ] Given the dashboard, when opened, then I see count of mandates by stage and type, and weighted expected fees (fee x probability) by quarter.
- [ ] Given I am not staffed on a deal, when it is counted, then it appears only in aggregates, never by name or code name.

REP-03. As back-office, I want expected fee income per month so that cash planning is accurate.
- [ ] Given retainers and expected closing dates, when the forecast runs, then it shows retainers and success fees per month for 12 months, exportable to Excel.
- [ ] Given invoices sent and paid are recorded, when the forecast runs, then actual vs forecast is shown per month.

REP-04. As a partner, I want win rate, lost reasons and closed deal stats so that we improve pitching.
- [ ] Given a period, when I run the report, then I see pitches, win rate %, top lost reasons, average deal duration (mandate to closing) and average EV/EBITDA by sector.

REP-05. As a director, I want a one-click status report for the client so that weekly updates take minutes.
- [ ] Given a deal, when I generate the report, then a PDF with funnel (BUY-07), timeline vs plan and next steps is created, with no internal notes or fees.
- [ ] Given the report, when generated, then it uses the client's language and the firm's template, and is logged as an activity.

REP-06. As compliance, I want exports limited and logged so that data does not leave uncontrolled.
- [ ] Given role Analyst, when they export more than 500 contacts, then approval from a partner is required.
- [ ] Given any export, when completed, then user, time, filter and row count are in the audit log.

REP-07. (derived) As back-office, I want to record invoices sent and paid on a mandate, so that the forecast can show actuals
- [ ] (derived) Given a mandate, when back-office records an invoice with type (retainer or success fee), amount, sent date and paid date, then it is stored on the mandate and visible only to roles that see fee fields (AUTHZ-06).
- [ ] (derived) Given the invoice task created at closing (DEAL-05), when back-office records the invoice, then the task is completed.

### Epic 10: GDPR, audit & non-functional

GDPR-01. As compliance, I want each contact to carry a legal basis so that processing is lawful.
- [ ] Given a contact, when created, then legal basis (legitimate interest by default, or consent) and source are stored.
- [ ] Given marketing mailings, when a contact has opted out, then they are excluded automatically.

GDPR-02. As compliance, I want to export or erase a person's data so that we answer requests within 30 days.
- [ ] Given a request, when I run Export person, then all data and activities about them are produced as a file.
- [ ] Given an erasure, when no legal hold applies, then personal fields are anonymised and activities keep only non-personal content; if a legal hold (e.g. AML 10-year retention) applies, erasure is blocked with the reason.

GDPR-03. As compliance, I want inactive contacts flagged after 5 years so that we do not keep data forever.
- [ ] Given no interaction for 5 years (configurable), when the monthly job runs, then the owner is asked to keep or anonymise.

AUD-01. As compliance, I want every access and change logged so that we can investigate leaks.
- [ ] Given any create, update, delete, view of a deal, export, login, permission change, when it happens, then user, time, IP, record and old/new values are logged.
- [ ] Given the audit log, when anyone tries to edit or delete entries, then it is impossible (append-only), retained 10 years.
- [ ] Given compliance, when searching by user or deal, then results return in under 5 seconds.

NFR-01. As compliance, I want the platform secured to industry standards so that client data is protected.
- [ ] Given any connection, when tested, then only TLS 1.2+ is accepted and data at rest is encrypted (AES-256).
- [ ] Given hosting, when audited, then all data and backups are in EU data centres.
- [ ] Given a release, when deployed, then it passes OWASP Top 10 checks with no high or critical findings open.
- [ ] Given a yearly penetration test, when findings are high or critical, then they are fixed within 30 days.
- [ ] Given daily backups kept 35 days, when a quarterly restore test runs, then data is restored successfully and the result is logged.

NFR-02. As a user, I want the CRM fast so that I use it during calls.
- [ ] Given 50 concurrent users and 200k contacts, when load-tested, then 95% of page loads are under 2 seconds and searches under 1 second.
- [ ] Given a report on all deals, when run, then it returns in under 10 seconds.

NFR-03. As a partner, I want the CRM available when I work so that deals are not blocked.
- [ ] Given a month, when measured, then uptime is 99.5% between 8:00 and 20:00 CET.
- [ ] Given a disaster, when recovery runs, then at most 24 hours of data are lost (RPO) and service is back within 8 hours (RTO).
- [ ] Given planned maintenance, when scheduled, then users are notified 48 hours ahead and it runs outside business hours.

NFR-04. As a user, I want the CRM in my language and usable on any screen so that adoption is high.
- [ ] Given my language setting (EN, FR, NL), when I use the CRM, then all labels, emails and errors appear in that language.
- [ ] Given a screen 375 px wide, when I open any page, then no horizontal scroll is needed.
- [ ] Given an accessibility audit, when run, then WCAG 2.1 AA is met.
- [ ] Given dates and numbers, when shown, then they use Belgian formats (DD/MM/YYYY, 1.234,56 for FR/NL).

NFR-05. As IT, I want a documented API so that we can connect the data room, BI and future tools.
- [ ] Given the API, when called, then it uses OAuth 2.0 client credentials or personal API tokens issued in the CRM; no basic auth or shared keys.
- [ ] Given any API call, when it reads deals, then the same role and deal-team rules apply as in the UI (AUTHZ-01/02/06).
- [ ] Given an OpenAPI specification, when published, then it covers every endpoint with examples and stays in sync with each release.
- [ ] Given a client exceeds 100 requests per minute, when the limit is hit, then it receives 429 with a retry-after header.
- [ ] Given a breaking change, when released, then it ships as a new version and the old one runs at least 6 months.
- [ ] Given any API write, when executed, then it is recorded in the audit log like a UI change (AUD-01).

## Cross-cutting Acceptance Criteria

- [ ] (derived) Every deal-scoped read path (record, list, search, export, report, notification, calendar feed, API) applies role AND deal-team checks server-side; a non-staffed user never receives a deal's target or client name.
- [ ] (derived) Every new screen meets NFR-04 (EN/FR/NL labels, 375 px without horizontal scroll, Belgian formats) from the ticket that introduces it.
- [ ] (derived) Every create, update and delete introduced by any story is written to the audit log (AUD-01) by the same request that makes the change.
- [ ] (derived) The existing backend and frontend test suites keep passing.

## Implementation Decisions

- **Stack stays as the boilerplate ships it.** FastAPI backend with async SQLAlchemy and Alembic, PostgreSQL, Next.js frontend with shadcn/ui only, deployed to Azure in the EU through `infra/`. Each epic area is a vertical slice under the backend `modules` layer (`interfaces` → `modules` → `infrastructure`).
- **Sessions, not JWTs, for the browser.** The existing server-side cookie session (crudauth) with CSRF token is kept. AUTH-03 "access token / refresh token" is satisfied by a rolling idle timeout plus an absolute 12-hour lifetime on the server-side session: activity in any tab extends the session, and silent renewal never navigates away. "Refresh token revoked" in AUTH-04 means the server-side session record is revoked. Personal API tokens and OAuth 2.0 client credentials (NFR-05) are a separate credential type for API clients.
- **No external identity provider.** The Microsoft Entra sign-in that the boilerplate ships is removed (routes, settings, frontend button, user columns via migration). Login is email + password + TOTP only.
- **Login is email-based.** The boilerplate's `username` login field becomes email. User records gain first name, last name, title, status (Invited, Active, Deactivated), last login date/IP/device.
- **One role per user.** The existing single `role_id` on the user stays. Roles map to a permission set stored in the database and editable by admin (AUTHZ-01). Superuser flag is retired in favour of the Admin role.
- **2FA.** TOTP (RFC 6238, 6 digits, 30 s) with secrets encrypted at rest; 10 hashed one-time recovery codes; trusted-device cookie for 30 days (admin toggle). A "step-up" check re-asks the code for sensitive actions (break-glass, mass export, role change).
- **Password storage.** Argon2id (or the crudauth bcrypt default if Argon2id is not available), last 5 hashes kept for reuse checks; breach checks via the Have I Been Pwned k-anonymity range API behind a port that tests fake.
- **One access-policy module.** A single deal-access policy answers "can this principal see / edit this deal (or this field)" from role permissions, deal-team membership (with expiry), break-glass grants, compliance rules and closed-deal age. Every deal-scoped query, search, export, report, notification and feed goes through it. Hidden deals return 404, forbidden actions on visible records return 403.
- **Deal team.** Membership rows with role on the deal (lead partner, partner, director, analyst...), added-by, added-at and optional expiry. Every change writes to the wall-crossing register.
- **Opportunities and mandates share the wall.** Opportunities use the same team-membership and policy as mandates.
- **Stages.** All mandate types use the sell-side stage list in v1. Stage exit criteria are configured per stage by admin (DEAL-08) and evaluated server-side on every move; the engagement letter and KYC gate (ORI-05) is a built-in exit criterion of Preparation.
- **Optimistic concurrency.** Deal records carry a version; a stale write returns 409 with the current version (DEAL-03).
- **Conflict check.** Name normalisation strips legal forms (NV, SA, BV, SRL, BVBA, SPRL, GmbH, Ltd, ...) and accents before fuzzy matching (PostgreSQL `pg_trgm` + `unaccent`); group entities come from CO-03 / CO-04 links; scope is active mandates plus those closed or aborted in the last 24 months.
- **Search.** PostgreSQL full-text plus `pg_trgm` / `unaccent` for fuzzy matching; no external search engine in v1.
- **Background work.** A scheduled-job runner in the backend runs reminders, expiries, digests, retention and quarterly reviews. Every job is idempotent and takes "now" from an injectable clock.
- **External services behind ports.** KBO/BCE lookup, NBB filed-accounts import, breached-password check, geo-IP, outbound email (existing ACS/Resend integration) and inbound email (a webhook from the mail provider's inbound parse) each sit behind an interface with a fake used in tests.
- **Documents are links.** The CRM stores https links with labels; the engagement letter "upload" in ORI-05 is a labelled document link, not a file.
- **Generated files.** Excel exports via a server-side xlsx writer; PDFs (funnel, client report) rendered server-side from templates (ADM-07).
- **Audit log.** An append-only table (database role has INSERT and SELECT only, no UPDATE/DELETE) written in the same transaction as the change, retained 10 years, indexed by user and record.
- **Internationalisation.** EN, FR, NL message catalogues in frontend and backend (emails, errors). User language setting drives both. Belgian date and number formats.
- **Microsoft Entra removal, superuser retirement and username-to-email are the only changes to existing boilerplate behaviour.**

## Testing Decisions

Every acceptance criterion, cross-cutting ones included, is proven by a test or, for criteria that cannot be a unit of code, by a recorded check.

- **A good test** drives the system through its public interface and asserts observable behaviour (HTTP status, response body, emails captured by the fake sender, audit rows, rendered page). It does not assert internal calls or table layouts.
- **Seam 1 (primary): the backend HTTP API.** Integration tests call `/api/v1/...` with an `httpx.AsyncClient` against a real PostgreSQL, logged in as a user of the relevant role and staffing. External services are replaced by fakes at their port. Two test-only hooks: an injectable clock and a "run scheduled jobs now" trigger. Prior art: the existing backend integration tests for auth endpoints and users/roles CRUD.
- **Deal-access matrix.** One parametrised suite enumerates every deal-scoped endpoint and asserts staffed vs non-staffed vs compliance vs break-glass vs read-only outcomes (AUTHZ-02 "automated test suite" criterion). New deal-scoped endpoints must register themselves in it; a test fails if an endpoint touching deal data is missing from the matrix.
- **Seam 2: browser end-to-end (Playwright).** Only for behaviour that lives in the browser: login redirect and deep links, timeout warning and multi-tab keep-alive, Back after logout, unsaved-changes warnings, mobile read-only below 768 px, 375 px layout, Kanban drag, WCAG 2.1 AA (axe), language and Belgian formats. Prior art: the existing sign-in, sign-out and page-gate E2E specs and their account setup.
- **Frontend unit tests (Vitest)** for pure client logic only (formatters, routing guards). Prior art: the existing tests under the frontend unit folder.
- **Seam 3: operational checks.** NFR-01 (TLS, encryption, EU region via Bicep assertions, OWASP ZAP baseline in CI, pentest and restore logs), NFR-02 (k6 load test script against a seeded 200k-contact dataset), NFR-03 (uptime monitor, documented RPO/RTO drill), and the OpenAPI-in-sync check run as CI jobs, scripts or release checklist items, not unit tests.

## Out of Scope

- External identity providers / SSO (explicitly excluded by Epic 1).
- Multiple roles per user (v1 is one role per user).
- Storing document files; the CRM stores links only. Email attachments are stored by name only.
- Two-way mail or calendar sync (email logging is BCC/forward only; calendar is a read-only iCal feed).
- Native mobile apps (responsive web only).
- Billing / Stripe from the boilerplate.
- Separate stage lists for buy-side, fundraising and debt advisory (same list as sell-side in v1).

## Further Notes

- AUTH-07 "all sessions on that device" is implemented by Log out everywhere, which ends every session on every device (AUTH-04).
- AUTHZ-04: the deal partner's approval task is informational with comments; compliance decides.
- ADM-01 listed the duplicate-email criterion twice in the source; it appears once here.
- AUTH-06 relies on the travelling flag (AUTH-12), REP-03 on invoice records (REP-07), BUY-06 and REP-05 on templates (ADM-07), DEAL-02 on configurable exit criteria (DEAL-08).
