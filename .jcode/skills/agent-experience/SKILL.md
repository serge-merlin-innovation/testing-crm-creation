---
name: agent-experience
description: "Turn a finished multi-agent run's check failures, decisions and postmortems into a recommendations-only report: what to change, where, and why."
disable-model-invocation: true
---

You are writing one report, `docs/research/agent-experience-improvements.md`, from one finished **run** (a coordinator and the subagents it spawned). It lists only the biggest opportunities to save time and tokens, to give the human more control over agent decisions, and to make the process smoother. Each one is a recommendation, where it goes, and a short reason. It holds no analysis sections, raw counts tables, method notes or narrative.

## Inputs

- `check-failures.log` at the repo root: every failing check, TDD reds included.
- The run's decision report (`docs/DECISION-REPORT.md`, or `docs/decisions/<spec>.md`): the decisions agents took on the user's behalf.
- `postmortem/*.md` written by the run's coordinator and workers.

Leave out quality assessments: ISO 25010 or any other standards-based evaluation, audits, and load or security reviews, even when they sit in `postmortem/` or `docs/research/`. Use none of their findings, counts or recommendations.

## Steps

1. **Read every input in full.** Bucket the log lines by error text, and tell planned TDD reds (a single red on a new test, then green) apart from waste (repeats, environment, fixtures, guards, drift). Group the decisions by who should have taken them: the spec, an ADR, the constitution, or really the agent at run time. Group the postmortem findings that repeat across files. Done when every log line, decision row and run postmortem has been read, and you have a count for each bucket.
2. **Choose the recommendations.** Keep a recommendation when it removes a recurring cost, which means at least 10 log lines, 3 postmortems or 3 decisions, or one decision that a reviewer had to revert. Merge recommendations that share one fix. Done when each remaining recommendation names one concrete change.
3. **Find where each change goes.** Give an existing file path, or a new path that matches the repo's conventions: `docs/agents/CONSTITUTION.md`, `.jcode/skills/<name>/SKILL.md`, `docs/adr/`, `CONTEXT.md`, the app code and config, CI, hooks. Check each path with `ls` or `grep`. Done when every path in the report exists, or is marked as new.
4. **Write the report** in the format below, and commit it.

## Format

```markdown
# Agent experience: recommendations from <run name>

One sentence: the inputs (log lines, decision count, postmortem count), the run date and the PR. Each table is ordered by impact, largest first.

## Time and tokens
| Recommendation | Where | Why |
|---|---|---|

## Controllability
| Recommendation | Where | Why |
|---|---|---|

## Processing
| Recommendation | Where | Why |
|---|---|---|
```

- **Time and tokens** covers wasted reruns, long or flaky suites, environment setup, and rules the agents learn by failing.
- **Controllability** covers decisions that a human should take up front: spec gaps, conventions, rules, and the format of the decision log.
- **Processing** covers ticket slicing, coordination, merging, knowledge left outside the repo, and the logging itself.
- **Recommendation** is the change, stated as an imperative.
- **Where** is the file path or paths, in backticks.
- **Why** is one or two sentences: the cost observed in this run, with its evidence count (log lines, postmortems or decision rows).

Done when every row has all three cells, and nothing in the report draws on a quality assessment.
