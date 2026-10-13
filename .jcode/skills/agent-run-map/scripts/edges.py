"""Step 3: derive the relationships between sessions from data -> <work_dir>/edges.json.

Kinds (each edge carries `evidence`, the fact it was derived from):
  blocks    ticket B's issue lists ticket A under "## Blocked by"           (scored agent of A -> of B)
  merged    a merger ran `git merge <branch>`; the branch's worker -> merger, checked against git merge commits
  findings  a fixer's prompt names a review file that a reviewer wrote       (reviewer -> fixer)
            a reviewer/verifier prompt names the commit it read             (session that made the commit -> reviewer)
  takeover  a prompt says resume / previous attempt / interrupted           (dead session -> replacement)
  extra     an implementation prompt asks to build another ticket's left-out work (this agent -> that ticket's agent)

Override with config "edges": {"add": [{from,to,kind,label}], "drop": [[from,to,kind], ...]}.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collect import load  # noqa: E402
from common import SESSIONS_DIR, args, git, issues, load_config, parse_ts, primary_agents, read_json, section, tool_result_text, tool_uses, write_json  # noqa: E402

GIT_MERGE = re.compile(r"git (?:-C \S+ )?merge((?:\s+-{1,2}[\w-]+(?:=\S+)?|\s+-m\s+(?:'[^']*'|\"[^\"]*\"|\S+))*)\s+([\w./-]+)")
MD_FILE = re.compile(r"([\w./~$-]*?/)?([\w.-]+\.md)\b")


def session_msgs(sid):
    p = os.path.join(SESSIONS_DIR, sid + ".json")
    return load(p)[1] if os.path.exists(p) else []


def merges_run(msgs, integration):
    """(timestamp, branch) for every `git merge <branch>` a session ran, the integration branch itself excluded."""
    out = []
    for m, c in tool_uses(msgs):
        if c.get("name") != "bash":
            continue
        cmd = (c.get("input") or {}).get("command", "")
        for g in GIT_MERGE.finditer(cmd):
            br = g.group(2)
            if br in (integration, "--abort", "--continue", "HEAD") or br.startswith("-") or "merge-wip" in br or re.fullmatch(r"[0-9a-f]{7,40}", br):
                continue
            out.append((m.get("timestamp"), br))
    seen, uniq = set(), []
    for ts, br in out:
        if br not in seen:
            seen.add(br)
            uniq.append((ts, br))
    return uniq


def written_files(msgs, prompt):
    """Basenames of .md files a session wrote: write/edit calls, plus the output file its prompt names."""
    names = set()
    for _, c in tool_uses(msgs):
        if c.get("name") in ("write", "edit", "apply_patch"):
            fp = str((c.get("input") or {}).get("file_path") or "")
            if fp.endswith(".md"):
                names.add(os.path.basename(fp))
    for m in re.finditer(r"\b[Ww]rite (?:the findings to |the report to )?(\S+?\.md)\b", prompt):
        names.add(os.path.basename(m.group(1)))
    return {n for n in names if not n.startswith(("20", "README", "notes"))}


def commit_author(sha, sessions, msgs_of, repo, exclude):
    """The session that made a commit: the earliest tool result naming the sha at or after its commit time."""
    ct = git(repo, "log", "-1", "--format=%cI", sha).strip()
    if not ct:
        return None
    t0 = parse_ts(ct)
    best = None
    for s in sessions:
        if s["name"] in exclude:
            continue
        for m in msgs_of[s["name"]]:
            ts = m.get("timestamp")
            if not ts or parse_ts(ts) < t0 or (parse_ts(ts) - t0).total_seconds() > 900:
                continue
            if any(c.get("type") == "tool_result" and sha in tool_result_text(c) for c in m.get("content", []) or []):
                if best is None or ts < best[0]:
                    best = (ts, s["name"])
                break
    return best and best[1]


def main():
    cfg = load_config(args(__doc__).parse_args().config)
    data = read_json(cfg, "data.json")
    sessions = data["sessions"]
    S = {s["name"]: s for s in sessions}
    C = next(s["name"] for s in sessions if s["role"] == "coordinator")
    integ = cfg["branch"]
    msgs_of = {s["name"]: session_msgs(s["id"]) for s in sessions}
    primary = {int(k): v for k, v in (data.get("primary") or {}).items()} or primary_agents(sessions, cfg.get("primary"))
    edges, unresolved = [], []

    def add(a, b, kind, label="", evidence=""):
        if a and b and a != b and not any(e["from"] == a and e["to"] == b and e["kind"] == kind for e in edges):
            edges.append(dict(**{"from": a, "to": b}, kind=kind, label=label, evidence=evidence))

    # blocks: "## Blocked by" of each ticket's issue
    tickets = sorted(primary)
    iss = issues(cfg, tickets)
    for t in tickets:
        for b in re.findall(r"#(\d+)", section(iss[t]["body"], "Blocked by")):
            b = int(b)
            if b in primary:
                add(primary[b], primary[t], "blocks", "", f"issue #{t} Blocked by #{b}")
            else:
                unresolved.append(f"#{t} is blocked by #{b}, which has no session in this run")

    # merged: the git merges each merger ran, mapped to the worker that last held that branch
    git_merges = git(cfg["repo"], "log", "--merges", "--first-parent", "--format=%h %s", integ).splitlines()
    workers = [s for s in sessions if s["role"] in ("implementation", "fixer") and s.get("branch")]
    merged_by = {}
    for s in sessions:
        if s["role"] != "merger":
            continue
        for ts, br in merges_run(msgs_of[s["name"]], integ):
            cands = [w for w in workers if w["branch"] == br and (not ts or w["created_at"] < ts)]
            if not cands:
                unresolved.append(f"{s['name']} merged {br}, which no worker session held")
                continue
            w = max(cands, key=lambda w: w["created_at"])
            t = w.get("ticket")
            confirmed = [l.split()[0] for l in git_merges if br in l or (t and re.search(rf"(ticket )?#{t}\b", l))]
            add(w["name"], s["name"], "merged", "merged by", f"{s['name']} ran git merge {br}" + (f"; merge commit {confirmed[-1]}" if confirmed else "; no matching merge commit"))
            merged_by.setdefault(s["name"], []).append(br)
    for ts, br in merges_run(msgs_of[C], integ):  # the coordinator's own merges are facts for the report, not edges
        unresolved.append(f"coordinator {C} ran git merge {br} itself")

    # takeovers: a cue in the prompt, a dead predecessor with the same ticket (or branch) and role
    succ = {}
    for s in sessions:
        if not s.get("takeover_cue"):
            continue
        key = (lambda o: o.get("ticket") == s["ticket"]) if s.get("ticket") else (lambda o: o.get("branch") == s.get("branch"))
        dead = [o for o in sessions if o["role"] == s["role"] and not o["ended_cleanly"] and o["created_at"] < s["created_at"] and key(o)]
        if not dead:
            continue
        p = max(dead, key=lambda o: o["created_at"])
        succ.setdefault(p["name"], []).append(s["name"])
    for p, rs in succ.items():
        for i, r in enumerate(sorted(rs, key=lambda n: S[n]["created_at"])):
            verb = "resumed" if re.match(r"Resume", S[r]["task_prompt"]) else "respawned"
            label = f"split into {len(rs)}" if len(rs) > 1 and i == 0 else ("" if len(rs) > 1 else verb)
            add(p, r, "takeover", label, f"{r}'s prompt resumes or replaces work; {p} ended without a report")

    # findings: review files written by reviewers, named by fixers
    wrote = {s["name"]: written_files(msgs_of[s["name"]], s["task_prompt"]) for s in sessions if s["role"] in ("reviewer", "verifier")}
    replaced = {r for rs in succ.values() for r in rs}
    for s in sessions:
        if s["role"] != "fixer":
            continue
        named = {m.group(2) for m in MD_FILE.finditer(s["task_prompt"])}
        named |= {f"{a}{x}.md" for a, xs in re.findall(r"([\w-]+-)\{([\w,]+)\}\.md", s["task_prompt"]) for x in xs.split(",")}
        for rv, files in wrote.items():
            hit = sorted(named & files)
            if not hit:
                continue
            pred = [p for p, rs in succ.items() if s["name"] in rs]
            if s["name"] in replaced and any(e["from"] == rv and e["to"] in pred for e in edges if e["kind"] == "findings"):
                continue  # a resumed fixer inherits its predecessor's findings through the takeover link
            add(rv, s["name"], "findings", "findings", f"{s['name']}'s prompt names {', '.join(hit)} written by {rv}")
    # findings: the commit a reviewer or verifier read
    for s in sessions:
        if s["role"] not in ("reviewer", "verifier") or s["name"] in replaced:
            continue
        m = re.search(r"\b(?:tip|at|@)\s+([0-9a-f]{7,40})\b", s["task_prompt"])
        if not m:
            continue
        who = commit_author(m.group(1), sessions, msgs_of, cfg["repo"], {s["name"]})
        if who and who != C:
            add(who, s["name"], "findings", "verified" if s["role"] == "verifier" else f"reviewed {m.group(1)}", f"{s['name']} read {m.group(1)}, committed by {who}")
        elif not who:
            unresolved.append(f"{s['name']} read {m.group(1)}: no session found that made it")

    # extra: an implementation prompt that hands over another ticket's left-out work
    for s in sessions:
        if s["role"] != "implementation":
            continue
        for sent in re.split(r"(?<=[.;])\s+|\n", s["task_prompt"]):
            if not re.search(r"\b(build|built)\b", sent, re.I) or not re.search(r"left (out|these)|missing|API-only", sent):
                continue
            for t in {int(x) for x in re.findall(r"#(\d+)", sent)} - {s["ticket"]}:
                if t in primary:
                    what = "pages" if re.search(r"page|screen", sent, re.I) else "work"
                    add(s["name"], primary[t], "extra", f"built #{t} {what}", sent[:160])

    ov = cfg.get("edges") or {}
    drop = {tuple(x) for x in ov.get("drop", [])}
    edges = [e for e in edges if (e["from"], e["to"], e["kind"]) not in drop]
    for e in ov.get("add", []):
        add(e["from"], e["to"], e["kind"], e.get("label", ""), "config edges.add")
    write_json(cfg, "edges.json", dict(edges=edges, merged_by=merged_by, takeovers=succ, unresolved=unresolved))
    count = {}
    for e in edges:
        count[e["kind"]] = count.get(e["kind"], 0) + 1
    print(json.dumps(dict(edges=len(edges), kinds=count, unresolved=unresolved), indent=1))


if __name__ == "__main__":
    main()
