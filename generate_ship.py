#!/usr/bin/env python3
"""
Animated "Jet Runner" contribution card.

- Only the card background (and its frame) uses the Nightmare banner colors:
  dark maroon -> navy with pink / purple / blue glows.
- Days and legend use a purple palette; bullets and jet stay blue.
- A plain purple line (no effects) sweeps quickly left -> right and
  opens the graph. Days right behind it are tiny and dim, then gradually grow to full size.
- An F-35 slowly flies left -> right underneath and shoots every active day;
  a shot day explodes and is removed.

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
JET_SCALE = 0.85

# ---- palette for the days and the legend (level 0..4); faint (empty) -> deepest #5b3fa8 (most active) ----
COLORS = ["#28223f", "#0e4c7a", "#1b74b5", "#2a9df4", "#5cc8ff"]   # level 0 = empty day (purple-gray), 1..4 = original blues
LEGEND_COLORS = COLORS  # legend matches the graph

# ---- banner colors, used for the card background / frame only ----
STOPS = [(0.0, "#ff4fb8"), (0.35, "#c04ee8"), (0.65, "#7a5cf5"), (1.0, "#1f6bff")]

LEVELS = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}

# ---- timing (seconds) ----
START_DELAY = 0.6      # the beam waits a moment before it starts
BEAM_STEP = 0.05       # beam time per column (53 columns ~ 2.7 s) -- fast
GROW_COLS = 5          # how many columns behind the beam are still "growing"
GROW = GROW_COLS * BEAM_STEP   # time for a day to go from tiny/dim to full size
GROW_FROM_SCALE = 0.18  # size of a day right at the beam (1 = full size)
GROW_FROM_OPACITY = 0.12  # opacity of a day right at the beam
JET_START = START_DELAY + 0.9   # jet starts once the first columns are open
STEP = 0.16            # jet time per column (53 columns ~ 8.5 s) -- slow
SHOT_GAP = 0.42        # delay between bullets in one column (max)
SHOT_GAP_MIN = 0.10    # lower bound when the year is very busy
COL_PAUSE_IN = 0.15    # jet stops this long before firing
COL_PAUSE_OUT = 0.25   # ...and this long after the last bullet leaves
MAX_LOOP = 30.0        # busy years are sped up just enough to stay under this
BULLET_SPEED = 180.0   # px / second
HOLD = 3.2             # finished graph stays visible this long
FADE = 0.7             # fade out before the loop restarts
TRAIL = 70             # length of the soft purple trail behind the beam (px)


def stops_xml():
    return "".join(f'<stop offset="{u}" stop-color="{c}"/>' for u, c in STOPS)


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


# F-35 seen from above, nose up. Right half, then mirrored.
F35_BODY = (
    "M0 -20 L1.5 -14 L2.6 -8 L3.4 -3 L4.4 1 L13.8 9.2 L13.4 12.4 L5 11.2 L4.4 13 "
    "L9.6 16.6 L8.8 19 L3.4 17.6 L2.4 18 L2.1 20.5 L-2.1 20.5 L-2.4 18 L-3.4 17.6 "
    "L-8.8 19 L-9.6 16.6 L-4.4 13 L-5 11.2 L-13.4 12.4 L-13.8 9.2 L-4.4 1 L-3.4 -3 "
    "L-2.6 -8 L-1.5 -14 Z"
)


def jet_svg():
    return f"""<g transform="scale({JET_SCALE})"><g filter="url(#glow)">
