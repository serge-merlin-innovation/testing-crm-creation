---
name: to-spec
description: "Turn the current conversation into a spec and publish it to the project issue tracker: no interview, just synthesis of what you've already discussed."
disable-model-invocation: true
---

This skill takes the current conversation context and codebase understanding and produces a spec. Synthesize what you already know: the only time you ask the user anything is the single confirmation in step 3.

The issue tracker and triage label vocabulary should have been provided to you. If not, read `docs/agents/issue-tracker.md` and `docs/agents/triage-labels.md`.

## Process

1. Explore the repo to understand the current state of the codebase, if you haven't already. Use the project's domain glossary vocabulary throughout the spec, and respect any ADRs in the area you're touching.

2. Gather the user stories and their acceptance criteria. They come from two sources:

   - **User-supplied**: stories, criteria, or requirement sentences the user wrote, in the conversation or in the optional argument (a file path or an issue reference: read its full body and comments). Copy their wording **verbatim**, even where your own style would differ: only the numbering and checkbox layout follow the template.
   - **Derived**: every story or criterion whose wording is yours, including one that restates, splits, or widens something the user said. Mark each one `(derived)` so the user sees what they did not write.

   This step is done when every behaviour the feature adds has a story, every story carries at least one acceptance criterion, and every story without a testable outcome has been merged into another or dropped. A story where neither the user nor the conversation gives you a criterion is a **gap**: keep it, and flag it for step 3.

3. Sketch out the seams at which you're going to test the feature. Existing seams should be preferred to new ones. Use the highest seam possible. If new seams are needed, propose them at the highest point you can. The fewer seams across the codebase, the better - the ideal number is one.

   Show the user, in one message: the seams, the user stories with their acceptance criteria, and the flagged gaps. Offer a derived criterion for each gap. The user approves, edits, or fills gaps in that single pass: approval accepts your derived criteria, and anything they write enters the spec verbatim.

4. Write the spec using the template below, then publish it to the project issue tracker. Apply the `ready-for-agent` triage label - no need for additional triage.

   User Stories and Testing Decisions are always written. Every other section is written only from what the conversation supplies: when it supplies nothing for a section, omit its heading.

<spec-template>

## Problem Statement

The problem that the user is facing, from the user's perspective.

## Solution

The solution to the problem, from the user's perspective.

## User Stories

A numbered list of user stories, each followed directly by its acceptance criteria as a checkbox list. Number the stories once and keep the numbers stable: tickets reference them. Each user story should be in the format of:

1. As an <actor>, I want a <feature>, so that <benefit>
   - [ ] <acceptance criterion>

<user-story-example>
1. As a mobile bank customer, I want to see balance on my accounts, so that I can make better informed decisions about my spending
   - [ ] Each account on the overview shows its current balance in the account's currency
   - [ ] Given a pending transaction, when I open the overview, then the balance shows both available and pending amounts
2. (derived) As a mobile bank customer, I want to see when my balance was last updated, so that I know whether to trust it
   - [ ] (derived) The overview shows the time of the last balance refresh
</user-story-example>

Write each criterion as one plain, independently verifiable statement, or as Given/When/Then where a precondition and trigger make it clearer.

## Cross-cutting Acceptance Criteria

Acceptance criteria that bind the whole feature rather than one story (performance, accessibility, no regression in existing behaviour), as a checkbox list in the same format.

## Implementation Decisions

A list of implementation decisions that were made. This can include:

- The modules that will be built/modified
- The interfaces of those modules that will be modified
- Technical clarifications from the developer
- Architectural decisions
- Schema changes
- API contracts
- Specific interactions

Do NOT include specific file paths or code snippets. They may end up being outdated very quickly.

Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it within the relevant decision and note briefly that it came from a prototype. Trim to the decision-rich parts, not a working demo, just the important bits.

## Testing Decisions

Every acceptance criterion, cross-cutting ones included, is proven by a test. When the conversation agreed no other testing decisions, the acceptance criteria are the testing decisions.

A list of testing decisions that were made. Include:

- A description of what makes a good test (only test external behavior, not implementation details)
- Which modules will be tested
- Prior art for the tests (i.e. similar types of tests in the codebase)

## Out of Scope

A description of the things that are out of scope for this spec.

## Further Notes

Any further notes about the feature.

</spec-template>
