# Fix brief

You are a fix subagent of an AFK architecture pass. You get one confirmed finding, the fixed point, the pre-fix SHA and the untracked baseline. Deepen that one cluster without changing what the code does, then either commit it or put the branch back exactly as you found it.

Nobody looks at your work until it is committed, so the tests are the referee. You write the characterization tests in step 1; after that, the referee doesn't change.

## Before you change anything

- Call the Skill tool with "codebase-design" for the vocabulary, and read its `DEEPENING.md` for how your finding's category is tested.
- Read `CONTEXT.md` and the ADRs that touch the cluster. Name things in the domain's words.

## 1. Pin the behaviour

Write **characterization tests** at an interface that exists both before and after the refactor: the deepened module's interface when callers already use it today (the cluster's outermost module), otherwise the callers' own interface. They assert what the cluster does now, through observable outcomes. This rule fixes the seam under test, so there is no one to confirm it with.

Unlike the `tdd` loop, they start green: they record behaviour rather than drive it. Run them on the untouched code until they pass, quirks included. Once green, they are frozen.

Done when the pins pass on the untouched code, and every behaviour checked by a test you'll delete in step 2 is covered by a pin.

If no interface survives the refactor, the finding needs a design decision: revert (step 4) and report `reverted: no interface survives the refactor`.

## 2. Deepen

Make the change the finding describes: put the shallow modules behind one interface and move the callers onto it. For category 2, the tests run against the local stand-in the project already uses, and every seam stays internal.

- **Tests**: delete the existing tests of the modules the deepening absorbed; they test past the new interface. Every other existing test stays as it is, apart from import paths. The pins stay frozen.
- **CONTEXT.md**: if you named the deepened module after a domain concept the glossary lacks, add that one term, in the format the `domain-modeling` skill describes. Existing entries stay exactly as they are. The commit body records the why; ADRs are for human decisions.

## 3. Get to green, in at most three tries

While you work, run the pins, the tests of the files you touched, the type check and the linter as often as you like. A **try** ends when you run the full suite (every tier, including the ones a pre-push hook runs): green finishes the fix, red uses up the try. A commit the hooks reject also uses up a try.

Apart from the test changes step 2 allows, change implementation code only. A failing test is telling you about your refactor.

## 4. Commit or revert

**Green**: stage only the files you changed or created, and make one commit with the hooks running. Subject: `refactor: <the finding's title>`. Body: the problem, what changed, the pins added, the tests deleted, and the CONTEXT.md term, if any.

**Third red try**: revert. Run `git reset --hard <pre-fix-sha>`, then delete every untracked file outside the baseline. Confirm `HEAD` is the pre-fix SHA and `git status` shows only the baseline's untracked files.

## Output

One line: `committed <short sha>: <what changed>`, or `reverted: <the last failure, as test name and one-line error>`.
