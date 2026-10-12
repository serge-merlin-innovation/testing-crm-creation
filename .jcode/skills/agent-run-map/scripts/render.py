"""Step 5: render the three outputs into <out_dir>.

  agent-run-map.html           columns layout, from templates/columns.template.html
  agent-run-map-timeline.html  timeline layout, from templates/timeline.template.html
  agent-run-token-vs-quality.md
      If the file is missing, it is created from templates/report.template.md.
      Every <!-- BEGIN:x --> ... <!-- END:x --> block is regenerated; the narrative between blocks is left alone.
"""
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import SKILL, args, esc_md, load_config, merger_scopes, no_pm_reason, read_json, tokens  # noqa: E402

COLOURS = {"blocks": "#64748b", "merged": "#2563eb", "findings": "#dc2626", "takeover": "#7c3aed", "extra": "#ca8a04"}
ARROW = {"blocks": "-->", "merged": "-.->", "findings": "==>", "takeover": "-.->", "extra": "-.->"}
GROUPS = [("g_tickets", "Tickets (dependency graph)", ("implementation",)), ("g_merge", "Mergers into {branch}", ("merger",)),
          ("g_rev", "Reviews", ("reviewer", "verifier")), ("g_fix", "Fixers", ("fixer",))]
STAT_ROWS = [("peak_context_vs_failed_pct", "Peak context vs failed %"), ("total_tokens_vs_failed_pct", "Total tokens vs failed %"),
             ("output_tokens_vs_failed_pct", "Output tokens vs failed %"), ("total_tokens_vs_criteria_total", "Total tokens vs criteria count (size check)"),
             ("peak_context_vs_criteria_failed_count", "Peak context vs failed count"),
             ("total_tokens_vs_failed_pct_without_top", "Total tokens vs failed %, without {top}"),
             ("peak_context_vs_failed_pct_without_top", "Peak context vs failed %, without {top}"),
             ("total_tokens_incl_takeovers_vs_failed_pct", "Total tokens incl. crashed/resumed attempts vs failed %")]


def mid(n):  # mermaid ids: letters, digits, underscore
    return re.sub(r"\W", "_", n)


def card_class(s):
    q = s.get("quality")
    if s["role"] == "coordinator":
        return "coord"
    if q and q.get("in_correlation"):
        p = q["failed_pct"]
        return "bad" if p >= 30 else "mid" if p >= 15 else "good"
    return "dead" if not s["ended_cleanly"] else "other"


def label(s):
    head = s["name"] + (f" · #{s['ticket']}" if s.get("ticket") else "")
    lines = [f"<b>{head}</b>", s["role"], f"{tokens(s['total_tokens'])} tok · peak {tokens(s['peak_context'])}"]
    q = s.get("quality")
    if q and q.get("in_correlation"):
        lines.append(f"failed {q['failed_pct']}% ({q['criteria_failed']}/{q['criteria_total']})")
    lines.append("📄 postmortem" if s.get("postmortem") else "no postmortem")
    return "<br/>".join(lines).replace('"', "'")


def mermaid(cfg, data, edges):
    S = {s["name"]: s for s in data["sessions"]}
    C = next(s["name"] for s in data["sessions"] if s["role"] == "coordinator")
    gh = cfg.get("postmortem_url")
    out = ["```mermaid", "flowchart LR", f'  {mid(C)}["{label(S[C])}"]:::coord']
    for gid, title, roles in GROUPS:
        names = [n for n in S if S[n]["role"] in roles]
        if not names:
            continue
        out += [f'  subgraph {gid}["{title.format(branch=cfg["branch"])}"]', "    direction LR"]
        for n in sorted(names, key=lambda n: (S[n].get("ticket") or 99, S[n]["created_at"])):
            out.append(f'    {mid(n)}["{label(S[n])}"]:::{card_class(S[n])}')
        out.append("  end")
    out.append(f"  {mid(C)} ==>|spawns all| g_tickets")
    for e in edges:
        lab = f"|{e['label']}|" if e["label"] and e["kind"] != "blocks" else ""
        out.append(f"  {mid(e['from'])} {ARROW[e['kind']]}{lab} {mid(e['to'])}")
    for i, e in enumerate(edges, start=1):
        out.append(f"  linkStyle {i} stroke:{COLOURS[e['kind']]}")
    for n, s in S.items():
        if s["peak_context"] > cfg["hot_context"]:
            out.append(f"  style {mid(n)} stroke:#c2410c,stroke-width:3px")
    for n, s in S.items():
        if s.get("postmortem"):
            url = gh + s["postmortem"] if gh else os.path.relpath(os.path.join(cfg["repo"], "postmortem", s["postmortem"]), cfg["out_dir"])
            out.append(f'  click {mid(n)} "{url}" "Postmortem of {n}" _blank')
    out += ["  classDef coord fill:#1e293b,color:#fff,stroke:#0f172a", "  classDef good fill:#dcfce7,stroke:#16a34a",
            "  classDef mid fill:#fef9c3,stroke:#ca8a04", "  classDef bad fill:#fee2e2,stroke:#dc2626",
            "  classDef dead fill:#e5e7eb,stroke:#6b7280,stroke-dasharray:4 3", "  classDef other fill:#f1f5f9,stroke:#64748b", "```"]
    return "\n".join(out)


