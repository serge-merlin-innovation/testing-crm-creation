"""Step 1: collect the run's sessions, token usage and postmortems -> <work_dir>/data.json.

Selection: every ~/.jcode/sessions/session_*.json whose id is the coordinator or whose parent_id is the
coordinator, created inside the run window, optionally filtered by working_dir globs. Messages appended
to the sibling .journal.jsonl after the last snapshot are merged in by message id.
"""
import fnmatch
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import SESSIONS_DIR, args, load_config, parse_ts, run_window, tool_uses, write_json  # noqa: E402

# Ordered: first match wins. Override with config "role_patterns": [[role, regex], ...].
ROLE_PATTERNS = [
    ("implementation", r"^(Implement|Resume)\b[^.\n]*\bissue #(\d+)"),
    ("merger", r"^(Merger task|Merge)\b"),
    ("fixer", r"^(Fix\b|Resume an interrupted fixer)"),
    ("verifier", r"^(Read-only )?[Vv]erif"),
    ("reviewer", r"^(Read-only\b[^.\n]*\breview|Run the /code-review|Review\b)"),
]
CUE_TAKEOVER = r"\b(Resume|resume|previous attempt|previous worker|earlier attempt|respawn|interrupted)\b"
PM_FILE = re.compile(r"postmortem/(\d{4}-\d{2}-\d{2}-\d{4}-[\w.-]+?\.md)")


def load(path):
    d = json.load(open(path))
    msgs = list(d.get("messages") or [])
    seen = {m["id"] for m in msgs}
    jn = 0
    j = path[: -len(".json")] + ".journal.jsonl"
    if os.path.exists(j):
        for line in open(j):
            if not line.strip():
                continue
            for m in json.loads(line).get("append_messages", []):
                if m["id"] not in seen:
                    seen.add(m["id"])
                    msgs.append(m)
                    jn += 1
    return d, msgs, jn


def first_prompt(msgs):
    for m in msgs:
        if m["role"] == "user" and m.get("display_role") != "system":
            t = [c.get("text", "") for c in m.get("content", []) if c.get("type") == "text"]
            if t and t[0].strip():
                return t[0].split("<system-reminder>")[0].strip()
    return ""


def usage(msgs):
    s = dict(input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_creation_tokens=0, peak_context=0, model_calls=0)
    for m in msgs:
        u = m.get("token_usage")
        if not u:
            continue
        s["model_calls"] += 1
        s["input_tokens"] += u.get("input_tokens") or 0
        s["output_tokens"] += u.get("output_tokens") or 0
        s["cache_read_tokens"] += u.get("cache_read_input_tokens") or 0
        s["cache_creation_tokens"] += u.get("cache_creation_input_tokens") or 0
        s["peak_context"] = max(s["peak_context"], u.get("prompt_tokens") or 0)
    s["total_tokens"] = s["input_tokens"] + s["output_tokens"] + s["cache_read_tokens"] + s["cache_creation_tokens"]
    return s


def classify(prompt, is_coord, patterns):
    if is_coord:
        return "coordinator", None
    for role, rx in patterns:
        m = re.search(rx, prompt)
        if m:
            ticket = int(m.group(2)) if role == "implementation" else None
            return role, ticket
    return "other", None


def ended_cleanly(msgs):
    """A session that never sent a swarm report and whose last message is not assistant text died mid-task."""
    reported = any(c.get("name") == "swarm" and (c.get("input") or {}).get("action") == "report" for _, c in tool_uses(msgs))
    convo = [m for m in msgs if m.get("display_role") != "system"]
    last = convo[-1] if convo else None
    last_text = bool(last and last["role"] == "assistant" and any(c.get("type") == "text" for c in last.get("content", [])))
    return reported or last_text


def edit_calls(msgs):
    n = 0
    for _, c in tool_uses(msgs):
        if c.get("name") in ("edit", "write", "apply_patch", "replace", "multiedit"):
            if "postmortem/" not in json.dumps(c.get("input")):
                n += 1
    return n


def postmortem(msgs, pm_dir):
    """The postmortem the session wrote: a write to postmortem/<file>, else a file named in its git add/commit."""
    written, named = [], []
    for _, c in tool_uses(msgs):
        inp = c.get("input") or {}
        fp = str(inp.get("file_path") or "")
        for f in PM_FILE.findall(fp):
            written.append(f)
        if c.get("name") in ("bash", "apply_patch"):
            for f in PM_FILE.findall(json.dumps(inp)):
                named.append(f)
    for f in written + named:
        if os.path.exists(os.path.join(pm_dir, f)):
            return f
    return None


