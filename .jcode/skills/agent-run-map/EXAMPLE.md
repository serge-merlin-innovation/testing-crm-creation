# Worked example: the M&A CRM run of 2026-10-10

The skill was proven against the run that produced `docs/research/agent-run-*` (coordinator `session_dragon_1791594378843_3abb849d09a66f69`, 48 sessions). Config used, with outputs in a scratch folder:

```json
{
  "coordinator": "session_dragon_1791594378843_3abb849d09a66f69",
  "repo": "/Users/serge/Projects/testing-crm-creation",
  "run_date": "2026-10-10",
  "out_dir": "~/.jcode/scratch/arm/out/docs/research",
  "work_dir": "~/.jcode/scratch/arm/work",
  "working_dir_globs": ["/Users/serge/Projects/testing-crm-creation", "/Users/serge/Projects/crm-*"],
  "title": "M&A CRM",
  "decision_report": "docs/DECISION-REPORT.md",
  "reviews": [
    {"file": "~/.jcode-notes/ma-crm/review.md", "label": "review 1 (review.md)", "kind": "code"},
    {"file": "~/.jcode-notes/ma-crm/review-spec-a.md", "label": "review 2 (review-spec-a.md)"},
    {"file": "~/.jcode-notes/ma-crm/review-spec-b.md", "label": "review 2 (review-spec-b.md)"},
    {"file": "~/.jcode-notes/ma-crm/review-spec-c.md", "label": "review 2 (review-spec-c.md)"}
  ],
  "ticket_commits": {"1": ["19cd6e3", "5fb8e8e"], "2": ["f04985a", "bab6450"], "3": ["f7caa9a", "296327c"], "4": ["fdf2b04"],
                     "5": ["c729de8", "88f5a9a"], "6": ["5c6906d", "0a313da", "bc65032"], "7": ["6e8bcb0"], "18": ["67aa89c"],
                     "19": ["cefad83", "94ead4e", "863c3f9"], "16": ["de9af70", "f5b8462", "db6a05a"]}
}
```

`failures.json` was the 77 judged rows of the original hand attribution, converted one-to-one.

## Result (compare.py against the committed outputs)

- Sessions: 48 = 48. Per-session tokens (input, output, cache read, cache write, total, peak, model calls, messages, duration): 0 differences.
- Postmortems: all 37 found from the sessions' own tool calls, the same 37 files as the hand list.
- Failed %: 0 differences over the 20 scored agents (56 of 272 criteria, 17 ambiguous). Correlation table identical.
- check.mjs: the timeline HTML file shows 48 cards, 0 overlaps, 0 errors, 0 network requests, and all 37 postmortem links resolve.
- Layout: fed the hand-coded edge set, the timeline layout script reproduces the committed positions and canvas size exactly.

## Edge differences (79 derived vs 74 hand-coded, 73 shared)

| Edge | Why it differs |
|---|---|
| + sabertooth, pawprint, chipmunk, iwazaru → dog (blocks) | Issue #20's "Blocked by" lists #3, #11, #14, #15, #16, #17, #19. The hand list kept only #3, #11, #14. |
| + iwazaru → tigress, iwazaru → wyvern (extra) | iwazaru's prompt asked it to build the pages #4 left out and the admin screens #2 left API-only. The hand list recorded only calf building #5's pages. |
| − turkey → rabbit (findings, "verified") | rabbit verified commit 55a3ce3, which tiger made after turkey's merges. Both links existed in the hand list; the data names only tiger. |

The coordinator itself merged `feat/ma-crm-t5` and `feat/ma-crm-spec-c-be`; these are reported as not drawn, matching the hand list.
