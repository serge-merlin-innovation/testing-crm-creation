# Area brief

Fill in the placeholders and send one copy per area as that agent's prompt. Keep the section for the branch you are
on and delete the other one.

<area-brief>

## Context
Merlin is estimating a from-scratch build of <client>'s <app | feature list> on Merlin's delivery boilerplate. Your
job is to inventory ONE area and propose its tickets. Read .claude/skills/to-estimate/shared-rules.md first. It defines the
categories, the used? flag and the sizing rule you apply.

## Your area: <area>
<screens, routes, code ranges and tables | the list items in this area, verbatim>

The other agents own <other areas>. When you touch one of their features, mark it "owned by <area>".

## App branch: the app
- **Original source,** read-only: <app path>
- **Disposable running copy** of the same code: <copy path>, served at <url>. Its data is a copy of client data, and
  changing it is fine.
- **Row counts:** <table rows>
- **The client's keys are absent from the copy,** so anything that needs them fails here. Leave them absent, and
  reach no external service. The client's own configuration holds real values for: <keys>.

### Browser rules (the browser and the server are shared)
- **Your own tab.** Create your own tab and pass its id to every browser call. The browser is signed in as the test
  admin, and all tabs share that session.
- **Stay signed in as the admin in the browser.** Test sign-out, password changes, role changes and other roles with
  curl, using a ZZTEST user of your own and your own cookie jar. If curl needs the admin's credentials, they are in
  <credentials file>. Never print the password.
- **Your records only.** Start the name of every record you create with ZZTEST, and delete only records you created.
- **External services.** For an endpoint that reaches an external service, read its code, or block the request in
  your own tab.
- **Dialogs and file pickers.** Stub native dialogs, or set files through page JavaScript in your own tab, and say so
  in section 8.
- **If the server stops,** restart it with launch configuration <name>, note what triggered the stop, and redo your
  cleanup.
- **Security probes** use harmless payloads only, such as a `<b>` tag or a file written inside the copy's own data
  folder. Remove them afterwards.

## List branch: the list
For each item, write down:
- the outcome it serves;
- the assumptions you had to make;
- the client questions that would remove those assumptions.

An item you can't size without the client is a deep dive.

## Output
Write <scratchpad>/inventory/<area-slug>.md with these sections:
1. Features: #, feature, category, used? (app) or clear/unclear (list), evidence
2. Business rules: statuses and transitions, validation, formulas, and who may do what (for a list: the assumptions)
3. Bugs and oddities (app)
4. Dead features and deep dives, each with its client question
5. Gaps noticed: production needs in your area
6. Roadmap lines, with ticket names
7. Tickets for dead features if the client says yes, and what folds into existing tickets
8. What you could not verify, and why

Then return a summary of at most 15 lines: counts per category, the tickets you proposed, and your three most
surprising findings.

</area-brief>
