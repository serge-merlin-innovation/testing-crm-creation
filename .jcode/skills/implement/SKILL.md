---
name: implement
description: "Implement a spec's tickets on one branch, one subagent per ticket, and open one pull request for the spec, stacked on a blocker's open pull request when there is one."
disable-model-invocation: true
---

Implement the spec the user names: every ticket linked to it as a sub-issue, on a single **integration branch**, in one pull request.

If the spec has no sub-issues, it was judged small enough for one session: treat the spec itself as the single ticket and implement it the same way. If the user names a single ticket instead of a spec, treat that ticket as the spec the same way.

## Choosing the base branch

The **base branch** is where the integration branch starts and what its pull request targets. Find it from the issues blocking the named spec or ticket, outside its own task graph:

- Every blocker is closed, or has no open pull request: the base is the default branch.
- Exactly one blocker has an open pull request: the base is that pull request's head branch. This **stacks** the new pull request on it, so the work builds on code that is not merged yet.
- Several blockers have open pull requests: stop and ask the user. Merge order decides the base, and a branch can't stack on two parents.

When stacked, say so at the top of the pull request body: `Stacked on #<parent PR>. Merge that first.` GitHub only honours closing keywords on pull requests that target the default branch, so the closing keywords take effect once the stack lands on it.

The parent is squash-merged, so its commits never reach the default branch as they are. When the parent merges, move the stacked branch onto the default branch: `git rebase --onto origin/<default> <old parent tip> <branch>`, force-push with `--force-with-lease`, and retarget the pull request with `gh pr edit <n> --base <default>`. If the parent gains commits before it merges, rebase the stacked branch onto the new parent tip the same way.

The tickets are not a list of steps. They are a **task graph** with blocking relationships between them. This means there is always a **frontier** of tickets which are ready to be grabbed: every ticket whose blockers are all committed.

Communication to and from subagents should be sparse. Communicate primarily through **context pointers**: to the spec, tickets, research notes, and previous commits. Don't duplicate information already available via pointers.

**Implementer subagents** should be run in the background where possible for maximum concurrency.

## Steps

1. Read the spec and its tickets to understand the task graph and find the first frontier.

2. (optional) Use an **exploration subagent** to conduct any exploration required by the tickets: relevant codebase files or external documentation. It saves its markdown notes in a directory outside the repo, accessible by all future subagents. This lets **implementer subagents** focus on implementation rather than exploration.

3. Create the integration branch from the **base branch**. Open the draft pull request against the base branch after the first ticket is committed to it (a branch with no commits ahead of its base can't open one), marked as closing the spec and its tickets.

4. Hand each frontier ticket to its own **implementer subagent**. Each implementer subagent:
   - confirms its working copy is based on the integration branch before starting, and resets onto it if not;
   - uses /tdd where possible, at pre-agreed seams;
   - proves every acceptance criterion in the ticket with a passing test;
   - runs typechecking and single test files regularly;
   - commits its work;
   - in a worktree, merges the integration branch tip into its own branch before reporting done;
   - reports what it built and the test that proves each acceptance criterion.

5. Run frontier tickets in parallel when they touch separate parts of the code, such as one backend-only and one frontend-only ticket. Give each parallel subagent its own worktree (`isolation: "worktree"`) on its own branch. Run every other ticket on the integration branch itself, one after another.

6. When a worktree subagent reports, merge its branch into the integration branch with a **merger subagent**. The merger subagent resolves any conflicts, runs the tests the merged tickets touch, and commits the merge. Use one merger subagent at a time, so merges into the integration branch never race.

7. If a commit changes the **frontier**, kick off **implementer subagents** for the newly unblocked tickets straight away. This allows for maximum concurrency.

8. Once every ticket is committed, run the full test suite.

9. Use /code-review to review the work since the integration branch's fixed point: its merge-base with the base branch. Fix all issues raised in a single **implementer subagent** and commit the fixes.

10. Set the spec's line in `ROADMAP.md` to `done` and commit it, so merging the pull request ships the status with the code.

11. Mark the draft pull request ready for review. Its Evidence lists each acceptance criterion with the test that proves it. It closes the spec, every ticket the branch implements and every issue it fixes, one keyword per issue: `Closes #3, closes #4, closes #5`.

12. Remove the `ready-for-agent` label from each of those issues: the linked pull request now marks them as awaiting human review. The pull request is done when none of them still carries `ready-for-agent` and, unless it is stacked, `gh pr view --json closingIssuesReferences` lists each of them. A stacked pull request lists them only once it is retargeted to the default branch.

13. Clean up all **implementer subagent** worktrees.
