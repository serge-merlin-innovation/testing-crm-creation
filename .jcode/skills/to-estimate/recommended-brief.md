# Recommended-features brief

Fill in the placeholders and send this as one agent's prompt.

<recommended-brief>

## Context
Merlin is estimating a from-scratch build of <client>'s <app | feature list> on Merlin's delivery boilerplate. Other
agents inventory the features. You own the **recommended** category: what basic production readiness needs
(security, privacy, operations, data) that neither the <app | list> nor the boilerplate provides. Read
.claude/skills/to-estimate/shared-rules.md first.

## Sources (read-only)
- <app path. Its .env stays closed; its keys are: <keys> | the feature list>
- **The data:** <data store path | none>. Read the schemas and counts only.
- **The boilerplate** at <boilerplate path>, commit <sha>: `apps/backend`, `apps/frontend`, `infra/`, the
  constitution, and the methodology (it says where delivery stops).
- **The running copy** at <url> allows harmless read-only probes, but read the code first.

## Produce
1. **Security and privacy findings in the app** (app branch), each with its file:line, 3–8 quoted lines, and the
   consequence.
2. **Recommended features.** For each one, give:
   - the outcome;
   - why it's needed: the evidence, or the legal or operational reason;
   - whether the boilerplate covers it, citing its code;
   - the tickets it needs.

   Check every one of these:
   - permissions per role, enforced on the backend;
   - privacy for the personal data involved: retention, erasure, export, legal basis, and processor agreements with
     any AI service or third party;
   - an audit trail;
   - file storage, and malware scanning of uploads;
   - backups, with a rehearsed restore;
   - monitoring and alerts;
   - a production environment, and go-live;
   - moving existing users onto the new sign-in;
   - email delivery, if anything sends mail;
   - one interface language;
   - accessibility.
3. **Project work** that costs tickets but isn't a feature:
   - setup;
   - data migration, per table, with row counts and the data-quality problems the data shows;
   - cutover;
   - anything else needed before real users arrive.
4. **Risks to the estimate** that depend on the client or third parties.
5. **What you could not verify,** and why.

Write <scratchpad>/inventory/recommended.md, then return a summary of at most 15 lines.

</recommended-brief>
