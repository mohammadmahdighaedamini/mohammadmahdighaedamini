#!/usr/bin/env python3
"""
Generates an animated SVG: a retro spaceship sweeps left -> right under your
GitHub contribution graph and shoots every active day.

Usage:
  GITHUB_TOKEN=... GITHUB_USER=yourname python generate_ship.py   # real data
  python generate_ship.py --demo                                  # fake data
Output: assets/contrib-ship.svg
"""
import json
import os
import random
import sys
import urllib.request

OUT = "assets/contrib-ship.svg"

CELL, GAP = 10, 3
P = CELL + GAP
PAD_X = 28
GRID_Y = 84
ROWS = 7
SHIP_Y = GRID_Y + ROWS * P + 46
H = SHIP_Y + 46

COLORS = ["#161e2b", "#0e4c7a", "#1b74b5", "#2a9df4", "#5cc8ff"]
LEVELS = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}

# timing (seconds)
INTRO = 0.9        # grid wipes in from the left while the ship waits
STEP = 0.07        # ship time per empty column
FIRE_GAP = 0.16    # delay between bullets in one column
BULLET_SPEED = 420.0
HOLD = 1.8         # pause at the end before looping


def fetch(user, token):
    query = """query($login:String!){user(login:$login){contributionsCollection{
    contributionCalendar{totalContributions weeks{contributionDays{
    contributionLevel contributionCount weekday}}}}}}"""
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": user}}).encode(),
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "contrib-ship",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    weeks = []
    for w in cal["weeks"]:
        weeks.append(
            [(d["weekday"], LEVELS.get(d["contributionLevel"], 0), d["contributionCount"])
             for d in w["contributionDays"]]
        )
    return weeks, cal["totalContributions"]


def demo():
    random.seed(7)
    weeks = []
    for c in range(53):
        col = []
        for r in range(7):
            lvl = 0
            if c >= 50 and random.random() < 0.55:
                lvl = random.choice([1, 2, 3, 4])
            elif c < 50 and random.random() < 0.03:
                lvl = random.choice([1, 2])
            col.append((r, lvl, lvl))
        weeks.append(col)
    total = sum(d[2] for w in weeks for d in w)
    return weeks, total


def fmt(v):
    return f"{v:.4f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def anim(attr, values, times, T, extra=""):
    """<animate> with absolute times (seconds) normalised to keyTimes."""
    kt, last = [], 0.0
    for t in times:
        n = min(1.0, max(last, t / T))
        kt.append(n)
        last = n
    kt[0], kt[-1] = 0.0, 1.0
    return (
        f'<animate attributeName="{attr}" values="{";".join(fmt(v) for v in values)}" '
        f'keyTimes="{";".join(f"{k:.5f}" for k in kt)}" dur="{T:.3f}s" '
        f'repeatCount="indefinite" {extra}/>'
    )


