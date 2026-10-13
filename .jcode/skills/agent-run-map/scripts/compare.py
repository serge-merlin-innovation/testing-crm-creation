"""Optional: compare a fresh run of the skill against an earlier, committed output.

  compare.py --config run.json --ref-dir docs/research [--ref-data old/data.json]

Reads the graph embedded in <ref-dir>/agent-run-map-timeline.html (and optionally an older data.json), then prints
every difference in sessions, per-session tokens, failed % per ticket, and the edge set.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import args, expand, load_config, read_json  # noqa: E402


def embedded_graph(path):
    s = open(path).read()
    i = s.index("const G = ") + len("const G = ")
    return json.loads(s[i: s.index("\n", i)].rstrip().rstrip(";"))


def main():
    ap = args(__doc__)
    ap.add_argument("--ref-dir", required=True)
    ap.add_argument("--ref-data")
    a = ap.parse_args()
    cfg = load_config(a.config)
    data, ed = read_json(cfg, "data.json"), read_json(cfg, "edges.json")
    ref = embedded_graph(os.path.join(expand(a.ref_dir), "agent-run-map-timeline.html"))
    new = {s["name"]: s for s in data["sessions"]}
    old = {n["name"]: n for n in ref["nodes"]}
    print(f"sessions: new {len(new)}, ref {len(old)}; only new {sorted(set(new) - set(old))}; only ref {sorted(set(old) - set(new))}")
    keys = ["total_tokens", "peak_context", "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens", "model_calls"]
    tok = [(n, k, old[n][k], new[n][k]) for n in old if n in new for k in keys if old[n].get(k) != new[n][k]]
    print(f"token fields differing: {len(tok)}", *[f"  {t}" for t in tok], sep="\n")
    if a.ref_data:
        od = {s["name"]: s for s in json.load(open(expand(a.ref_data)))["sessions"]}
        tok2 = [(n, k) for n in od if n in new for k in keys + ["messages", "duration_min"] if od[n].get(k) != new[n].get(k)]
        print(f"vs ref data.json, fields differing: {len(tok2)}", *[f"  {t}" for t in tok2], sep="\n")
    fp = []
    for n, o in old.items():
        oq = o.get("quality")
        nq = (new.get(n) or {}).get("quality")
        a_ = oq and oq.get("scored") and (oq["pct"], oq["failed"], oq["total"])
        b_ = nq and nq.get("in_correlation") and (nq["failed_pct"], nq["criteria_failed"], nq["criteria_total"])
        if (a_ or None) != (b_ or None):
            fp.append((n, a_, b_))
    print(f"failed % differing: {len(fp)}", *[f"  {t}" for t in fp], sep="\n")
    k = lambda e: (e["from"], e["to"], e["kind"])  # noqa: E731
    A, B = {k(e): e for e in ref["edges"]}, {k(e): e for e in ed["edges"]}
    print(f"edges: new {len(B)}, ref {len(A)}, shared {len(set(A) & set(B))}")
    for x in sorted(set(A) - set(B)):
        print(f"  only ref:  {x} {A[x]['label']!r}")
    for x in sorted(set(B) - set(A)):
        print(f"  only new:  {x} {B[x]['label']!r}  <- {B[x]['evidence'][:120]}")
    for x in sorted(set(A) & set(B)):
        if A[x]["label"] != B[x]["label"]:
            print(f"  label:     {x} {A[x]['label']!r} -> {B[x]['label']!r}")


if __name__ == "__main__":
    main()
