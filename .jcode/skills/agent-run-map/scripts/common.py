"""Shared helpers for the agent-run-map scripts. Python stdlib only.

Every script takes `--config <run.json>`. The config is small; see SKILL.md for its keys.
Paths inside it may use ~. Intermediate files live in the work dir (config "work_dir").
"""
import argparse
import json
import os
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SESSIONS_DIR = os.path.expanduser("~/.jcode/sessions")


def expand(p):
    return os.path.abspath(os.path.expanduser(os.path.expandvars(p))) if p else p


def load_config(path):
    cfg = json.load(open(path))
    cfg.setdefault("coordinator", os.environ.get("JCODE_SESSION_ID"))
    if not cfg["coordinator"]:
        raise SystemExit("no coordinator: set \"coordinator\" in the config or run inside a jcode session")
    if not cfg.get("run_date") and not cfg.get("run_start"):
        cfg["run_date"] = json.load(open(os.path.join(SESSIONS_DIR, cfg["coordinator"] + ".json")))["created_at"][:10]
    cfg["repo"] = expand(cfg.get("repo") or os.getcwd())
    cfg["out_dir"] = expand(cfg.get("out_dir") or os.path.join(cfg["repo"], "docs/research"))
    short = cfg["coordinator"].split("_")[1] if cfg["coordinator"].count("_") >= 2 else cfg["coordinator"]
    cfg["work_dir"] = expand(cfg.get("work_dir") or f"~/.jcode-notes/agent-run-map/{short}-{cfg.get('run_date', 'run')}")
    cfg["failures"] = expand(cfg.get("failures") or os.path.join(cfg["work_dir"], "failures.json"))
    cfg.setdefault("branch", git(cfg["repo"], "rev-parse", "--abbrev-ref", "HEAD").strip())
    cfg.setdefault("title", os.path.basename(cfg["repo"]))
    cfg.setdefault("hot_context", 200_000)
    os.makedirs(cfg["work_dir"], exist_ok=True)
    os.makedirs(cfg["out_dir"], exist_ok=True)
    return cfg


def args(desc):
    ap = argparse.ArgumentParser(description=desc)
    ap.add_argument("--config", required=True, help="run config JSON (see SKILL.md)")
    return ap


def work(cfg, name):
    return os.path.join(cfg["work_dir"], name)


def read_json(cfg, name):
    return json.load(open(work(cfg, name)))


def write_json(cfg, name, obj):
    json.dump(obj, open(work(cfg, name), "w"), indent=1)


def git(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True).stdout


def parse_ts(x):
    return datetime.fromisoformat(x.replace("Z", "+00:00"))


def run_window(cfg):
    """[start, end) of the run in UTC. Defaults to the whole of run_date (UTC) plus `days`-1 days."""
    start = parse_ts(cfg["run_start"]) if cfg.get("run_start") else datetime.fromisoformat(cfg["run_date"]).replace(tzinfo=timezone.utc)
    end = parse_ts(cfg["run_end"]) if cfg.get("run_end") else start + timedelta(days=cfg.get("days", 1))
    return start, end


def tool_uses(msgs):
    for m in msgs:
        for c in m.get("content", []) or []:
            if c.get("type") == "tool_use":
                yield m, c


def tool_result_text(c):
    x = c.get("content")
    if isinstance(x, list):
        return " ".join(i.get("text", "") for i in x if isinstance(i, dict))
    return str(x or "")


def tokens(n):
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}K"


LANES = [
    ("coordinator", "Coordinator", ("coordinator",)),
    ("tickets", "Tickets", ("implementation",)),
    ("mergers", "Mergers", ("merger",)),
    ("reviews", "Reviews & verification", ("reviewer", "verifier")),
    ("fixers", "Fixers", ("fixer",)),
]


def lane_of(role):
    for i, (key, _, roles) in enumerate(LANES):
        if role in roles:
            return i
    return len(LANES) - 1


def time_steps(nodes, edges, coordinator):
    """One step after the latest predecessor. "extra" links run backwards in time and are ignored.
    A session that was taken over sits one step before its replacement."""
    preds = defaultdict(set)
    for e in edges:
        if e["kind"] != "extra":
            preds[e["to"]].add(e["from"])
    for n in nodes:
        if not preds[n] and n != coordinator:
            preds[n].add(coordinator)
    step = {}

    def s(n, stack=()):
        if n in step:
            return step[n]
        step[n] = 0 if not preds[n] or n in stack else 1 + max(s(p, stack + (n,)) for p in preds[n])
        return step[n]

    for n in nodes:
        s(n)
    for e in edges:
        if e["kind"] == "takeover":
            step[e["from"]] = max(step[e["from"]], step[e["to"]] - 1)
    return step


