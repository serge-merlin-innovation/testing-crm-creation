"""Step 6: render the one output into <out_dir>.

  agent-run-map-timeline.html  timeline layout, from templates/timeline.template.html
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import SKILL, args, load_config, read_json, tokens  # noqa: E402


def html(cfg, layout, template, out):
    g = read_json(cfg, f"graph-{layout}.json")
    t = open(os.path.join(SKILL, "templates", template)).read()
    title = cfg["title"].replace("&", "&amp;").replace("<", "&lt;")
    t = t.replace("__TITLE__", title).replace("__RUN_DATE__", cfg.get("run_date", "")).replace("__HOT_K__", tokens(cfg["hot_context"]))
    t = t.replace("__GRAPH__", json.dumps(g, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/"))
    os.makedirs(cfg["out_dir"], exist_ok=True)
    path = os.path.join(cfg["out_dir"], out)
    open(path, "w").write(t)
    return path


def main():
    cfg = load_config(args(__doc__).parse_args().config)
    print(html(cfg, "timeline", "timeline.template.html", "agent-run-map-timeline.html"))


if __name__ == "__main__":
    main()
