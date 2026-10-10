# Shared rules

The single source of truth for every `to-estimate` agent and for the merge.

## Categories

Every feature lands in exactly one category.

- **Working** (app): reachable from the UI, and it does what it claims when you exercise it end to end in the
  running copy.
- **Requested** (list): a clear feature from the list. It takes the place of working.
- **Dead** (app): vibe-coded, but never came true. That covers:
  - no UI entry point (no UI means nobody uses it);
  - a placeholder or "coming soon" tile;
  - hardcoded mock content;
  - a control that errors or does nothing;
  - a dependency on an integration that was never set up.

  Each dead feature carries its question for the client: do you want it, and what should it do?
- **Deep dive** (both): a feature whose intent neither the code nor the list reveals. It needs a session with the
  client before it can be sized, and it carries the questions for that session.
- **Recommended** (both): absent from the input, needed for production (security, privacy, operations, data), and
  not already in the boilerplate.

Two kinds of work fall outside the categories and still cost tickets:
- **Day-one data:** moving existing data and users into the new app, when they exist.
- **Project work:** setup, environments and cutover. These are never roadmap lines.

## The used? flag (app)

Give every working feature a used? verdict, with its evidence. These signals show whether a feature was used:
- **Row counts.** A table with 0 rows behind a working screen means the feature is unused.
- **Id formats.** Ids the app generates versus ids that came from an import or an earlier app.
- **Timestamps.** Times the app wrote versus bare import dates.
- **Seed equality.** A table identical to a seed or import file.

Working-but-unused features still count, marked **(unused)**. The client confirms them, like the dead ones.

## Sizing rule

Tickets are units. The quote multiplies their count by an average, so every ticket is about the same amount of work.
- **What a ticket is:** one thin vertical **slice** through every layer: model and migration, service and routes
  with integration tests including the auth matrix, one screen or screen section with its loading, error and empty
  states, and unit tests. It can be demoed in one sentence and finished in one agent session, under about 150K
  tokens.
- **Target size:**
  - Features: one resource's list with filters and detail, its create/edit/delete, one external integration, one
    dashboard panel group, or one import or export.
  - Platform work: one Bicep module with its parameters and wiring, or one workflow with its jobs.

  Merge smaller pieces into a neighbour, and split bigger ones.
- **Naming:** name tickets as outcomes ("Consultant can log a call, meeting or email on a prospect"). Group them under
  **roadmap lines**: outcomes a non-technical person understands in one spoken sentence.
- **The boilerplate:** its existing capabilities count only as value, in the boilerplate report. What it lacks, or
  holds only as a placeholder, is build work.

## Evidence and personal data

- Every claim carries its evidence: a file:line, a route, a row count, or what happened when you exercised it.
- People appear by role ("a consultant", "an applicant"). Names, emails, phone numbers and document contents stay out
  of every report.
- What you could not verify gets its own section, with the reason.