BOILERPLATE = re.compile(r"^(Merger task|Your worktree|Read AGENTS|Do not|Do it read-only)|^\S+ in /\S+( on branch \S+)?( \(tip \w+\))?\.?$")


def scope_of(prompt):
    """The first sentence that says what the job is: location and boilerplate sentences are skipped, paths shortened."""
    text = re.sub(r"(/Users|~)/[\w./~-]*/([\w.-]+)", r"\2", prompt)
    for sent in re.split(r"(?<=[.:])\s+|\n", text):
        sent = sent.strip()
        if sent and not BOILERPLATE.search(sent):
            return sent[:140]
    return text[:140]


def branch_of(prompt):
    m = re.search(r"\bbranch (feat/[\w./-]+|[\w-]+/[\w./-]+)", prompt)
    return m.group(1).rstrip(".,;:)") if m else None


def main():
    cfg = load_config(args(__doc__).parse_args().config)
    C = cfg["coordinator"]
    start, end = run_window(cfg)
    globs = [os.path.expanduser(g) for g in cfg.get("working_dir_globs") or []]
    patterns = cfg.get("role_patterns") or ROLE_PATTERNS
    overrides = cfg.get("overrides") or {}
    pm_dir = os.path.join(cfg["repo"], "postmortem")
    sessions = []
    for f in sorted(glob.glob(SESSIONS_DIR + "/session_*.json")):
        try:
            d0 = json.load(open(f))
        except Exception:
            continue
        if d0.get("id") != C and d0.get("parent_id") != C:
            continue
        if not (start <= parse_ts(d0["created_at"]) < end):
            continue
        wd = d0.get("working_dir") or ""
        if globs and not any(fnmatch.fnmatch(wd, g) for g in globs):
            continue
        d, msgs, jn = load(f)
        after = None
        if d["id"] == C:  # a live coordinator keeps talking after the run: cut at the window end, report the rest apart
            later = [m for m in msgs if m.get("timestamp") and parse_ts(m["timestamp"]) >= end]
            msgs = [m for m in msgs if not (m.get("timestamp") and parse_ts(m["timestamp"]) >= end)]
            if later:
                u = usage(later)
                after = dict(messages=len(later), model_calls=u["model_calls"], total_tokens=u["total_tokens"], peak_context=u["peak_context"],
                             note=f"Coordinator activity after {end.isoformat()}. Excluded from the figures.")
        prompt = first_prompt(msgs)
        role, ticket = classify(prompt, d["id"] == C, patterns)
        ts = [m["timestamp"] for m in msgs if m.get("timestamp")]
        last = max(ts) if ts else d["created_at"]
        name = d.get("short_name") or d["id"]
        s = dict(id=d["id"], name=name, parent_id=d.get("parent_id"), working_dir=wd, model=d.get("model"),
                 provider_key=d.get("provider_key"), reasoning_effort=d.get("reasoning_effort"),
                 created_at=d["created_at"], last_activity=last,
                 duration_min=round((parse_ts(last) - parse_ts(d["created_at"])).total_seconds() / 60, 1),
                 session_status=d.get("status"), messages=len(msgs), journal_messages=jn, **usage(msgs),
                 role=role, ticket=ticket, branch=branch_of(prompt), task_prompt=prompt,
                 takeover_cue=bool(re.search(CUE_TAKEOVER, prompt)), ended_cleanly=d["id"] == C or ended_cleanly(msgs),
                 edit_calls=edit_calls(msgs), postmortem=postmortem(msgs, pm_dir), after_run=after)
        s["scope"] = None if role in ("implementation", "coordinator") else scope_of(prompt)
        s.update(overrides.get(name, {}))
        s["scope_set"] = "scope" in overrides.get(name, {})
        sessions.append(s)
    sessions.sort(key=lambda s: s["created_at"])
    names = [s["name"] for s in sessions]
    dup = {n for n in names if names.count(n) > 1}
    for s in sessions:  # short names are the node ids; disambiguate the rare clash
        if s["name"] in dup:
            s["name"] = s["name"] + "-" + s["id"][-4:]
    write_json(cfg, "data.json", dict(coordinator=C, window=[start.isoformat(), end.isoformat()], sessions=sessions))
    roles = {}
    for s in sessions:
        roles[s["role"]] = roles.get(s["role"], 0) + 1
    print(json.dumps(dict(sessions=len(sessions), roles=roles, dead=[s["name"] for s in sessions if not s["ended_cleanly"]],
                          postmortems=sum(1 for s in sessions if s["postmortem"]),
                          other=[s["name"] for s in sessions if s["role"] == "other"]), indent=1))


if __name__ == "__main__":
    main()
