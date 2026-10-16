#!/usr/bin/env python3
"""
Animated "Jet Runner" contribution card.

A small jet slowly sweeps left -> right under your contribution graph. The graph
opens up behind a glowing beam as the jet moves, and the jet shoots every active
day (each hit flashes and pops, then the day stays lit).

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
ROWS = 7
GRID_X = 48
GRID_Y = 108
GRID_H = ROWS * P - GAP
SHIP_Y = GRID_Y + GRID_H + 46
H = SHIP_Y + 58

COLORS = ["#161e2b", "#0e4c7a", "#1b74b5", "#2a9df4", "#5cc8ff"]
LEVELS = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}

# ---- timing (seconds) -- everything is intentionally slow and relaxed ----
START_DELAY = 0.6      # jet waits a moment before it starts
STEP = 0.16            # jet time per column (53 columns ~ 8.5 s)
SHOT_GAP = 0.42        # delay between bullets in one column (max)
SHOT_GAP_MIN = 0.10    # lower bound when the year is very busy
COL_PAUSE_IN = 0.15    # jet stops this long before firing
COL_PAUSE_OUT = 0.25   # ...and this long after the last bullet leaves
MAX_LOOP = 30.0        # busy years are sped up just enough to stay under this
BULLET_SPEED = 180.0   # px / second
LEAD = 26              # how far the glowing beam runs ahead of the jet
HOLD = 3.2             # finished graph stays visible this long
FADE = 0.7             # fade out before the loop restarts


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
            if c >= 49 and random.random() < 0.45:
                lvl = random.choice([1, 2, 3, 4])
            elif c < 49 and random.random() < 0.02:
                lvl = random.choice([1, 2])
            col.append((r, lvl, lvl))
        weeks.append(col)
    total = sum(d[2] for w in weeks for d in w)
    return weeks, total


def fmt(v):
    return f"{v:.4f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def norm(times, T):
    """Absolute times (s) -> non-decreasing keyTimes in [0, 1]."""
    kt, last = [], 0.0
    for t in times:
        n = min(1.0, max(last, t / T))
        kt.append(n)
        last = n
    kt[0], kt[-1] = 0.0, 1.0
    return kt


def key_times(times, T):
    return ";".join(f"{k:.5f}" for k in norm(times, T))


def anim(attr, values, times, T):
    return (
        f'<animate attributeName="{attr}" values="{";".join(fmt(v) for v in values)}" '
        f'keyTimes="{key_times(times, T)}" dur="{T:.3f}s" repeatCount="indefinite"/>'
    )


def build(weeks, total):
    cols = len(weeks)
    grid_w = cols * P - GAP
    W = GRID_X * 2 + grid_w
    right = W - GRID_X
    gun_y = SHIP_Y - 20  # bullets leave the jet here

    def cx(c):
        return GRID_X + c * P + CELL / 2

    # ---------------- schedule ----------------
    active_cols = sum(1 for w in weeks if any(d[1] > 0 for d in w))
    n_shots = sum(1 for w in weeks for d in w if d[1] > 0)
    # Quiet profiles run at the relaxed pace set above. Very busy years are sped
    # up just enough to keep one loop under MAX_LOOP seconds.
    fixed = START_DELAY + HOLD + FADE
    est = (fixed + cols * STEP + active_cols * (COL_PAUSE_IN + COL_PAUSE_OUT)
           + max(0, n_shots - active_cols) * SHOT_GAP_MIN)
    s = 1.0
    if est > MAX_LOOP:
        s = max(0.35, (MAX_LOOP - fixed) / (est - fixed))
    step, pin, pout = STEP * s, COL_PAUSE_IN * s, COL_PAUSE_OUT * s
    gap = SHOT_GAP
    if n_shots:
        spare = MAX_LOOP - (fixed + cols * step + active_cols * (pin + pout))
        gap = min(SHOT_GAP, max(SHOT_GAP_MIN * s, spare / n_shots))

    t = START_DELAY
    pts = [(0.0, cx(0))]          # (time, jet x)
    shots = []                    # (col, row, fire_t, hit_t)
    for c, week in enumerate(weeks):
        if c:
            t += step
        pts.append((t, cx(c)))
        active = sorted((d[0] for d in week if d[1] > 0), reverse=True)  # bottom first
        if active:
            t += pin
            for i, row in enumerate(active):
                ft = t + i * gap
                ty = GRID_Y + row * P + CELL
                shots.append((c, row, ft, ft + (gun_y - ty) / BULLET_SPEED))
            t += (len(active) - 1) * gap + pout
            pts.append((t, cx(c)))
    sweep_end = t
    T = sweep_end + HOLD + FADE
    pts.append((T, cx(cols - 1)))
    p_times = [tt for tt, _ in pts]

    def pts_anim(attr, fn):
        return anim(attr, [fn(x) for _, x in pts], p_times, T)

    reveal_x0 = GRID_X - 2
    full_w = grid_w + 4
    beam_max = GRID_X + grid_w + 2

    out = []
    a = out.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
      f'role="img" aria-label="Contribution activity - a jet shoots the active days">')
    a(f"""<defs>