def pm_link(cfg, s, short=False):
    if not s.get("postmortem"):
        return "none (" + (s.get("no_pm") or "none written") + ")"
    rel = os.path.relpath(os.path.join(cfg["repo"], "postmortem", s["postmortem"]), cfg["out_dir"])
    text = s["postmortem"][:15] + "…" if short else s["postmortem"]
    return f"[{text}]({rel})"


def blocks(cfg, data, ed):
    sm = data.get("summary") or {}
    S = data["sessions"]
    for s in S:
        s["no_pm"] = None if s.get("postmortem") else no_pm_reason(s)
    corr = sm.get("correlation") or {}
    top = corr.get("top_token_agent", "the top token user")
    rows = ["| Pair | n | Pearson r | p (two-sided) | Spearman ρ |", "|---|---|---|---|---|"]
    for k, t in STAT_ROWS:
        v = corr.get(k)
        if v:
            rows.append(f"| {t.format(top=top)} | {v['n']} | {v['pearson_r']:+.3f} | {v['p_two_sided']:.2f} | {v['spearman_rho']:+.3f} |")
    C = next(s for s in S if s["role"] == "coordinator")
    jn = sorted((s for s in S if s["journal_messages"]), key=lambda s: -s["journal_messages"])
    roles = {}
    for s in S:
        roles[s["role"]] = roles.get(s["role"], 0) + 1
    dead = [s["name"] for s in S if not s["ended_cleanly"]]
    unscored = [s["name"] for s in S if s["role"] == "implementation" and s.get("quality") and not s["quality"]["in_correlation"]]
    method = "\n\n".join([
        f"**Sessions.** Every `~/.jcode/sessions/session_*.json` created in the run window {data['window'][0][:16]} to {data['window'][1][:16]} UTC"
        + (f", with a working dir matching {', '.join('`' + g + '`' for g in cfg.get('working_dir_globs'))}" if cfg.get("working_dir_globs") else "")
        + f", that is either the coordinator `{C['id']}` or has it as `parent_id`. That gives {len(S)} sessions: "
        + ", ".join(f"{v} {k}" for k, v in roles.items()) + ". Messages appended to `session_*.journal.jsonl` after the last JSON snapshot are merged in by message id"
        + (": " + ", ".join(f"{s['name']} ({s['journal_messages']})" for s in jn[:6]) + "." if jn else "."),
        "**Token figures.** Summed over every message's `token_usage`: `input_tokens`, `output_tokens`, `cache_read_input_tokens`, "
        "`cache_creation_input_tokens`. Total = the sum of the four. Peak context = the largest `prompt_tokens` of any single model call. "
        "Model calls = messages carrying `token_usage`. Duration = `created_at` to the last message timestamp."
        + (f" The coordinator kept working after the run window; that later activity ({tokens(C['after_run']['total_tokens'])} tokens) is left out and kept in `after_run`." if C.get("after_run") else ""),
        "**Roles.** Read from each session's first user message (`Implement GitHub issue #N` = implementation for ticket N, "
        "`Merger task` = merger, `Fix …` = fixer, read-only review = reviewer, verification = verifier)."
        + (f" Sessions that ended without a report and without a final answer (crashed or killed): {', '.join(dead)}." if dead else ""),
        f"**Postmortems.** Read from each session's own tool calls (the `postmortem/*.md` it wrote or committed). {sum(1 for s in S if s.get('postmortem'))} sessions have one.",
        f"**Criteria.** Each ticket's criterion IDs come from `gh issue view N`: the \"User stories covered\" list (with explicit `(criteria …)` subsets) checked against the `- [ ]` lines under each story. That gives {sm.get('criteria_total')} criteria over {sm.get('scored_agents')} tickets.",
        f"**Scored agents.** One per ticket, the first session that built it." + (f" {', '.join(unscored)} are shown but not scored." if unscored else ""),
        "**Statistics.** Pearson r with a two-sided t-test p-value, plus Spearman ρ, over the scored agents. Computed in plain Python, no libraries.",
    ])
    pm = ["| Session | Role | Postmortem |", "|---|---|---|"]
    for s in sorted(S, key=lambda s: (["coordinator", "implementation", "merger", "reviewer", "fixer", "verifier", "other"].index(s["role"]), s.get("ticket") or 0, s["created_at"])):
        pm.append(f"| {s['name']}{' (#' + str(s['ticket']) + ')' if s.get('ticket') else ''} | {s['role']} | {pm_link(cfg, s)} |")
    ev = ["| From | To | Kind | Evidence |", "|---|---|---|---|"] + [f"| {e['from']} | {e['to']} | {e['kind']} | {esc_md(e['evidence'])} |" for e in ed["edges"]]
    if ed.get("unresolved"):
        ev += ["", "Not drawn:", ""] + [f"- {u}" for u in ed["unresolved"]]
    hot = cfg["hot_context"]
    ses = [f"Peak context over {tokens(hot)} is in bold. \"Failed first time\" = failed criteria / the ticket's criteria. Only one agent per ticket is scored.", "",
           "| Session | Role | Ticket / scope | Model | Input | Output | Cache read | Cache write | Peak context | Failed first time | Postmortem |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in S:
        q = s.get("quality")
        f = f"{q['failed_pct']}% ({q['criteria_failed']}/{q['criteria_total']})" if q and q.get("in_correlation") else ""
        pk = f"**{tokens(s['peak_context'])}**" if s["peak_context"] > hot else tokens(s["peak_context"])
        scope = f"#{s['ticket']}" if s.get("ticket") else esc_md(s.get("scope"))[:60]
        ses.append(f"| {s['name']} | {s['role']} | {scope} | {s.get('model')} | {tokens(s['input_tokens'])} | {tokens(s['output_tokens'])} | "
                   f"{tokens(s['cache_read_tokens'])} | {tokens(s['cache_creation_tokens'])} | {pk} | {f} | {pm_link(cfg, s, short=True)} |")
    fl = ["`*` = attribution ambiguous. The note for each one is in `data.json`.", ""]
    for s in sorted((s for s in S if s.get("quality") and s["quality"]["in_correlation"]), key=lambda s: s["ticket"]):
        q = s["quality"]
        items = ", ".join(f"{f['criterion']}{'*' if f['ambiguous'] else ''} ({'; '.join(x['source'].split(' (')[0] + ' ' + x['ref'] for x in f['sources'])})" for f in q["failed"]) or "none"
        fl.append(f"- **#{s['ticket']} {s['name']}**: {q['criteria_failed']}/{q['criteria_total']} = {q['failed_pct']}%. {items}")
    return dict(correlation="\n".join(rows), method=method, mermaid=mermaid(cfg, data, ed["edges"]), postmortems="\n".join(pm),
                edges="\n".join(ev), sessions="\n".join(ses), failed="\n".join(fl))


def report(cfg, data, ed):
    path = os.path.join(cfg["out_dir"], "agent-run-token-vs-quality.md")
    C = next(s for s in data["sessions"] if s["role"] == "coordinator")
    if os.path.exists(path):
        text = open(path).read()
    else:
        text = open(os.path.join(SKILL, "templates/report.template.md")).read()
        for k, v in dict(TITLE=cfg["title"], RUN_DATE=cfg.get("run_date", data["window"][0][:10]), COORDINATOR=C["name"],
                         N_CHILDREN=len(data["sessions"]) - 1, TODAY=date.today().isoformat(), BRANCH=cfg["branch"], HOT_K=tokens(cfg["hot_context"])).items():
            text = text.replace("{{" + k + "}}", str(v))
    for k, v in blocks(cfg, data, ed).items():
        text, n = re.subn(rf"<!-- BEGIN:{k} -->.*?<!-- END:{k} -->", lambda _: f"<!-- BEGIN:{k} -->\n{v}\n<!-- END:{k} -->", text, flags=re.S)
        if not n:
            print(f"warning: no BEGIN:{k} block in {path}; section not refreshed")
    open(path, "w").write(text)
    return path


def html(cfg, layout, template, out):
    g = read_json(cfg, f"graph-{layout}.json")
    t = open(os.path.join(SKILL, "templates", template)).read()
    title = cfg["title"].replace("&", "&amp;").replace("<", "&lt;")
    t = t.replace("__TITLE__", title).replace("__RUN_DATE__", cfg.get("run_date", "")).replace("__HOT_K__", tokens(cfg["hot_context"]))
    t = t.replace("__GRAPH__", json.dumps(g, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/"))
    path = os.path.join(cfg["out_dir"], out)
    open(path, "w").write(t)
    return path


def main():
    cfg = load_config(args(__doc__).parse_args().config)
    data = read_json(cfg, "data.json")
    ed = read_json(cfg, "edges.json")
    merger_scopes(data, ed, cfg["branch"])
    print(html(cfg, "columns", "columns.template.html", "agent-run-map.html"))
    print(html(cfg, "timeline", "timeline.template.html", "agent-run-map-timeline.html"))
    print(report(cfg, data, ed))


if __name__ == "__main__":
    main()
