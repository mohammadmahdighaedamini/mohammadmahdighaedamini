#!/usr/bin/env python3
"""
Animated "Jet Runner" contribution card, themed after the Nightmare neon banner
(pink -> purple -> blue on a dark maroon / navy background).

- A glowing beam sweeps quickly left -> right and opens the contribution graph.
- Each column of days lifts up in 3D as the beam passes, then lands and stays still.
- A small jet slowly flies left -> right underneath and shoots every active day.

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

# ---- palette: sampled from the banner, pink -> purple -> blue ----
STOPS = [(0.0, "#ff4fb8"), (0.35, "#c04ee8"), (0.65, "#7a5cf5"), (1.0, "#1f6bff")]
BASE_DARK = "#0c0614"                       # what an empty day fades into
INTENSITY = [0.16, 0.40, 0.60, 0.80, 1.0]   # contribution level 0..4

LEVELS = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}

# ---- timing (seconds) ----
START_DELAY = 0.6      # beam and jet both wait a moment before they start
BEAM_STEP = 0.05       # beam time per column (53 columns ~ 2.7 s) -- fast
LIFT_X, LIFT_Y = 2.5, 5.0   # how far a column floats up before it lands
LAND = 0.55            # time to come down
SETTLE = 0.25          # tiny soft overshoot, then still
STEP = 0.16            # jet time per column (53 columns ~ 8.5 s) -- slow
SHOT_GAP = 0.42        # delay between bullets in one column (max)
SHOT_GAP_MIN = 0.10    # lower bound when the year is very busy
COL_PAUSE_IN = 0.15    # jet stops this long before firing
COL_PAUSE_OUT = 0.25   # ...and this long after the last bullet leaves
MAX_LOOP = 30.0        # busy years are sped up just enough to stay under this
BULLET_SPEED = 180.0   # px / second
HOLD = 3.2             # finished graph stays visible this long
FADE = 0.7             # fade out before the loop restarts


# ---------------- colour helpers ----------------
def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in c)


def _mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def grad(u):
    u = max(0.0, min(1.0, u))
    for (u0, c0), (u1, c1) in zip(STOPS, STOPS[1:]):
        if u <= u1:
            return _mix(_rgb(c0), _rgb(c1), (u - u0) / (u1 - u0))
    return _rgb(STOPS[-1][1])


def cell_color(c, lvl, cols):
    """Colour follows the banner gradient across the graph; level sets the brightness."""
    u = c / max(1, cols - 1)
    return _hex(_mix(_rgb(BASE_DARK), grad(u), INTENSITY[lvl]))


def back_color(c, lvl, cols):
    return _hex(_mix(_rgb(cell_color(c, lvl, cols)), (0, 0, 0), 0.5))


def stops_xml(opacity=None):
    op = "" if opacity is None else f' stop-opacity="{opacity}"'
    return "".join(f'<stop offset="{u}" stop-color="{c}"{op}/>' for u, c in STOPS)


# ---------------- data ----------------
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


# ---------------- svg helpers ----------------
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

    # ---------------- jet schedule ----------------
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

    # ---------------- beam schedule (independent of the jet, much faster) ----------------
    reveal_x0 = GRID_X - 2
    full_w = grid_w + 4
    beam_dur = cols * BEAM_STEP
    beam_end = START_DELAY + beam_dur

    def t_beam(c):
        return START_DELAY + beam_dur * (GRID_X + c * P - reveal_x0) / full_w

    beam_times = [0, START_DELAY, beam_end, T]

    out = []
    a = out.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
      f'role="img" aria-label="Contribution activity - a jet shoots the active days">')
    a(f"""<defs>
