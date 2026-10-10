---
name: improve-codebase-architecture-afk
description: AFK architecture pass over the current branch's diff. Deepens up to two shallow modules in and around the change with no human in the loop, and files the rest as issues. Use when the user asks for an AFK architecture pass.
---

# Improve Codebase Architecture (AFK)

The unattended sibling of `/improve-codebase-architecture`. Nobody picks a candidate and nobody is grilled, so rules make the two calls a human makes there:

- **Pick** is a rating, a category filter, a fresh second opinion, and a cap of two fixes.
- **Shape** is forced: only deepenings that add no new seam, so the code mostly decides the design.

The pass ends with `refactor:` commits on the current branch, issues for what it left alone, and a report for the pull request. Nobody answers questions during the pass. When the rules don't settle a case, take the conservative branch: leave the code alone, file the finding, and say why in the report.

You are the orchestrator. You hold the findings and the results; subagents do the reading and the editing, one at a time. Paste each subagent's brief in full into its prompt: it has no other access to this skill.

**Clean**, throughout: no tracked changes, and no untracked files beyond the baseline saved in step 1.

## Inputs

- **Fixed point**: the commit the branch's change is measured from. Use the one the caller passed; otherwise the merge-base of `HEAD` and the default branch.
- **Issue tracker**: if it wasn't provided, read `docs/agents/issue-tracker.md`. The label string for the `needs-triage` role is in `docs/agents/triage-labels.md`.

## Process

### 1. Check the start

- `git status --porcelain --untracked-files=no` is empty.
- `git diff --name-only <fixed-point>...HEAD` lists at least one file.
- Save `git ls-files --others --exclude-standard` as the **untracked baseline**.

If either check fails, skip to step 6 and report why.

### 2. Review

Spawn one review subagent with [REVIEW.md](REVIEW.md) and the fixed point. Done when it returns a ranked list in which every finding carries every field REVIEW.md asks for. An empty list skips to step 6.

### 3. Sort

Put every finding in exactly one bucket:

- **Eligible**: rated `Strong`, category 1 or 2, no ADR conflict. Keep the reviewer's order.
- **File**: rated `Strong`, but category 3 or 4 (reason: _needs a new seam_) or in conflict with an ADR (reason: _contradicts ADR-NNNN_).
- **Drop**: rated `Worth exploring` or `Speculative`.

### 4. Fix, one finding at a time

Work down the eligible list. At most **two fixes start per pass**, and a fix that ends reverted still used its slot. For each finding:

1. Confirm the tree is clean and record `HEAD` as the **pre-fix SHA**.
2. Spawn a fresh verifier subagent with [VERIFY.md](VERIFY.md) and the finding. It judges the code as the previous fix left it. A `reject` moves the finding to **File** (reason: _verifier: <its reason>_) and uses no slot.
3. On `confirm`, spawn a fix subagent with [FIX.md](FIX.md), the finding, the fixed point, the pre-fix SHA and the untracked baseline. Wait for it to finish before anything else starts.
4. Check its claim against git:
   - `committed`: `HEAD~1` is the pre-fix SHA, the subject of `HEAD` starts with `refactor:`, and the tree is clean.
   - `reverted`: `HEAD` is the pre-fix SHA and the tree is clean. Move the finding to **File** (reason: _reverted: <its last failure>_).

   When git disagrees with the claim, restore the pre-fix state yourself (`git reset --hard <pre-fix-sha>`, then delete the untracked files outside the baseline) and treat the fix as reverted.

Once two fixes have started, move the eligible findings still waiting to **File** (reason: _over the cap of two fixes per pass_).

Done when every eligible finding is committed, reverted, or in **File**, and the tree is clean.

### 5. File issues

List the open issues once. For each finding in **File**, look for an open issue that already covers the same cluster of modules: if there is one, note its number and file nothing. Otherwise create an issue labelled `needs-triage`:

- **Title**: names the deepening in the domain's words, e.g. "Deepen the Order intake module".
- **Body**: files, problem, solution, dependency category, the reason from its bucket, the branch it was found on, and a last line: _Filed by the AFK architecture pass._ Domain terms come from `CONTEXT.md`, architecture terms from `codebase-design`.

Done when every finding in **File** has an issue number, new or existing.

### 6. Report

Return this section for the pull request description, and nothing else:

```md
## Architecture pass

**Fixed**
- `<short sha>` <title>: <what changed, one line>

**Reverted**
- <title>: <last failure, one line>

**Filed**
- #<n> <title>: <reason>
- #<n> <title>: already open
```

Leave out empty groups. A pass that fixed and filed nothing reports one line instead, saying why: no change since the fixed point, tracked changes at the start, or no `Strong` findings in scope.
