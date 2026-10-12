# Postmortem: agent-run-map skill

- Date: 2026-10-12 12:54
- Role: worker
- Task: Turn the one-off agent-map scripts into a reusable skill (`.jcode/skills/agent-run-map/`) and prove it reproduces the 2026-10-10 run's outputs
- Model: Claude (jcode, session chick)

## Summary

I read the reference scripts in `~/.jcode-notes/ma-crm/agent-map/src/`, the three committed outputs and the house-style skills. Then I wrote a seven-step skill. Its scripts are stdlib Python plus a Playwright check: collect, quality (draft and score), edges, two layouts, render, check and compare. They derive the session list, roles, postmortems, ticket dependencies, merges, review findings and takeovers from session files, `gh` issues and git. Run end to end into a scratch folder, they reproduced the 48 sessions, every per-session token figure, every failed % (56/272, 17 ambiguous) and the correlation table, with 0 differences. Fed the hand-coded edges, the layouts reproduced the committed positions exactly. The derived edge set differs from the hand list by 7 edges, each explained in EXAMPLE.md. check.mjs passed on both maps: 48 cards, 0 overlaps, 0 errors, 0 network requests, 37/37 links. I committed and pushed only the skill folder.

## Findings

### 1. Session JSON has no "ended" or "crashed" field, so dead sessions are inferred

- Category: Information access
- Severity: medium
- Evidence: The `status` field reads "Closed" for both bird (crashed) and cat (finished), and "Active" for sauropod (killed). I had to infer death from "no `swarm report` and the last message is not assistant text", which matched the four known cases but is a heuristic.
- Suggested change: Have the swarm runtime record an end reason (reported, crashed, killed, restarted) in the session file, and read it in `collect.py` when present.
- Target: jcode session format; `.jcode/skills/agent-run-map/scripts/collect.py` (`ended_cleanly`)

### 2. Review commits and the reviewer's own output file are not linked to sessions anywhere

- Category: Information access
- Severity: medium
- Evidence: Mapping "reviewer read commit X" to the session that made X needed a scan of every tool result for the sha within 15 minutes of the commit time. Mapping a fixer to its review file needed both the reviewer's write calls and its prompt (pig and ox wrote via a path the scan does not see).
- Suggested change: Ask coordinators to name the producing session in fixer and reviewer prompts ("findings from <session>"), or write a `Session:` trailer on commits. Either would let `edges.py` read the link instead of inferring it.
- Target: coordinator prompt conventions (`docs/agents/CONSTITUTION.md` or the swarm prompt); `edges.py`

### 3. The destructive-command gate blocks scratch cleanup even with an explicit path

- Category: Tool economy
- Severity: low
- Evidence: Two `rm -f` calls on files in `$JCODE_SCRATCH_DIR` that I had just generated were refused (one for a glob, one for a variable path). They needed a re-issue with a justification. A `find -exec rm` on a non-existent `__pycache__` was refused too.
- Suggested change: Allow deletes inside `$JCODE_SCRATCH_DIR` without the gate, or write scratch-only cleanup through the dedicated tools.
- Target: jcode Bash destructive-command gate

### 4. The failure draft cannot judge code-review findings

- Category: Automated checks
- Severity: low
- Evidence: `quality.py draft` recovered 49 of the 56 judged owned failures. The misses are code-review B/S findings that cite no criterion ID in their text, and decision rows whose criterion is implied.
- Suggested change: Ask reviewers to tag each finding with the criterion ID it breaks (`(AUTHZ-02 c6)`). The code-review skill could require it.
- Target: `.jcode/skills/code-review/SKILL.md`

## Worker postmortems

none
