"""Step 4a: column layout -> <work_dir>/graph-columns.json.

One column per agent type (coordinator, tickets, mergers, reviews, fixers). Inside a column, cards follow
the run's order (time step, then ticket, then start time), and each column is centred on one shared
horizontal mid-line.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import LANES, args, graph_base, lane_of, load_config, time_steps, write_json  # noqa: E402

CARD_W, CARD_H, ROW_GAP = 230, 98, 22
GAPS = [160, 420, 300, 300]  # between columns; the tickets->mergers gap carries the most wires
TOP, HEAD = 20, 34


def main():
    cfg = load_config(args(__doc__).parse_args().config)
    g = graph_base(cfg)
    nodes = {n["name"]: n for n in g["nodes"]}
    step = time_steps(nodes, g["edges"], g["coordinator"])
    columns = {i: sorted((n for n in nodes if lane_of(nodes[n]["role"]) == i),
                         key=lambda n: (step[n], nodes[n].get("ticket") or 0, nodes[n]["created_at"])) for i in range(len(LANES))}
    tallest = max(len(c) for c in columns.values())
    col_h = lambda k: k * CARD_H + (k - 1) * ROW_GAP  # noqa: E731
    body_h = col_h(tallest)
    mid = TOP + HEAD + body_h / 2
    col_x = [30]
    for gap in GAPS[: len(LANES) - 1]:
        col_x.append(col_x[-1] + CARD_W + gap)
    layout = {}
    for i, names in columns.items():
        y0 = mid - col_h(len(names)) / 2
        for j, n in enumerate(names):
            layout[n] = {"x": col_x[i], "y": round(y0 + j * (CARD_H + ROW_GAP)), "col": i}
    g.update(layout=layout, lanes=[], columns=[{"title": LANES[i][1], "x": col_x[i]} for i in range(len(LANES))],
             size={"w": col_x[-1] + CARD_W + 120, "h": TOP + HEAD + body_h + 40, "card_w": CARD_W, "card_h": CARD_H, "row_gap": ROW_GAP,
                   "col_x": col_x, "gaps": GAPS, "mid": mid, "head": HEAD, "top": TOP})
    write_json(cfg, "graph-columns.json", g)
    print("columns", {LANES[i][1]: len(c) for i, c in columns.items()}, "size", g["size"]["w"], "x", g["size"]["h"])


if __name__ == "__main__":
    main()
