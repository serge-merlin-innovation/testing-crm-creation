---
name: retro-auto
description: "Unattended retrospective written to postmortem/ at the git root. Use as the last step before your final response in any session that implemented, tested, verified or otherwise touched code, when the repo has a postmortem/ folder."
---

You are running an unattended **retrospective** on your own session, as its last step before your final response. Nobody answers questions here: you decide, write the report, and continue. You are suggesting improvements to the coding agent's **environment** to improve future runs. The run is **report-only**: the postmortem file is the one file you write.

## Steps

1. Check the gates. Find the git root (`git rev-parse --show-toplevel`, falling back to the working directory). Stop the skill here, writing nothing, when any of these holds:
   - `postmortem/` is missing at the git root.
   - The session edited no files and made fewer than 5 tool calls.

2. Review the current session only: your own transcript, the files you touched, the checks you ran and their results. Keep it to what is already in your context plus cheap lookups (the repo's check scripts, its CI workflow, its steering files).

3. Look for candidates for improvement in the categories below. Keep the top **5 findings** at most, ranked by severity. A clean session with zero findings is a valid result.

4. Write the report to `postmortem/YYYY-MM-DD-HHMM-<role>-<task-slug>.md` at the git root, using the template below. `<role>` is `worker` when you were spawned or assigned by a coordinator, `main` otherwise. `<task-slug>` is a short kebab-case name for the task. Append `-2`, `-3`, ... when the name already exists. The step is done when the file exists and every finding has evidence and a target file.

5. Continue to your final response. End it with one line: `Postmortem: postmortem/<file>.md`.

## Categories

- **Navigation**: how easy was it for the agent to find the right files? Are there hidden dependencies between files? Would a **navigation pointer** make it easier? _Use when_ the session took a long time to find a piece of information.
- **Automated checks**: are there automated checks that could catch errors the agent made? Linting, typing, tests, filesystem linters? Read the repo's own check command first (its `package.json`/build-tool `lint`/`check` scripts, its CI workflow), so a check that already exists but sits unwired or silently broken is the finding, not a reinvention. A repo with no **guardrail** (no pre-commit hook and no CI job running its lint/typecheck/test command) is itself a finding: an un-linted repo is a standing missed opportunity, not a neutral default. _Use when_ the agent made a mistake an automated check could have caught, or the repo has no guardrail at all.
- **Coding standards**: should the **reviewer agent** be given a new rule to enforce? Should an existing rule be removed or clarified? Classify the violation first: a **mechanical** one (a fixed syntactic pattern, a banned API, an import shape, a file-location rule) gets a deterministic check, full stop: a custom rule in the repo's own linter, a new pre-commit hook, or a new CI job, whichever the repo's language and existing guardrail make cheapest. Default to building the check over writing the rule. Reserve `CONSTITUTION.md` for genuine **judgement calls** (cross-file consistency, "matches the surrounding style," anything no guardrail could ever substitute for). _Use when_ the reviewer agent failed to catch a mistake.
- **Global AGENTS.md**: are there any steering instructions that should be moved to coding standards (or automated checks) instead? _Use when_ the AGENTS.md file is particularly large, in the repo OR the user's global scope.
- **Tool economy**: did the agent make expensive tool calls that could be streamlined? Is there any custom tooling (CLIs, MCPs) that is particularly token-inefficient? _Use when_ the agent made an expensive tool call.
- **No-ops**: look for instructions in steering files that don't modify the agent's behavior. _Use when_ the steering files are large and unwieldy.
- **Information access**: look for opportunities to increase the agent's access to information. Teeing dev server logs, readonly access to third-party services. _Use when_ a crucial piece of information was not available to the agent.

## Template

```markdown
# Postmortem: <task in a few words>

- Date: YYYY-MM-DD HH:MM
- Role: main | worker
- Task: <one line>
- Model: <model, if known>

## Summary

<One paragraph: what the session set out to do, what it did, how it ended.>

## Findings

### 1. <title>

- Category: <one of the categories>
- Severity: high | medium | low
- Evidence: <what happened in the session, concretely>
- Suggested change: <the fix>
- Target: <file or tool the change lands in>

## Worker postmortems

<main role only: links to the worker postmortem files written during this run, or "none".>
```

## Reference

### Implementation vs Review

All work goes through two stages: implementation and review. The implementation agent has the most **context pressure**. They are responsible for exploration, writing code, and debugging failures.

The review agent has the least context pressure: it receives a diff, so no exploration needed. It often does not need to write code or debug.

This means that the review agent should be responsible for imposing coding standards, not the implementation agent.

### Files

Suggested changes usually target one of these:

- `CLAUDE.md`/`AGENTS.md`: pushed to the context window of any agent working in the repo. Use them incredibly sparingly, usually only for **navigation pointers** to other files.
- `CONSTITUTION.md`: the standing rules. Add **navigation pointers** to docs folders if it gets more than 1,000 lines long.
- Docs: reference files, pointed to by other files. Look for existing docs before suggesting new ones.
- Skills: for docs (since their description goes into the agent's context window), or for user-invoked commands.
