"""Step 4b: timeline layout -> <work_dir>/graph-timeline.json.

Time runs left to right: each session sits one step after the sessions it waited on (blocked by, merged,
reviewed, taken over). One horizontal lane per agent type; inside a cell, cards stack by ticket then start.
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import LANES, args, graph_base, lane_of, load_config, time_steps, write_json  # noqa: E402

CARD_W, CARD_H, COL_GAP, ROW_GAP, LANE_GAP, LABEL_W, TOP = 210, 112, 110, 36, 72, 150, 30


def main():
    cfg = load_config(args(__doc__).parse_args().config)
    g = graph_base(cfg)
    nodes = {n["name"]: n for n in g["nodes"]}
    step = time_steps(nodes, g["edges"], g["coordinator"])
    cells = defaultdict(list)
    for n in nodes:
        cells[(lane_of(nodes[n]["role"]), step[n])].append(n)
    rows = [max([len(v) for (l, _), v in cells.items() if l == i] or [1]) for i in range(len(LANES))]
    lane_y, y = [], TOP
    for r in rows:
        lane_y.append(y)
        y += r * CARD_H + (r - 1) * ROW_GAP + LANE_GAP
    layout = {}
    for (lane, st), names in cells.items():
        for j, n in enumerate(sorted(names, key=lambda n: (nodes[n].get("ticket") or 0, nodes[n]["created_at"]))):
            layout[n] = {"x": LABEL_W + st * (CARD_W + COL_GAP), "y": lane_y[lane] + j * (CARD_H + ROW_GAP)}
    last = max(step.values())
    h = lane_y[-1] + rows[-1] * CARD_H + (rows[-1] - 1) * ROW_GAP + TOP
    g.update(layout=layout, lanes=[{"title": LANES[i][1], "y": lane_y[i], "h": rows[i] * CARD_H + (rows[i] - 1) * ROW_GAP} for i in range(len(LANES))],
             size={"w": LABEL_W + last * (CARD_W + COL_GAP) + CARD_W + COL_GAP, "h": h, "card_w": CARD_W, "card_h": CARD_H,
                   "col_gap": COL_GAP, "row_gap": ROW_GAP, "lane_gap": LANE_GAP, "label_w": LABEL_W})
    write_json(cfg, "graph-timeline.json", g)
    print("steps", last + 1, "lanes", {LANES[i][1]: rows[i] for i in range(len(LANES))}, "size", g["size"]["w"], "x", g["size"]["h"])


if __name__ == "__main__":
    main()
