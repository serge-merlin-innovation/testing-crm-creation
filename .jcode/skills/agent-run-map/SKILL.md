---
name: agent-run-map
description: "Map a finished multi-agent run as one offline HTML timeline: token use vs acceptance criteria failed first time, per-agent links and postmortems."
disable-model-invocation: true
---

You are mapping one **run**: a coordinator session and every subagent it spawned. The only output is one file in the output folder:

- `agent-run-map-timeline.html`: the interactive map. Time runs left to right, with one lane per role.

Everything is local. Each postmortem link is a relative path from the HTML file to the session's local `<repo>/postmortem/*.md` file, never a GitHub or other remote URL. The HTML is self-contained and loads nothing over the network.
 
The scripts in `scripts/` do the mechanical work (Python stdlib; Playwright from the repo's frontend for the check). Your job is the judgement they cannot do: the failure attribution. Run every script from this skill's folder with `--config <run.json>`. A full config, and the result of proving the skill against a real run, are in [`EXAMPLE.md`](EXAMPLE.md).
 
## Steps

1. **Write the run config.** Create `run.json` in a work dir outside the repo (default `~/.jcode-notes/agent-run-map/<coordinator-short-name>-<run-date>/`). Only `coordinator` is required. Default it to the current session (`$JCODE_SESSION_ID`) when the user says "my last run" from the coordinator. Otherwise search `~/.jcode/sessions/session_*.json` for the session whose `id` many others name as `parent_id`. Keys:

   | Key | Default | Meaning |
   |---|---|---|
   | `coordinator` | `$JCODE_SESSION_ID` | coordinator session id |
   | `repo` | cwd | repo the run worked on |
   | `run_date` | coordinator's `created_at` day (UTC) | run window start; `days` (1) sets its length, or give `run_start` / `run_end` |
   | `out_dir` | `<repo>/docs/research` | where the timeline HTML goes |
   | `work_dir` | see above | intermediate JSON (`data.json`, `edges.json`, `graph-*.json`, `issues.json`) |
   | `working_dir_globs` | none | keep sessions whose `working_dir` matches, e.g. the repo and its worktrees `~/Projects/<repo>-*` |
   | `branch` | repo's current branch | integration branch the mergers merged into |
   | `title` | repo folder name | shown in headings |
   | `reviews` | none | `[{file, label, kind: "trace"\|"code"}]`: review files for the failure draft |
   | `decision_report` | none | repo-relative decision log whose rows carry `superseded_marker` ("Superseded by review") |
   | `failures` | `<work_dir>/failures.json` | the judged failure rows (step 3) |
   | `hot_context` | 200000 | peak context drawn with an orange outline |
   | `overrides`, `primary`, `edges`, `ticket_commits`, `role_patterns` | none | corrections, see Reference |

   Done when the file parses and names an existing `~/.jcode/sessions/<coordinator>.json`.

2. **Collect sessions.** `python3 scripts/collect.py --config run.json`. It keeps the coordinator plus every session whose `parent_id` is the coordinator, created in the run window and matching `working_dir_globs`. It merges `session_*.journal.jsonl` messages by id and sums `token_usage`. It classifies each **role** from the first non-system user message, and finds each postmortem from the session's own write or commit of `postmortem/*.md`. Read the printed summary. Done when every session has a role other than `other` (fix with `overrides` or `role_patterns`), and each name in `dead` really crashed or was killed (check its last messages).

3. **Attribute failures.** `python3 scripts/quality.py --config run.json draft` reads the criteria from `gh issue view N` and turns the review files into `failures.draft.json`. Judge every draft row by the rules under **Failed first time**, and save the result as the `failures` file. Then run `python3 scripts/quality.py --config run.json`. Done when the score run exits 0. It refuses an `owned` row whose criterion is not in that ticket's issue. Every ambiguous row also needs a note saying who else shares the blame.

4. **Derive edges.** `python3 scripts/edges.py --config run.json`. Every edge carries the evidence it came from, see **Edges**. Done when every line under `unresolved` is either expected (the coordinator's own merges) or fixed with `edges.add` / `edges.drop` in the config, with the reason in your final message.

5. **Lay out.** `python3 scripts/layout_timeline.py --config run.json`. Done when it prints its size, and the lane counts add up to the session count.

6. **Render.** `python3 scripts/render.py --config run.json`. It writes `agent-run-map-timeline.html` and nothing else. Done when it prints that one path.

7. **Verify.** `node scripts/check.mjs --repo <repo> --expect <sessions> --shots <work_dir> <out_dir>/agent-run-map-timeline.html`. Look at the `*-fit.png` screenshot. When an earlier output exists, also run `python3 scripts/compare.py --config run.json --ref-dir <old out_dir>`, and explain every difference it prints in your final message. Done when check.mjs exits 0: the expected card count, 0 overlaps, 0 errors, 0 network requests, and every postmortem link resolving to a local file on disk.

## Reference

### Roles

First match on the first prompt wins (`collect.py` `ROLE_PATTERNS`):

| Role | Prompt starts with | Lane |
|---|---|---|
| implementation | `Implement … issue #N`, `Resume … issue #N` (ticket = N) | Tickets |
| merger | `Merger task`, `Merge` | Mergers |
| fixer | `Fix`, `Resume an interrupted fixer` | Fixers |
| verifier | `Read-only verification`, `Verify` | Reviews |
| reviewer | `Read-only … review`, `Run the /code-review`, `Review` | Reviews |

A session is **dead** when it never sent a `swarm report` and its last message is not assistant text. The **scored agent** for a ticket is the earliest implementation session that is not dead-without-edits and whose prompt does not start with `Resume`. Override it with `primary: {"12": "name"}`. A ticket's commits are matched by `#N` / `ticket N` / `tN` in `git log <branch>` subjects. Early commits that do not name the ticket go in `ticket_commits: {"N": ["sha", …]}`.

### Failed first time

**failed %** = criteria of the ticket that a later review found unmet ÷ all criteria of the ticket.

- **Criteria.** Taken from the issue's "User stories covered" list. A `(criteria 1,3)` subset counts only those. Otherwise every `- [ ]` line under the story under "Acceptance criteria" counts. A `- cross-cutting` story becomes `X-1..X-n`.
- **Sources.** A code-review blocker or should-fix finding, mapped to the criterion it cites or breaks. A traceability row marked WEAK, MISSING or CONTRADICTS. A decision-report row marked superseded by a review, where an agent quietly narrowed the spec. A criterion counts once, however many sources flag it.
- **Row kinds.** `owned`: the criterion is in that ticket's issue and its own work missed it, so it counts in the %. `cross`: the finding hit this ticket's code but another ticket's criterion, so it is listed on the code's agent and left out of its %. `excluded`: considered and not counted, with the reason in the note.
- **Exclude** a finding that maps to no criterion, a finding about code that had not merged when the review ran (compare the review's commit with the merge commits), a row written by a fixer rather than a ticket agent, and a row the code had already fixed before the review.
- **Ambiguous.** When the criterion's ticket and the code's author differ (a ticket's screens assigned to another agent, a route from one ticket guarded by another), keep the failure on the criterion's ticket and write "ambiguous between #A and #B" in the note. Notes matching `ambigu` are counted and starred.
- **Caveats to state in your final message.** Small n. Ticket size and type confound the result. Who failed is not always who was asked (give the ambiguous count). The review rounds differ in method and in branch state. WEAK fails a working feature whose test does not prove it. The attribution is a judged estimate, not a measurement.

The draft gets the traceability rows almost right: in the reference run it found 49 of the 56 owned failures. It cannot judge code-review findings or decision rows. Treat every row with `kind`, `ticket` and `note` as a proposal.

### Edges

| Kind | Derived from | Arrow |
|---|---|---|
| blocks | each issue's `## Blocked by` list | scored agent of the blocker → scored agent of the ticket |
| merged | each merger's own `git merge <branch>` commands; the worker that last held that branch (the `branch …` in its prompt) before the merge; checked against `git log --merges --first-parent <branch>` | worker → merger |
| findings | a fixer's prompt naming a review file (`review-spec-{a,b}.md` expands) that a reviewer wrote or was told to write | reviewer → fixer |
| findings | a reviewer or verifier prompt naming the commit it read (`tip`, `at`, `@` + sha); the session that made the commit is the first whose tool result names the sha within 15 minutes of its commit time | committer → reviewer |
| takeover | a prompt with resume / previous attempt / interrupted, and a dead predecessor with the same ticket (or branch) and role. One predecessor with several successors is labelled "split into n" | dead session → replacement |
| extra | an implementation prompt asking to build pages or work that another ticket left out | this agent → that ticket's scored agent |

A resumed fixer inherits its predecessor's findings link and gets none of its own. The coordinator's own merges are listed as not drawn.

### Data the scripts cannot derive

- The failure attribution itself (`failures.json`): kinds, exclusions, cross-ticket blame and ambiguity notes need someone to read the reviews.
- Early ticket commits whose subjects do not name the ticket (`ticket_commits`).
- A link that happened only in a DM or the coordinator's head, with no trace in a prompt, a git command or an issue. Add it with `edges.add`.
- A takeover whose predecessor did not die (an alive session replaced by hand) has no dead predecessor to match. Add it with `edges.add`.
