---
name: to-tickets
description: Decide whether a plan, spec, or the current conversation is too big for one implementation session, and only if it is, break it into the fewest tracer-bullet tickets, each declaring its blocking edges, published to the configured tracker. Zero tickets is a valid outcome.
disable-model-invocation: true
---

# To Tickets

Decide whether a plan, spec, or conversation needs splitting at all, and if it does, break it into the **fewest** **tickets** that work: tracer-bullet vertical slices, each declaring the tickets that **block** it.

A ticket exists for one reason only: the work is too big for one fresh implementation session to finish inside the smart zone (roughly 150k tokens of context, including the code it reads). Being asked to run this skill is not a reason to produce tickets. A spec that fits in one session is implemented directly from the spec, and that is the expected outcome for most small and medium specs.

The issue tracker and triage label vocabulary are located in `docs/agents/issue-tracker.md` and `docs/agents/triage-labels.md`.

## Process

### 1. Gather context

Work from whatever is already in the conversation context. If the user passes a reference (a spec path, an issue number or URL) as an argument, fetch it and read its full body and comments.

### 2. Explore the codebase (optional)

If you have not already explored the codebase, do so to understand the current state of the code. Ticket titles and descriptions should use the project's domain glossary vocabulary, and respect ADRs in the area you're touching.

### 3. Decide whether to split at all

Estimate whether one fresh session can implement the whole spec: the code it must read, the layers it touches, the tests it writes. Default to **no split**.

Split only when at least one of these holds:

- The spec clearly cannot be implemented in one session without leaving the smart zone.
- The user explicitly wants several people working on it in parallel.

If none holds, stop here. Tell the user the spec fits in one session, give a one-line reason, recommend implementing it directly from the spec, and publish nothing. Do not invent slices to justify running the skill.

### 4. Draft vertical slices

Break the work into the **fewest** tracer bullet tickets that each fit in one session. Prefer two big tickets over five small ones.

<vertical-slice-rules>

- Each slice cuts a narrow but COMPLETE path through every layer (schema, API, UI, tests): vertical, NOT a horizontal slice of one layer
- A completed slice is demoable or verifiable on its own
- Each slice is as large as fits in a single fresh context window, not as small as possible
- Tests, docs, config, and cleanup belong inside the slice that needs them, never in their own ticket
- Each ticket must justify its existence: if merging it into a neighbour still fits one session, merge it

</vertical-slice-rules>

Give each ticket its **blocking edges**: the other tickets that must complete before it can start. A ticket with no blockers can start immediately.

Give each ticket the user stories it **covers**, by their spec number (plus "cross-cutting" when it carries cross-cutting criteria), and copy their acceptance criteria **verbatim** from the spec, `(derived)` markers included. A cross-cutting criterion goes to the ticket that delivers the behaviour it binds; when it binds several, to the latest of them in dependency order. Drafting is done when every acceptance criterion in the spec lands in exactly one ticket: none missing, none duplicated. When the source has no spec, write the acceptance criteria yourself.

### 5. Quiz the user

Present the proposed breakdown as a numbered list. For each ticket, show:

- **Title**: short descriptive name
- **Blocked by**: which other tickets (if any) must complete first
- **Covers**: the user stories it covers, by spec number
- **What it delivers**: the end-to-end behaviour this ticket makes work

Ask the user:

- Does this need splitting at all, or should the spec be implemented directly?
- Does the granularity feel right? (too coarse / too fine)
- Are the blocking edges correct: does each ticket only depend on tickets that genuinely gate it?
- Should any tickets be merged?

Iterate until the user approves the breakdown.

### 6. Publish the tickets to the configured tracker

Publish the approved tickets. **How** depends on the tracker `docs/agents/issue-tracker.md` describes; the tickets are the same either way, only the shape of the blocking edges changes:

- **Local files** → write one file per ticket under `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01` in dependency order (blockers first). Each file's "Blocked by" lists the numbers/titles it depends on. Use the per-ticket file template below: one ticket per file, never a single combined file.
- **A real issue tracker (GitHub, Linear, …)** → publish one issue per ticket in dependency order (blockers first) so each ticket's blocking edges can reference real identifiers. Use the platform's native blocking / sub-issue relationship where it has one; otherwise set each ticket's "Blocked by" to the blocking issues. Apply the `ready-for-agent` triage label unless instructed otherwise; the tickets are agent-grabbable by construction.

Work the **frontier**: any ticket whose blockers are all done. For a purely linear chain that means top to bottom.

Do NOT close or modify any parent issue.

<local-ticket-template>

# <NN>: <Ticket title>

**What to build:** the end-to-end behaviour this ticket makes work, from the user's perspective, not a layer-by-layer implementation list.

**Blocked by:** the numbers/titles of the tickets that gate this one, or "None (can start immediately)".

**Covers:** the spec's user stories, by number.

**Status:** ready-for-agent

- [ ] Acceptance criterion 1, verbatim from the spec
- [ ] Acceptance criterion 2, verbatim from the spec

</local-ticket-template>

<issue-template>

## Parent

A reference to the parent issue on the tracker (if the source was an existing issue, otherwise omit this section).

## What to build

The end-to-end behaviour this ticket makes work, from the user's perspective, not layer-by-layer implementation.

## User stories covered

The spec's user stories this ticket covers, by number.

## Acceptance criteria

- [ ] Criterion 1, verbatim from the spec
- [ ] Criterion 2, verbatim from the spec

## Blocked by

- A reference to each blocking ticket, or "None (can start immediately)".

</issue-template>

In either form, avoid specific file paths or code snippets: they go stale fast. Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it and note briefly that it came from a prototype. Trim to the decision-rich parts, not a working demo, just the important bits.