def build(weeks, total):
    cols = len(weeks)
    grid_w = cols * P - GAP
    W = grid_w + PAD_X * 2

    def cx(c):
        return PAD_X + c * P + CELL / 2

    # ---------- schedule ----------
    t = INTRO
    ship_pts = [(0.0, cx(0)), (INTRO, cx(0))]
    shots = []  # (col, row, fire_t, hit_t)
    for c, week in enumerate(weeks):
        t += STEP
        ship_pts.append((t, cx(c)))
        active = sorted([d[0] for d in week if d[1] > 0], reverse=True)  # bottom first
        if active:
            for i, row in enumerate(active):
                ft = t + 0.05 + i * FIRE_GAP
                ty = GRID_Y + row * P + CELL
                dist = (SHIP_Y - 16) - ty
                shots.append((c, row, ft, ft + dist / BULLET_SPEED))
            t = t + 0.05 + (len(active) - 1) * FIRE_GAP + 0.12
            ship_pts.append((t, cx(c)))
    T = t + HOLD
    ship_pts.append((T - 0.35, ship_pts[-1][1]))
    ship_pts.append((T, cx(0)))
    hits = {(c, r): h for c, r, f, h in shots}

    out = []
    a = out.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
      f'aria-label="Contribution activity, shot by a spaceship">')
    a("""<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#0b1118"/><stop offset="1" stop-color="#0d1c26"/></linearGradient>
<filter id="glow" x="-100%" y="-100%" width="300%" height="300%">
<feGaussianBlur stdDeviation="2.2" result="b"/>
<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>""")
    a(f'<clipPath id="reveal"><rect x="{PAD_X - 2}" y="{GRID_Y - 4}" height="{ROWS * P + 8}" width="{grid_w + 4}">')
    a(anim("width", [0, grid_w + 4, grid_w + 4], [0, INTRO - 0.1, T], T))
    a("</rect></clipPath></defs>")

    a(f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="18" fill="url(#bg)" '
      f'stroke="#1f6fa8" stroke-opacity=".7" stroke-width="1.5"/>')
    a(f'<text x="{PAD_X}" y="40" font-family="Segoe UI, Ubuntu, Helvetica, Arial, sans-serif" '
      f'font-size="22" font-weight="700" fill="#f2f8ff">Contribution Activity</text>')
    a(f'<text x="{PAD_X}" y="62" font-family="Segoe UI, Ubuntu, Helvetica, Arial, sans-serif" '
      f'font-size="12" font-weight="600" fill="#7d93a8">{total} contributions in the last year</text>')

    # legend
    lx = W - PAD_X - 5 * 13 - 62 - 34
    a(f'<text x="{lx}" y="40" font-family="Segoe UI, Arial, sans-serif" font-size="10" fill="#8aa0b5">Less</text>')
    for i, col in enumerate(COLORS):
        a(f'<rect x="{lx + 28 + i * 13}" y="31" width="{CELL}" height="{CELL}" rx="2" fill="{col}"/>')
    a(f'<text x="{lx + 28 + 5 * 13 + 4}" y="40" font-family="Segoe UI, Arial, sans-serif" font-size="10" fill="#8aa0b5">More</text>')

    # cells
    a('<g clip-path="url(#reveal)">')
    for c, week in enumerate(weeks):
        for (row, lvl, _cnt) in week:
            x, y = PAD_X + c * P, GRID_Y + row * P
            a(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2.5" fill="{COLORS[lvl]}">')
            h = hits.get((c, row))
            if h is not None:
                a(anim("opacity", [1, 1, 0, 0, 1, 1],
                       [0, h, h + 0.12, T - 0.55, T - 0.25, T], T))
            a("</rect>")
    a("</g>")

    # explosions + bullets
    for c, row, f, h in shots:
        x, ty = cx(c), GRID_Y + row * P + CELL
        cy = GRID_Y + row * P + CELL / 2
        a(f'<circle cx="{fmt(x)}" cy="{fmt(cy)}" r="0" fill="#aee6ff" opacity="0">')
        a(anim("r", [0, 0, 9, 9], [0, h, h + 0.25, T], T))
        a(anim("opacity", [0, 0, 0.9, 0, 0], [0, h - 0.01, h, h + 0.25, T], T))
        a("</circle>")
        y0 = SHIP_Y - 16
        a(f'<rect x="{fmt(x - 1.5)}" y="{y0}" width="3" height="9" rx="1.5" fill="#8fe0ff" '
          f'filter="url(#glow)" opacity="0">')
        a(anim("y", [y0, y0, ty, ty], [0, f, h, T], T))
        a(anim("opacity", [0, 0, 1, 1, 0, 0], [0, f - 0.01, f, h, h + 0.01, T], T))
        a("</rect>")

    # ship
    a(f'<g transform="translate({fmt(cx(0))},{SHIP_Y})">')
    vals = [f"{fmt(x)},{SHIP_Y}" for _, x in ship_pts]
    kt, last = [], 0.0
    for tt, _ in ship_pts:
        n = min(1.0, max(last, tt / T))
        kt.append(n)
        last = n
    kt[0], kt[-1] = 0.0, 1.0
    a(f'<animateTransform attributeName="transform" type="translate" values="{";".join(vals)}" '
      f'keyTimes="{";".join(f"{k:.5f}" for k in kt)}" dur="{T:.3f}s" repeatCount="indefinite"/>')
    a('<g filter="url(#glow)">')
    a('<path d="M0 -16 L5 -4 L12 8 L6 6 L3 12 L-3 12 L-6 6 L-12 8 L-5 -4 Z" fill="#dff4ff" stroke="#2a9df4" stroke-width="1.5" stroke-linejoin="round"/>')
    a('<path d="M0 -9 L2.5 -2 L-2.5 -2 Z" fill="#2a9df4"/>')
    a('<path d="M-2 12 L0 20 L2 12 Z" fill="#5cc8ff"><animate attributeName="opacity" values="1;.3;1" dur=".25s" repeatCount="indefinite"/></path>')
    a("</g></g></svg>")
    return "\n".join(out)


def main():
    if "--demo" in sys.argv:
        weeks, total = demo()
    else:
        user = os.environ.get("GITHUB_USER")
        token = os.environ.get("GITHUB_TOKEN")
        if not user or not token:
            sys.exit("Set GITHUB_USER and GITHUB_TOKEN, or run with --demo")
        weeks, total = fetch(user, token)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(build(weeks, total))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