<clipPath id="card"><rect x="6" y="6" width="{W - 12}" height="{H - 12}" rx="22"/></clipPath>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="#1d0316"/><stop offset=".45" stop-color="#0d0618"/><stop offset="1" stop-color="#04061a"/></linearGradient>
<radialGradient id="gPink"><stop offset="0" stop-color="#ff3fa8" stop-opacity=".30"/><stop offset="1" stop-color="#ff3fa8" stop-opacity="0"/></radialGradient>
<radialGradient id="gViolet"><stop offset="0" stop-color="#a24ff0" stop-opacity=".18"/><stop offset="1" stop-color="#a24ff0" stop-opacity="0"/></radialGradient>
<radialGradient id="gBlue"><stop offset="0" stop-color="#2563ff" stop-opacity=".28"/><stop offset="1" stop-color="#2563ff" stop-opacity="0"/></radialGradient>
<linearGradient id="frame" x1="0" y1="0" x2="1" y2="0">{stops_xml()}</linearGradient>
<linearGradient id="titleGrad" gradientUnits="userSpaceOnUse" x1="{GRID_X}" y1="0" x2="{GRID_X + 270}" y2="0">{stops_xml()}</linearGradient>
<linearGradient id="beamV" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#ff9be0" stop-opacity="0"/><stop offset=".5" stop-color="#f6e3ff"/><stop offset="1" stop-color="#9ab6ff" stop-opacity="0"/></linearGradient>
<linearGradient id="beamH" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="#c04ee8" stop-opacity="0"/><stop offset=".5" stop-color="#c04ee8" stop-opacity=".42"/><stop offset="1" stop-color="#c04ee8" stop-opacity="0"/></linearGradient>
<filter id="glow" x="-300%" y="-100%" width="700%" height="300%">
<feGaussianBlur stdDeviation="2" result="b"/>
<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>""")
    a(f'<clipPath id="reveal"><rect x="{reveal_x0}" y="{GRID_Y - 12}" height="{GRID_H + 24}" width="{full_w}">')
    a(anim("width", [0, 0, full_w, full_w], beam_times, T))
    a("</rect></clipPath></defs>")

    # ---------------- card ----------------
    a('<g clip-path="url(#card)">')
    a(f'<rect width="{W}" height="{H}" fill="url(#bg)"/>')
    a(f'<circle cx="{fmt(W * 0.12)}" cy="{fmt(H * 0.92)}" r="240" fill="url(#gPink)"/>')
    a(f'<circle cx="{fmt(W * 0.45)}" cy="0" r="210" fill="url(#gViolet)"/>')
    a(f'<circle cx="{fmt(W * 0.92)}" cy="{fmt(H * 0.28)}" r="240" fill="url(#gBlue)"/>')
    a(f'<circle cx="{fmt(W * 0.78)}" cy="{H}" r="170" fill="url(#gBlue)" opacity=".5"/>')
    a("</g>")
    a(f'<rect x="6" y="6" width="{W - 12}" height="{H - 12}" rx="22" fill="none" '
      f'stroke="url(#frame)" stroke-opacity=".65" stroke-width="1.5"/>')
    a(f'<rect x="28" y="28" width="{W - 56}" height="{SHIP_Y + 30 - 28}" rx="16" fill="#07030f" '
      f'fill-opacity=".45" stroke="url(#frame)" stroke-opacity=".4" stroke-width="1.2"/>')

    font = "Segoe UI, Ubuntu, Helvetica, Arial, sans-serif"
    a(f'<text x="{GRID_X}" y="70" font-family="{font}" font-size="24" font-weight="700" '
      f'fill="url(#titleGrad)">Contribution Activity</text>')
    a(f'<text x="{GRID_X}" y="92" font-family="{font}" font-size="13" font-weight="600" fill="#a58fc4">'
      f'{total} contributions in the last year</text>')

    # legend
    sq_right = right - 34
    first_sq = sq_right - 5 * P + GAP
    mid = grad(0.5)
    a(f'<text x="{right}" y="70" text-anchor="end" font-family="{font}" font-size="11" fill="#a58fc4">More</text>')
    for i in range(5):
        col = _hex(_mix(_rgb(BASE_DARK), mid, INTENSITY[i]))
        a(f'<rect x="{first_sq + i * P}" y="61" width="{CELL}" height="{CELL}" rx="2.5" fill="{col}"/>')
    a(f'<text x="{first_sq - 7}" y="70" text-anchor="end" font-family="{font}" font-size="11" fill="#a58fc4">Less</text>')

    # ---------------- animated layer (fades in / out around each loop) ----------------
    a("<g>")
    a(anim("opacity", [0, 1, 1, 0], [0, 0.5, T - FADE, T], T))

    a('<g clip-path="url(#reveal)">')
    # dark "thickness" under every day: only peeks out while a column floats up
    a("<g>")
    for c, week in enumerate(weeks):
        for (row, lvl, _n) in week:
            a(f'<rect x="{GRID_X + c * P + 0.6}" y="{GRID_Y + row * P + 0.6}" width="{CELL - 1.2}" '
              f'height="{CELL - 1.2}" rx="2" fill="{back_color(c, lvl, cols)}"/>')
    a("</g>")
    # top faces: each column floats up when the beam reaches it, lands, then stays still
    for c, week in enumerate(weeks):
        tb = t_beam(c)
        times = [0, tb, tb + LAND, tb + LAND + SETTLE, T]
        lifted = f"{fmt(-LIFT_X)},{fmt(-LIFT_Y)}"
        vals = [lifted, lifted, "0.6,1.2", "0,0", "0,0"]
        a("<g>")
        a(f'<animateTransform attributeName="transform" type="translate" values="{";".join(vals)}" '
          f'keyTimes="{key_times(times, T)}" calcMode="spline" '
          f'keySplines="0 0 1 1;0.22 0.61 0.36 1;0.3 0 0.4 1;0 0 1 1" dur="{T:.3f}s" repeatCount="indefinite"/>')
        for (row, lvl, _n) in week:
            a(f'<rect x="{GRID_X + c * P}" y="{GRID_Y + row * P}" width="{CELL}" height="{CELL}" '
              f'rx="2.5" fill="{cell_color(c, lvl, cols)}"/>')
        a("</g>")
    a("</g>")

    # hits + bullets
    for c, row, f, h in shots:
        x = cx(c)
        cy = GRID_Y + row * P + CELL / 2
        ty = GRID_Y + row * P + CELL
        a(f'<rect x="{GRID_X + c * P}" y="{GRID_Y + row * P}" width="{CELL}" height="{CELL}" rx="2.5" '
          f'fill="#ffe9fa" opacity="0">')
        a(anim("opacity", [0, 0, 0.95, 0, 0], [0, h - 0.01, h, h + 0.4, T], T))
        a("</rect>")
        a(f'<circle cx="{fmt(x)}" cy="{fmt(cy)}" r="3" fill="none" stroke="#ffa6e6" stroke-width="1.5" opacity="0">')
        a(anim("r", [3, 3, 15, 15], [0, h, h + 0.55, T], T))
        a(anim("opacity", [0, 0, 0.9, 0, 0], [0, h - 0.01, h, h + 0.55, T], T))
        a("</circle>")
        a(f'<rect x="{fmt(x - 1.5)}" y="{gun_y}" width="3" height="9" rx="1.5" fill="#ffd0f3" '
          f'filter="url(#glow)" opacity="0">')
        a(anim("y", [gun_y, gun_y, ty, ty], [0, f, h, T], T))
        a(anim("opacity", [0, 0, 1, 1, 0, 0], [0, f - 0.01, f, h, h + 0.01, T], T))
        a("</rect>")

    # the beam that opens the graph
    beam_h = GRID_H + 24
    x_start, x_end = reveal_x0, reveal_x0 + full_w
    beam_op = anim("opacity", [0, 1, 1, 0, 0], [0, 0.3, beam_end, beam_end + 0.45, T], T)
    a(f'<rect y="{GRID_Y - 12}" width="16" height="{beam_h}" fill="url(#beamH)" opacity="0">')
    a(anim("x", [x_start - 8, x_start - 8, x_end - 8, x_end - 8], beam_times, T))
    a(beam_op)
    a("</rect>")
    a(f'<rect y="{GRID_Y - 12}" width="2" height="{beam_h}" rx="1" fill="url(#beamV)" opacity="0">')
    a(anim("x", [x_start - 1, x_start - 1, x_end - 1, x_end - 1], beam_times, T))
    a(beam_op)
    a("</rect>")

    # jet
    vals = ";".join(f"{fmt(x)},{SHIP_Y}" for _, x in pts)
    a(f'<g transform="translate({fmt(cx(0))},{SHIP_Y})">')
    a(f'<animateTransform attributeName="transform" type="translate" values="{vals}" '
      f'keyTimes="{key_times(p_times, T)}" dur="{T:.3f}s" repeatCount="indefinite"/>')
    a('<g transform="scale(1.1)" filter="url(#glow)">')
    a('<path d="M0 -16 L5 -4 L12 8 L6 6 L3 12 L-3 12 L-6 6 L-12 8 L-5 -4 Z" fill="#f7eaff" '
      'stroke="#b45cff" stroke-width="1.5" stroke-linejoin="round"/>')
    a('<path d="M0 -9 L2.5 -2 L-2.5 -2 Z" fill="#ff4fb8"/>')
    a('<path d="M-2 12 L0 20 L2 12 Z" fill="#6fa0ff">'
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