<clipPath id="card"><rect x="6" y="6" width="{W - 12}" height="{H - 12}" rx="22"/></clipPath>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#0a0f15"/><stop offset="1" stop-color="#0b1a22"/></linearGradient>
<radialGradient id="gBlue"><stop offset="0" stop-color="#2a9df4" stop-opacity=".38"/><stop offset="1" stop-color="#2a9df4" stop-opacity="0"/></radialGradient>
<radialGradient id="gGreen"><stop offset="0" stop-color="#2ecc71" stop-opacity=".24"/><stop offset="1" stop-color="#2ecc71" stop-opacity="0"/></radialGradient>
<radialGradient id="gPurple"><stop offset="0" stop-color="#8a5cf5" stop-opacity=".30"/><stop offset="1" stop-color="#8a5cf5" stop-opacity="0"/></radialGradient>
<radialGradient id="gTeal"><stop offset="0" stop-color="#19c3c3" stop-opacity=".32"/><stop offset="1" stop-color="#19c3c3" stop-opacity="0"/></radialGradient>
<linearGradient id="beamV" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#7fdcff" stop-opacity="0"/><stop offset=".5" stop-color="#b4efff"/><stop offset="1" stop-color="#7fdcff" stop-opacity="0"/></linearGradient>
<linearGradient id="beamH" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="#2a9df4" stop-opacity="0"/><stop offset=".5" stop-color="#2a9df4" stop-opacity=".38"/><stop offset="1" stop-color="#2a9df4" stop-opacity="0"/></linearGradient>
<filter id="glow" x="-300%" y="-100%" width="700%" height="300%">
<feGaussianBlur stdDeviation="2" result="b"/>
<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>""")
    a(f'<clipPath id="reveal"><rect x="{reveal_x0}" y="{GRID_Y - 6}" height="{GRID_H + 12}" width="{full_w}">')
    a(pts_anim("width", lambda x: max(0.0, min(full_w, x + LEAD - reveal_x0))))
    a("</rect></clipPath></defs>")

    # ---------------- card ----------------
    a('<g clip-path="url(#card)">')
    a(f'<rect width="{W}" height="{H}" fill="url(#bg)"/>')
    a(f'<circle cx="{fmt(W * 0.18)}" cy="40" r="190" fill="url(#gBlue)"/>')
    a(f'<circle cx="{fmt(W * 0.78)}" cy="14" r="160" fill="url(#gGreen)"/>')
    a(f'<circle cx="{fmt(W * 0.60)}" cy="{H}" r="190" fill="url(#gPurple)"/>')
    a(f'<circle cx="{W - 24}" cy="{fmt(H * 0.78)}" r="160" fill="url(#gTeal)"/>')
    a("</g>")
    a(f'<rect x="6" y="6" width="{W - 12}" height="{H - 12}" rx="22" fill="none" '
      f'stroke="#1f6fa8" stroke-opacity=".55" stroke-width="1.5"/>')
    a(f'<rect x="28" y="28" width="{W - 56}" height="{SHIP_Y + 30 - 28}" rx="16" fill="#04080c" '
      f'fill-opacity=".38" stroke="#1f6fa8" stroke-opacity=".5" stroke-width="1.2"/>')

    font = "Segoe UI, Ubuntu, Helvetica, Arial, sans-serif"
    a(f'<text x="{GRID_X}" y="70" font-family="{font}" font-size="24" font-weight="700" fill="#f2f8ff">'
      f'Contribution Activity</text>')
    a(f'<text x="{GRID_X}" y="92" font-family="{font}" font-size="13" font-weight="600" fill="#7d93a8">'
      f'{total} contributions in the last year</text>')

    # legend
    sq_right = right - 34
    first_sq = sq_right - 5 * P + GAP
    a(f'<text x="{right}" y="70" text-anchor="end" font-family="{font}" font-size="11" fill="#8aa0b5">More</text>')
    for i, col in enumerate(COLORS):
        a(f'<rect x="{first_sq + i * P}" y="61" width="{CELL}" height="{CELL}" rx="2.5" fill="{col}"/>')
    a(f'<text x="{first_sq - 7}" y="70" text-anchor="end" font-family="{font}" font-size="11" fill="#8aa0b5">Less</text>')

    # ---------------- animated layer (fades in / out around each loop) ----------------
    a("<g>")
    a(anim("opacity", [0, 1, 1, 0], [0, 0.5, T - FADE, T], T))

    # grid, opened by the beam
    a('<g clip-path="url(#reveal)">')
    for c, week in enumerate(weeks):
        for (row, lvl, _n) in week:
            a(f'<rect x="{GRID_X + c * P}" y="{GRID_Y + row * P}" width="{CELL}" height="{CELL}" '
              f'rx="2.5" fill="{COLORS[lvl]}"/>')
    a("</g>")

    # hits + bullets
    for c, row, f, h in shots:
        x = cx(c)
        cy = GRID_Y + row * P + CELL / 2
        ty = GRID_Y + row * P + CELL
        a(f'<rect x="{GRID_X + c * P}" y="{GRID_Y + row * P}" width="{CELL}" height="{CELL}" rx="2.5" '
          f'fill="#e6f7ff" opacity="0">')
        a(anim("opacity", [0, 0, 0.95, 0, 0], [0, h - 0.01, h, h + 0.4, T], T))
        a("</rect>")
        a(f'<circle cx="{fmt(x)}" cy="{fmt(cy)}" r="3" fill="none" stroke="#8fe0ff" stroke-width="1.5" opacity="0">')
        a(anim("r", [3, 3, 15, 15], [0, h, h + 0.55, T], T))
        a(anim("opacity", [0, 0, 0.9, 0, 0], [0, h - 0.01, h, h + 0.55, T], T))
        a("</circle>")
        a(f'<rect x="{fmt(x - 1.5)}" y="{gun_y}" width="3" height="9" rx="1.5" fill="#8fe0ff" '
          f'filter="url(#glow)" opacity="0">')
        a(anim("y", [gun_y, gun_y, ty, ty], [0, f, h, T], T))
        a(anim("opacity", [0, 0, 1, 1, 0, 0], [0, f - 0.01, f, h, h + 0.01, T], T))
        a("</rect>")

    # glowing beam that opens the graph
    beam_h = GRID_H + 12
    a(f'<rect y="{GRID_Y - 6}" width="16" height="{beam_h}" fill="url(#beamH)" opacity="1">')
    a(pts_anim("x", lambda x: min(x + LEAD, beam_max) - 8))
    a(anim("opacity", [1, 1, 0, 0], [0, sweep_end, sweep_end + 0.5, T], T))
    a("</rect>")
    a(f'<rect y="{GRID_Y - 6}" width="2" height="{beam_h}" rx="1" fill="url(#beamV)" opacity="1">')
    a(pts_anim("x", lambda x: min(x + LEAD, beam_max) - 1))
    a(anim("opacity", [1, 1, 0, 0], [0, sweep_end, sweep_end + 0.5, T], T))
    a("</rect>")

    # jet
    vals = ";".join(f"{fmt(x)},{SHIP_Y}" for _, x in pts)
    a(f'<g transform="translate({fmt(cx(0))},{SHIP_Y})">')
    a(f'<animateTransform attributeName="transform" type="translate" values="{vals}" '
      f'keyTimes="{key_times(p_times, T)}" dur="{T:.3f}s" repeatCount="indefinite"/>')
    a('<g transform="scale(1.1)" filter="url(#glow)">')
    a('<path d="M0 -16 L5 -4 L12 8 L6 6 L3 12 L-3 12 L-6 6 L-12 8 L-5 -4 Z" fill="#e8f6ff" '
      'stroke="#2a9df4" stroke-width="1.5" stroke-linejoin="round"/>')
    a('<path d="M0 -9 L2.5 -2 L-2.5 -2 Z" fill="#2a9df4"/>')
    a('<path d="M-2 12 L0 20 L2 12 Z" fill="#5cc8ff">'
      '<animate attributeName="opacity" values="1;.3;1" dur=".3s" repeatCount="indefinite"/></path>')
    a("</g></g>")

    a("</g></svg>")
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
