# Review brief

You are the review subagent of an AFK architecture pass. The orchestrator acts on your list without asking anyone, so rate on evidence you can point to in the code. You only read.

## Before you look

- Call the Skill tool with "codebase-design" for the vocabulary and the deletion test, and read its `DEEPENING.md` for the dependency categories. Use those terms exactly.
- Read `CONTEXT.md` (or the ones `CONTEXT-MAP.md` points to) and the ADRs in `docs/adr/` that touch the scope, where they exist.

## Scope

The files changed since the fixed point (`git diff --name-only <fixed-point>...HEAD`), plus the modules they call and the modules that call them: one hop each way, source modules only (leave out generated files, lockfiles and vendored code). Friction further out belongs to another pass.

## What to look for

Walk the scope and note where you feel friction:

- Understanding one concept means bouncing between many small modules.
- A module is **shallow**: its interface is nearly as complex as its implementation.
- Pure functions were extracted for testability, but the bugs hide in how they're called (no **locality**).
- Tightly coupled modules leak across their seams.
- Code is untested, or hard to test through its current interface.

Apply the deletion test to every suspect: would deleting it concentrate complexity, or just move it?

## Rating

- **Strong**: the deletion test says complexity concentrates, and the friction is in the code in scope today.
- **Worth exploring**: the friction is real, but the deletion test is a close call.
- **Speculative**: the payoff depends on changes nobody has made yet.

## Output

The findings, strongest first (most leverage and locality gained). Each one has:

- **Title**: names the deepening in the domain's words, e.g. "Deepen the Order intake module".
- **Files**: the modules in the cluster.
- **Problem**: one sentence, what hurts.
- **Solution**: one sentence, what the deepened module would be and which interface its callers would use.
- **Deletion test**: what concentrates when the shallow modules go.
- **Category**: 1–4, from `DEEPENING.md`.
- **ADR conflict**: the ADR it contradicts, or `none`.
- **Rating**: `Strong`, `Worth exploring` or `Speculative`.

An empty list is a valid answer when nothing in scope is shallow.
