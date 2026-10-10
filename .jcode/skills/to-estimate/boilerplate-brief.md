# Boilerplate value brief

Fill in the placeholders and send this as one agent's prompt.

<boilerplate-brief>

## Context
Merlin quotes two numbers:
- **Build tickets** set the schedule.
- **Value tickets** set the price. They are the build tickets plus the boilerplate capabilities the project uses,
  counted as if built from scratch.

Your job is to count the boilerplate at <boilerplate path>, commit <sha>, as tickets, and to flag which ones <client>
needs. Read .claude/skills/to-estimate/shared-rules.md first.

<If a cache exists: <path> counts this same commit. Reuse its capability table and gap list, and redo only the
"needed by" column.>

## Scope
- **Count everything that ships the app or keeps it correct:** the backend platform, the frontend platform, infra,
  CI/CD, quality gates (hooks, lint, the test harnesses), the agents pipeline, and setup scripts. Count each as if
  written from zero. Third-party libraries count as integrated, not rebuilt.
- **Leave out the factory's own tooling** (`.claude/skills`, `docs/agents`), and list it as not counted.
- **Count only what exists today.** A capability switched off in the deployed configuration counts as built.
- **Flag each capability for <client>:** needed, not needed, or needed only if a named dead feature is chosen.

## Output
Write <scratchpad>/inventory/boilerplate-from-scratch.md with these sections:
1. **Summary:** the total, the subtotal <client> needs, and the split by area.
2. **Capability inventory:** #, capability, evidence with size signals (lines, tests, routes), tickets, needed?
3. **Tickets by area,** named as outcomes.
4. **Gaps,** each with its file:line. The merge uses this list to correct any "the boilerplate covers it" claim.
   List every capability that:
   - exists only as a placeholder;
   - is switched off in the deployed configuration;
   - is not wired end to end, such as infra that no app code can reach, or a job with no worker.
5. **Not counted,** and why.
6. **What you could not verify,** and why.

Then return a summary of at most 15 lines: both totals, the split by area, and the three biggest cost drivers.

</boilerplate-brief>
