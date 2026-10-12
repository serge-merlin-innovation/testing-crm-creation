# Agent run: token usage vs output quality

The {{TITLE}} run of {{RUN_DATE}}. Coordinator `{{COORDINATOR}}` and its {{N_CHILDREN}} subagent sessions. Read-only analysis, {{TODAY}}.

Interactive views, both in this folder and self-contained (open in a browser, offline). Hover a card to highlight its links, click it for its token figures, failed criteria and postmortem link, and toggle link types in the legend.

- [agent-run-map.html](agent-run-map.html): one column per agent type (coordinator, tickets, mergers, reviews, fixers), each column centred on a shared mid-line, with right-angled links between columns.
- [agent-run-map-timeline.html](agent-run-map-timeline.html): time runs left to right, and each session sits one step after the sessions it waited on, in a lane for its role.

## Question

Did the implementation agents that used more tokens, or ran with a bigger context, ship work that failed more of its acceptance criteria?

## Answer

<!-- WRITE: one bold sentence answering the question, from the table below. -->

<!-- BEGIN:correlation -->
<!-- END:correlation -->

<!-- WRITE: the reading (what the Pearson vs Spearman values say, the outlier named in the "without" rows), then caveats:
small n, ticket size and type, who failed is not always who was asked (count the ambiguous rows), the reviews differ,
failure types, per-criterion rate vs mean of per-agent rates. End with a one-line conclusion. -->

## Method

<!-- BEGIN:method -->
<!-- END:method -->

## How the "failed first time" percentage is computed

For each implementation agent:

> **failed %** = criteria of its ticket that a later review found unmet ÷ all criteria of its ticket

1. **Denominator: the ticket's criteria.** Each ticket is a GitHub issue that lists the spec stories it covers. Every acceptance criterion (each `- [ ]` line) under those stories is counted.
2. **Numerator: criteria a later review found unmet.** A criterion counts once as failed, even when several sources flag it, if any review source says the ticket's work did not meet it: a code-review blocker or should-fix finding mapped to the criterion it breaks, a traceability row marked WEAK, MISSING or CONTRADICTS, or a decision-report row marked superseded by a review (a silent narrowing of the spec).
3. **Attribution: which agent a failure counts against.**
   - It counts against the ticket whose issue lists that criterion. The git history confirms which agent's commits implemented it.
   - A finding on one ticket's code that breaks another ticket's criterion is listed as a *cross-ticket finding* on the code's agent and left out of its %.
   - Findings with no matching criterion are left out, and so are findings about code that had not merged when the review ran.
   - Crashed or resumed attempts are not scored. The agent that actually built the ticket carries it.

<!-- WRITE: a worked example (the highest failed % ticket), then "How to read the number": shared failures and the ambiguous count, the strict bar (WEAK fails a working feature), non-uniform reviews, and that the attribution is a judged estimate. -->

## Agent map

Every session of the run and how the sessions relate. Each card shows the session name and ticket, its role, total tokens, peak context and, for implementation agents, the share of acceptance criteria that failed the first time.

**Arrows**

| Arrow | Colour | Meaning |
|---|---|---|
| `A ──▶ B` | grey | ticket B was blocked by ticket A (the issue's "Blocked by" list) |
| `A ┄▶ B` "merged by" | blue | B merged A's branch into `{{BRANCH}}` |
| `A ━▶ B` "findings" | red | reviewer A's findings were fixed by B, or B reviewed or verified a commit A made |
| `A ┄▶ B` "resumed / respawned / split" | purple | B took over A's unfinished job |
| `A ┄▶ B` "built #N …" | yellow | A was asked to build work that B's ticket left out |

**Cards**

- Colour: green under 15% failed, yellow 15-29%, red 30% or more, grey for agents that are not scored. A dashed grey card crashed or was killed.
- A thick orange border marks a peak context over {{HOT_K}}.
- "📄 postmortem" means the session wrote one. Click the card to open it (works in VS Code and in other Mermaid viewers that allow links). GitHub disables diagram links, so use the index below the diagram there.

<!-- BEGIN:mermaid -->
<!-- END:mermaid -->

### Postmortem index

<!-- BEGIN:postmortems -->
<!-- END:postmortems -->

### Where each link comes from

<!-- BEGIN:edges -->
<!-- END:edges -->

## Sessions

<!-- BEGIN:sessions -->
<!-- END:sessions -->

## Failed criteria per agent

<!-- BEGIN:failed -->
<!-- END:failed -->

## Limits

<!-- WRITE: n and the dominating point, the two review methods, judged attribution (ambiguous count), and anything the token figures include besides feature work. -->
