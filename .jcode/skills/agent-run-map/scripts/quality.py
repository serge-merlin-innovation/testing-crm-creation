"""Step 2: acceptance criteria and failed-first-time scores -> quality fields in <work_dir>/data.json.

  quality.py --config run.json draft   # writes <work_dir>/failures.draft.json from the review files
  quality.py --config run.json         # scores from the judged failures file (config "failures")

Criteria come from `gh issue view N`: every `- [ ]` line under each story of "## Acceptance criteria",
restricted to the subsets named in "## User stories covered" (`- STORY-01 (criteria 1,3)`).
A "- cross-cutting" story becomes X-1..X-n from the `**Cross-cutting` block.

Failures file: a JSON list of rows {ticket, criterion, source, ref, kind, note}.
  kind "owned"    = the criterion is in that ticket's issue and its own work missed it (counts in failed %).
  kind "cross"    = another ticket's criterion, broken by this ticket's code (listed, not in %).
  kind "excluded" = considered and not counted (the note says why). ticket may be null.
A note containing "ambiguous" marks the attribution as ambiguous.
"""
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import args, expand, git, issues, load_config, primary_agents, read_json, section, write_json  # noqa: E402

STATUS = re.compile(r"\b(WEAK|MISSING(?: \(UI\))?|CONTRADICTS)\b")
CRIT = re.compile(r"\b([A-Z]{1,6}-\d+ c\d+|X-\d+)\b")


def criteria(issue):
    b = issue["body"]
    ac = section(b, "Acceptance criteria")
    counts, cur = {}, None
    for line in ac.splitlines():
        m = re.match(r"\*\*([A-Z]+-\d+):", line)
        if m:
            cur = m.group(1)
            counts.setdefault(cur, 0)
            continue
        if line.startswith("**Cross-cutting"):
            cur = "X"
            counts["X"] = 0
            continue
        if re.match(r"\s*- \[ \]", line) and cur:
            counts[cur] += 1
    ids, stories = [], []
    for line in section(b, "User stories covered").strip().splitlines():
        line = line.strip()
        if line.lower() == "- cross-cutting":
            ids += [f"X-{i}" for i in range(1, counts.get("X", 0) + 1)]
            stories.append("cross-cutting")
            continue
        m = re.match(r"-\s*([A-Z]+-\d+)(?:\s*\(criteria? ([\d,\s]+)\))?", line)
        if not m:
            continue
        sid = m.group(1)
        stories.append(sid)
        lst = [int(x) for x in m.group(2).split(",")] if m.group(2) else list(range(1, counts.get(sid, 0) + 1))
        ids += [f"{sid} c{i}" for i in lst]
    return dict(title=issue["title"], stories=stories, criteria=ids)


def owner_of(crit):
    own = {}
    for t, c in crit.items():
        for cid in c["criteria"]:
            own.setdefault(cid, t)
    return own


def draft(cfg, crit):
    """Candidate failure rows read from the review files. Every row still needs a human or agent judgement:
    the kind, cross-ticket blame, exclusions and ambiguity notes are not in the review text."""
    own = owner_of(crit)
    rows = []
    for r in cfg.get("reviews") or []:
        path, label, kind = expand(r["file"]), r["label"], r.get("kind", "trace")
        text = open(path).read()
        if kind == "trace":  # | ID c# | test | STATUS |
            for line in text.splitlines():
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) < 3 or not CRIT.match(cells[0]):
                    continue
                st = STATUS.search(cells[-1])
                if not st:
                    continue
                cid = CRIT.match(cells[0]).group(1)
                rows.append(dict(ticket=own.get(cid), criterion=cid, source=label, ref=st.group(1),
                                 kind="owned" if cid in own else "excluded", note="" if cid in own else "criterion is in no ticket"))
        else:  # code review: '### B1. title' / '### S3. title', criterion cited in the heading or body
            for m in re.finditer(r"^#+\s*([BS]\d+)\.\s*(.*?)\n(.*?)(?=^#+\s*[BSN]\d+\.|\Z)", text, re.S | re.M):
                ref, title, body = m.groups()
                cids = list(dict.fromkeys(CRIT.findall(title + " " + body)))
                for cid in cids or [None]:
                    rows.append(dict(ticket=own.get(cid), criterion=cid or "-", source=label, ref=ref,
                                     kind="owned" if cid in own else "excluded",
                                     note=title.strip()[:160] + ("" if cid else " (no criterion cited: judge or exclude)")))
    dr = cfg.get("decision_report")
    if dr:
        marker = cfg.get("superseded_marker", "Superseded by review")
        for line in open(os.path.join(cfg["repo"], dr)):
            if marker not in line or not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            t = re.search(r"Ticket #(\d+)", line)
            cids = list(dict.fromkeys(CRIT.findall(line)))
            rows.append(dict(ticket=int(t.group(1)) if t else None, criterion=cids[0] if cids else "?",
                             source=f"{os.path.basename(dr)} (superseded)", ref=f"D{cells[0]}", kind="owned" if t else "excluded",
                             note=("criterion guessed from the row text: check it. " if cids else "name the criterion. ") + cells[2][:120]))
    write_json(cfg, "failures.draft.json", rows)
    print(f"{len(rows)} draft rows -> {cfg['work_dir']}/failures.draft.json. Judge each, then save as {cfg['failures']}")