def issues(cfg, numbers):
    """gh issue view for each ticket number, cached in <work_dir>/issues.json."""
    path = work(cfg, "issues.json")
    cache = json.load(open(path)) if os.path.exists(path) else {}
    for n in sorted(set(numbers)):
        if str(n) not in cache:
            out = subprocess.run(["gh", "issue", "view", str(n), "--json", "number,title,body"], cwd=cfg["repo"],
                                 capture_output=True, text=True)
            if out.returncode != 0:
                raise SystemExit(f"gh issue view {n} failed: {out.stderr.strip()}")
            cache[str(n)] = json.loads(out.stdout)
    json.dump(cache, open(path, "w"), indent=1)
    return {int(k): v for k, v in cache.items()}


def section(body, title):
    """Text of a '## <title>' section of an issue body ('' when absent)."""
    m = re.search(rf"^## {re.escape(title)}\s*\n(.*?)(?=^## |\Z)", body, re.S | re.M)
    return m.group(1) if m else ""


def primary_agents(sessions, overrides=None):
    """The agent scored for each ticket: the earliest implementation session that did the work. A session that
    died without editing anything, or a prompt that resumes an earlier worker, is never the primary."""
    by = defaultdict(list)
    for s in sessions:
        if s["role"] == "implementation" and s.get("ticket"):
            by[s["ticket"]].append(s)
    out = {}
    for t, ss in by.items():
        ok = [s for s in ss if not (not s["ended_cleanly"] and s["edit_calls"] == 0) and not s["task_prompt"].startswith("Resume")]
        out[t] = (sorted(ok or ss, key=lambda s: s["created_at"])[0])["name"]
    for t, n in (overrides or {}).items():
        out[int(t)] = n
    return out


def no_pm_reason(s):
    if s["role"] in ("reviewer", "verifier"):
        return "read-only " + s["role"]
    if not s["ended_cleanly"]:
        return "died before finishing" if s["edit_calls"] else "crashed before writing code"
    return "none written"


def merger_scopes(data, ed, branch):
    """A merger's scope is the list of branches it actually merged (edges.json), shortened against the integration branch."""
    for s in data["sessions"]:
        brs = ed.get("merged_by", {}).get(s["name"])
        if s["role"] == "merger" and brs and not s.get("scope_set"):
            short = [b[len(branch) + 1:] if b.startswith(branch + "-") else b for b in brs]
            s["scope"] = "Merge " + ", ".join(short) + f" into {branch}"


def graph_base(cfg):
    """Nodes (one per session, the fields the HTML templates read) and edges for both layouts."""
    data = read_json(cfg, "data.json")
    ed = read_json(cfg, "edges.json")
    merger_scopes(data, ed, cfg["branch"])
    pm_dir = os.path.join(cfg["repo"], "postmortem")
    nodes = []
    for s in data["sessions"]:
        q = s.get("quality")
        nodes.append(dict(
            name=s["name"], role=s["role"], phase=LANES[lane_of(s["role"])][0], ticket=s.get("ticket"), model=s.get("model"),
            duration_min=s["duration_min"], model_calls=s["model_calls"], input_tokens=s["input_tokens"], output_tokens=s["output_tokens"],
            cache_read_tokens=s["cache_read_tokens"], cache_creation_tokens=s["cache_creation_tokens"], total_tokens=s["total_tokens"],
            peak_context=s["peak_context"], scope=s.get("scope"), created_at=s["created_at"], dead=not s["ended_cleanly"],
            quality=dict(total=q["criteria_total"], failed=q["criteria_failed"] or 0, pct=q["failed_pct"] if q["failed_pct"] is not None else 0,
                         title=q["ticket_title"], failed_ids=[f["criterion"] + ("*" if f["ambiguous"] else "") for f in q["failed"]],
                         scored=q["in_correlation"]) if q and q.get("in_correlation") else None,
            postmortem=os.path.relpath(os.path.join(pm_dir, s["postmortem"]), cfg["out_dir"]) if s.get("postmortem") else None,
            no_pm=None if s.get("postmortem") else no_pm_reason(s)))
    coord = next(n["name"] for n in nodes if n["role"] == "coordinator")
    return dict(coordinator=coord, hot=cfg["hot_context"], nodes=nodes, edges=[{k: e[k] for k in ("from", "to", "kind", "label")} for e in ed["edges"]])


def esc_md(s):
    return str(s or "").replace("|", "\\|").replace("\n", " ")


def slug_rel(path, start):
    return os.path.relpath(path, start)


REVIEW_FILE = re.compile(r"([\w.-]+\.md)\b")