<path d="M-1.8 20.5 L0 30 L1.8 20.5 Z" fill="#5cc8ff"><animate attributeName="opacity" values="1;.35;1" dur=".28s" repeatCount="indefinite"/></path>
<path d="M-.9 20.5 L0 26 L.9 20.5 Z" fill="#dff4ff"><animate attributeName="opacity" values=".4;1;.4" dur=".28s" repeatCount="indefinite"/></path>
<path d="{F35_BODY}" fill="url(#jetBody)" stroke="#2a9df4" stroke-width=".8" stroke-linejoin="round"/>
<path d="M0 -12.5 C1.7 -10.8 1.9 -6.6 0 -3.6 C-1.9 -6.6 -1.7 -10.8 0 -12.5 Z" fill="#16304f"/>
<path d="M0 -11 C.7 -9.6 .8 -7.5 0 -6" fill="none" stroke="#8fe0ff" stroke-width=".5" opacity=".85"/>
<path d="M3 -3.2 L4.3 .4 L3 .9 Z M-3 -3.2 L-4.3 .4 L-3 .9 Z" fill="#23405f"/>
<path d="M0 -3 L0 17.4" stroke="#5b86a8" stroke-width=".5" opacity=".6"/>
<path d="M2.3 7 L5.4 14.6 M-2.3 7 L-5.4 14.6" stroke="#3d6a90" stroke-width="1.1" stroke-linecap="round" opacity=".85"/>
<path d="M-1.9 17.4 L1.9 17.4 L1.6 20.5 L-1.6 20.5 Z" fill="#2c4a66"/>
<circle cx="-13.5" cy="10.8" r=".9" fill="#5cc8ff"/><circle cx="13.5" cy="10.8" r=".9" fill="#5cc8ff"/>
</g></g>"""


def build(weeks, total):
    cols = len(weeks)
    grid_w = cols * P - GAP
    W = GRID_X * 2 + grid_w
    right = W - GRID_X
    gun_y = SHIP_Y - 17  # bullets leave the nose here

    def cx(c):
        return GRID_X + c * P + CELL / 2

    # ---------------- jet schedule ----------------
    active_cols = sum(1 for w in weeks if any(d[1] > 0 for d in w))
    n_shots = sum(1 for w in weeks for d in w if d[1] > 0)

    # Quiet profiles run at the relaxed pace set above. Very busy years are sped
    # up just enough to keep one loop under MAX_LOOP seconds.
    fixed = JET_START + HOLD + FADE
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

    t = JET_START
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
    hit = {(c, row): h for c, row, f, h in shots}

    # ---------------- beam schedule (independent of the jet, much faster) ----------------
    x_start = GRID_X - 2
    x_end = GRID_X + grid_w + 2
    beam_dur = cols * BEAM_STEP
    beam_end = START_DELAY + beam_dur
    beam_times = [0, START_DELAY, beam_end, T]

    def t_beam(c):
        return START_DELAY + beam_dur * (GRID_X + c * P - x_start) / (x_end - x_start)

    def beam_x(offset):
        """x animation that follows the beam, shifted by `offset` px."""
        return anim("x", [x_start + offset, x_start + offset, x_end + offset, x_end + offset], beam_times, T)

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
<linearGradient id="beamCore" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#a855f7" stop-opacity=".35"/><stop offset=".2" stop-color="#c58bff"/><stop offset=".5" stop-color="#ead7ff"/><stop offset=".8" stop-color="#c58bff"/><stop offset="1" stop-color="#a855f7" stop-opacity=".35"/></linearGradient>
<linearGradient id="beamHalo" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="#a855f7" stop-opacity="0"/><stop offset=".5" stop-color="#a855f7" stop-opacity=".45"/><stop offset="1" stop-color="#a855f7" stop-opacity="0"/></linearGradient>
<linearGradient id="beamTrail" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="#a855f7" stop-opacity="0"/><stop offset="1" stop-color="#a855f7" stop-opacity=".28"/></linearGradient>
<linearGradient id="jetBody" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="#b9d4ea"/><stop offset=".5" stop-color="#ffffff"/><stop offset="1" stop-color="#b9d4ea"/></linearGradient>
<filter id="glow" x="-300%" y="-100%" width="700%" height="300%">
<feGaussianBlur stdDeviation="2" result="b"/>
<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<filter id="beamGlow" x="-600%" y="-10%" width="1300%" height="120%">
<feGaussianBlur stdDeviation="2.5" result="b"/>
<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>""")

    # ---------------- card (the only place with the banner colors) ----------------
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
      f'fill="#ffffff">Contribution Activity</text>')
    a(f'<text x="{GRID_X}" y="92" font-family="{font}" font-size="13" font-weight="600" fill="#ffffff">'
      f'{total} contributions in the last year</text>')

    # legend (default blue palette)
    sq_right = right - 34
    first_sq = sq_right - 5 * P + GAP
    a(f'<text x="{right}" y="70" text-anchor="end" font-family="{font}" font-size="11" fill="#ffffff">More</text>')
    for i, col in enumerate(LEGEND_COLORS):
        a(f'<rect x="{first_sq + i * P}" y="61" width="{CELL}" height="{CELL}" rx="2.5" fill="{col}"/>')
    a(f'<text x="{first_sq - 7}" y="70" text-anchor="end" font-family="{font}" font-size="11" fill="#ffffff">Less</text>')

    # ---------------- animated layer (fades in / out around each loop) ----------------
    a("<g>")
    a(anim("opacity", [0, 1, 1, 0], [0, 0.5, T - FADE, T], T))

    # days: tiny + dim right behind the beam, then smoothly (linearly) grow
    # bigger and brighter over GROW_COLS columns until they reach full size.
    # A day that gets shot is removed.
    for c, week in enumerate(weeks):
        tb = t_beam(c)
        s_kt = key_times([0, tb, tb + GROW, T], T)
        for (row, lvl, _n) in week:
            h = hit.get((c, row))
            o_vals = [0, 0, GROW_FROM_OPACITY, 1, 1]
            o_times = [0, tb - 0.01, tb, tb + GROW, T]
            if h is not None:
                o_vals = [0, 0, GROW_FROM_OPACITY, 1, 1, 0, 0]
                o_times = [0, tb - 0.01, tb, tb + GROW, h, h + 0.12, T]
            a(f'<g transform="translate({fmt(cx(c))},{fmt(GRID_Y + row * P + CELL / 2)})" opacity="0">')
            a(f'<animateTransform attributeName="transform" type="scale" additive="sum" '
              f'values="{GROW_FROM_SCALE};{GROW_FROM_SCALE};1;1" keyTimes="{s_kt}" '
              f'dur="{T:.3f}s" repeatCount="indefinite"/>')
            a(anim("opacity", o_vals, o_times, T))
            a(f'<rect x="-5" y="-5" width="10" height="10" rx="2.5" fill="{COLORS[lvl]}"/>')
            a("</g>")

    # bullets + explosions
    for c, row, f, h in shots:
        x = cx(c)
        cy = GRID_Y + row * P + CELL / 2
        ty = GRID_Y + row * P + CELL
        a(f'<rect x="{GRID_X + c * P}" y="{GRID_Y + row * P}" width="{CELL}" height="{CELL}" rx="2.5" '
          f'fill="#dff4ff" opacity="0">')
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

    # the beam: a plain solid purple line (no glow, trail or sparks)
    beam_y, beam_h = GRID_Y - 8, GRID_H + 16
    a('<g opacity="0">')
    a(anim("opacity", [0, 1, 1, 0, 0], [0, 0.3, beam_end, beam_end + 0.45, T], T))
    a(f'<rect y="{beam_y}" width="3" height="{beam_h}" rx="1.5" fill="#a855f7">')
    a(beam_x(-1.5))
    a("</rect>")
    a("</g>")

    # jet (F-35)
    vals = ";".join(f"{fmt(x)},{SHIP_Y}" for _, x in pts)
    a(f'<g transform="translate({fmt(cx(0))},{SHIP_Y})">')
    a(f'<animateTransform attributeName="transform" type="translate" values="{vals}" '
      f'keyTimes="{key_times(p_times, T)}" dur="{T:.3f}s" repeatCount="indefinite"/>')
    a(jet_svg())
    a("</g>")

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
