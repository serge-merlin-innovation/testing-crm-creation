# M&A CRM ticket map

How the GitHub issues for the M&A CRM spec ([`docs/specs/ma-crm.md`](specs/ma-crm.md)) depend on each other. An arrow `A --> B` means A blocks B: B can start only once A is closed. GitHub holds the authoritative edges as native "blocked by" links on each issue.

```mermaid
flowchart TD
    classDef auth fill:#dbeafe,stroke:#1d4ed8,color:#1e3a8a
    classDef data fill:#dcfce7,stroke:#15803d,color:#14532d
    classDef deal fill:#fef3c7,stroke:#b45309,color:#78350f
    classDef wall fill:#fee2e2,stroke:#b91c1c,color:#7f1d1d
    classDef report fill:#ede9fe,stroke:#6d28d9,color:#4c1d95
    classDef final fill:#e5e7eb,stroke:#374151,color:#111827

    T1["#1 Foundation: email login, roles,<br/>permission matrix, audit log"]
    T2["#2 Two-factor login, lockout,<br/>suspicious-login alerts"]
    T3["#3 Session timeout, logout<br/>everywhere, mobile access"]
    T4["#4 Invitations, password policy,<br/>password reset"]
    T5["#5 Companies, contacts,<br/>reference data"]
    T6["#6 Mandates, deal team,<br/>Chinese wall"]
    T7["#7 Activities, notes, tasks,<br/>notifications"]
    T8["#8 Pipeline board, stage gates,<br/>milestones, closing"]
    T9["#9 Conflict check,<br/>KYC / engagement letter gate"]
    T10["#10 Fees, field restrictions,<br/>invoices"]
    T11["#11 Wall-crossing, delegation,<br/>break-glass, access review"]
    T12["#12 Origination: opportunities,<br/>pitches, win/lose"]
    T13["#13 Investor profiles, buyer list,<br/>status grid, NDAs"]
    T14["#14 Offers, templates, process<br/>letters, funnel, client report"]
    T15["#15 Email logging,<br/>calendar feed"]
    T16["#16 Search, relationship holders,<br/>merge, Excel import"]
    T17["#17 Home page, dashboards,<br/>fee forecast, win/loss"]
    T18["#18 Public API,<br/>tokens and OAuth"]
    T19["#19 Offboarding, GDPR rights,<br/>export controls"]
    T20["#20 Production readiness:<br/>i18n, a11y, security, perf"]

    T1 --> T2
    T2 --> T3
    T2 --> T4
    T1 --> T5
    T1 --> T6
    T5 --> T6
    T6 --> T7
    T6 --> T8
    T7 --> T8
    T8 --> T9
    T7 --> T10
    T8 --> T10
    T7 --> T11
    T9 --> T11
    T9 --> T12
    T10 --> T12
    T8 --> T13
    T9 --> T13
    T10 --> T14
    T13 --> T14
    T7 --> T15
    T8 --> T15
    T7 --> T16
    T10 --> T17
    T12 --> T17
    T6 --> T18
    T4 --> T19
    T7 --> T19
    T18 --> T19
    T3 --> T20
    T11 --> T20
    T14 --> T20
    T15 --> T20
    T16 --> T20
    T17 --> T20
    T19 --> T20

    class T1,T2,T3,T4 auth
    class T5,T16 data
    class T6,T7,T8,T10,T12,T13,T14,T15 deal
    class T9,T11,T18,T19 wall
    class T17 report
    class T20 final
```

Colours: blue is authentication, green is companies and contacts, amber is deal and buyer work, red is access control and compliance, purple is reporting, grey is the final production-readiness pass.

## Critical path

`#1 → #5 → #6 → #7 → #8 → #9 → #12 → #17 → #20` is the longest chain (9 tickets). Everything else can run alongside it once its blockers close.

## Parallel waves

Tickets in the same wave have no edge between them and can be worked at the same time.

| Wave | Tickets |
|---|---|
| 1 | #1 |
| 2 | #2, #5 |
| 3 | #3, #4, #6 |
| 4 | #7, #18 |
| 5 | #8, #16, #19 |
| 6 | #9, #10, #15 |
| 7 | #11, #12, #13 |
| 8 | #14, #17 |
| 9 | #20 |