def commits_for(log, n, extra):
    pat = re.compile(rf"(#|[Tt]icket #?|\bt){n}\b(?!\d)")
    out = [l for l in log if l.split(" ", 1)[0] in extra]
    for l in log:
        subj = l.split(" ", 1)[1] if " " in l else ""
        if not pat.search(subj) or subj.startswith("Merge") or "postmortem" in subj.lower() or subj.startswith(("Log decision", "Decision")):
            continue
        if re.search(r"into (\S+-t\d|ticket #|#\d+)", subj) or l in out:
            continue
        out.append(l)
    return out[:12]


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return sxy / (sx * sy) if sx and sy else 0.0


def ranks(v):
    o = sorted(range(len(v)), key=lambda i: v[i])
    r = [0] * len(v)
    i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
            j += 1
        for k in range(i, j + 1):
            r[o[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def p_value(r, n):
    """Two-sided t-test of Pearson r, via the regularised incomplete beta (continued fraction)."""
    t = r * math.sqrt((n - 2) / max(1e-12, 1 - r * r))
    df = n - 2
    x = df / (df + t * t)

    def betacf(a, b, x):
        qab, qap, qam = a + b, a + 1, a - 1
        c, d = 1, 1 - qab * x / qap
        d = 1 / d
        h = d
        for m in range(1, 200):
            m2 = 2 * m
            aa = m * (b - m) * x / ((qam + m2) * (a + m2))
            d = 1 / (1 + aa * d)
            c = 1 + aa / c
            h *= d * c
            aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
            d = 1 / (1 + aa * d)
            c = 1 + aa / c
            h *= d * c
        return h

    a, b = df / 2, 0.5
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    return bt * betacf(a, b, x) / a if x < (a + 1) / (a + b + 2) else 1 - bt * betacf(b, a, 1 - x) / b


def stat(xs, ys):
    if len(xs) < 3:
        return None
    r = pearson(xs, ys)
    return dict(pearson_r=round(r, 3), p_two_sided=round(p_value(r, len(xs)), 3), spearman_rho=round(pearson(ranks(xs), ranks(ys)), 3), n=len(xs))


def score(cfg, data, crit):
    sessions = data["sessions"]
    if not os.path.exists(cfg["failures"]):
        raise SystemExit(f"no failures file at {cfg['failures']}: run `quality.py draft`, judge the rows, save them there "
                         "(an empty list [] scores every ticket at 0%)")
    rows = json.load(open(cfg["failures"]))
    own = owner_of(crit)
    owned, cross, excluded, problems = {}, {}, [], []
    for r in rows:
        t, cid, kind = r.get("ticket"), r["criterion"], r["kind"]
        src = dict(source=r["source"], ref=r["ref"], note=r.get("note", ""))
        if kind == "excluded":
            excluded.append(dict(criterion=cid, **src))
        elif kind == "owned":
            if cid not in crit.get(t, {}).get("criteria", []):
                problems.append(f"{cid} is not a criterion of #{t} (owner: #{own.get(cid)})")
                continue
            owned.setdefault(t, {}).setdefault(cid, []).append(src)
        else:
            cross.setdefault(t, []).append(dict(criterion=cid, **src))
    if problems:
        raise SystemExit("failures file does not match the issues:\n  " + "\n  ".join(problems))
    primary = primary_agents(sessions, cfg.get("primary"))
    log = git(cfg["repo"], "log", "--format=%h %s", cfg["branch"]).splitlines()
    extra = {int(k): v for k, v in (cfg.get("ticket_commits") or {}).items()}
    amb = re.compile(r"[Aa]mbigu")
    for s in sessions:
        s["quality"] = None
        t = s.get("ticket")
        if s["role"] != "implementation" or t not in crit:
            continue
        c = crit[t]
        q = dict(ticket_title=c["title"], stories=c["stories"], criteria=c["criteria"], criteria_total=len(c["criteria"]),
                 implementation_commits=commits_for(log, t, extra.get(t, [])))
        if primary.get(t) == s["name"]:
            fails = owned.get(t, {})
            q.update(failed=[dict(criterion=k, sources=v, ambiguous=any(amb.search(x["note"]) for x in v)) for k, v in sorted(fails.items())],
                     criteria_failed=len(fails), failed_pct=round(100 * len(fails) / max(1, len(c["criteria"])), 1),
                     cross_ticket_findings=cross.get(t, []), in_correlation=True)
        else:
            why = "died before editing code" if not s["ended_cleanly"] and s["edit_calls"] == 0 else "took over or added to the scored agent's work"
            q.update(failed=[], criteria_failed=None, failed_pct=None, cross_ticket_findings=[], in_correlation=False,
                     note=f"Not scored: {primary.get(t)} is scored for #{t}. This session {why}.")
        s["quality"] = q
    pts = [s for s in sessions if s.get("quality") and s["quality"]["in_correlation"]]
    fp = [s["quality"]["failed_pct"] for s in pts]
    corr = {}
    if len(pts) >= 3:
        top = max(pts, key=lambda s: s["total_tokens"])
        rest = [s for s in pts if s is not top]
        extra_tok = {s["name"]: sum(o["total_tokens"] for o in sessions if o["role"] == "implementation" and o.get("ticket") == s["ticket"] and o is not s) for s in pts}
        corr = dict(
            peak_context_vs_failed_pct=stat([s["peak_context"] for s in pts], fp),
            total_tokens_vs_failed_pct=stat([s["total_tokens"] for s in pts], fp),
            output_tokens_vs_failed_pct=stat([s["output_tokens"] for s in pts], fp),
            total_tokens_vs_criteria_total=stat([s["total_tokens"] for s in pts], [s["quality"]["criteria_total"] for s in pts]),
            peak_context_vs_criteria_failed_count=stat([s["peak_context"] for s in pts], [s["quality"]["criteria_failed"] for s in pts]),
            total_tokens_vs_failed_pct_without_top=stat([s["total_tokens"] for s in rest], [s["quality"]["failed_pct"] for s in rest]),
            peak_context_vs_failed_pct_without_top=stat([s["peak_context"] for s in rest], [s["quality"]["failed_pct"] for s in rest]),
            total_tokens_incl_takeovers_vs_failed_pct=stat([s["total_tokens"] + extra_tok[s["name"]] for s in pts], fp),
        )
        corr["top_token_agent"] = top["name"]
    tot_c = sum(s["quality"]["criteria_total"] for s in pts)
    tot_f = sum(s["quality"]["criteria_failed"] for s in pts)
    n_amb = sum(1 for s in pts for f in s["quality"]["failed"] if f["ambiguous"])
    data["criteria"] = {str(k): v for k, v in crit.items()}
    data["primary"] = {str(k): v for k, v in primary.items()}
    data["summary"] = dict(
        sessions=len(sessions), implementation_sessions=sum(1 for s in sessions if s["role"] == "implementation"),
        scored_agents=len(pts), criteria_total=tot_c, criteria_failed=tot_f, ambiguous_failures=n_amb,
        per_criterion_failure_rate_pct=round(100 * tot_f / tot_c, 1) if tot_c else None,
        mean_failed_pct=round(sum(fp) / len(fp), 1) if fp else None, correlation=corr, excluded_findings=excluded,
        sessions_with_missing_data=[dict(name=s["name"], issue=(
            "no model calls recorded in the session file or journal" if s["model_calls"] == 0 else
            f"{s['journal_messages']} messages exist only in the .journal.jsonl (merged in)" if s["journal_messages"] else
            "no postmortem")) for s in sessions if s["model_calls"] == 0 or s["journal_messages"] or not s["postmortem"]])
    print(json.dumps({k: v for k, v in data["summary"].items() if k not in ("excluded_findings", "sessions_with_missing_data", "correlation")}, indent=1))


def main():
    ap = args(__doc__)
    ap.add_argument("mode", nargs="?", default="score", choices=["score", "draft"])
    a = ap.parse_args()
    cfg = load_config(a.config)
    data = read_json(cfg, "data.json")
    tickets = sorted({s["ticket"] for s in data["sessions"] if s.get("ticket")})
    crit = {n: criteria(i) for n, i in issues(cfg, tickets).items() if n in tickets}
    if a.mode == "draft":
        return draft(cfg, crit)
    score(cfg, data, crit)
    write_json(cfg, "data.json", data)


if __name__ == "__main__":
    main()
