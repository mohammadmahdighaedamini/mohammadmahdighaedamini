#!/usr/bin/env python3
"""
"Language Stack" card, same look as the contribution card (Nightmare background).

Languages are weighted by repository: every public, non-fork repo counts the same,
and is split between its languages by their share of the code. The top languages
are shown as bars. Each bar fills from 0 up to its percentage while the number
counts up with it (e.g. HTML: 0% -> 76%).

Synced with the contribution card: both loops start together and share the same
cycle length (read from assets/contrib-ship.svg, so run generate_ship.py first).
The bars finish at their own pace, stay full, and everything resets only when the
jet reaches the end and the contribution card starts over.

Usage:
  GITHUB_TOKEN=... GITHUB_USER=yourname python generate_langs.py   # real data
  python generate_langs.py --demo                                  # fake data
Output: assets/language-stack.svg
"""
import html
import json
import os
import re
import sys
import urllib.request

from fontembed import FONT_STACK, embed_fonts

OUT = "assets/language-stack.svg"

W = 782                 # same width as the contribution card
GRID_X = 48
ROW_Y0 = 132            # center of the first row
ROW_GAP = 30
TOP_N = 5               # languages shown (the rest are summed into "Other")
BAR_X = 268
BAR_W = W - GRID_X - BAR_X
BAR_H = 8

# ---- banner colors, used for the card background / frame ----
STOPS = [(0.0, "#ff4fb8"), (0.35, "#c04ee8"), (0.65, "#7a5cf5"), (1.0, "#1f6bff")]

# Brighter versions of a few language colors so they read well on the dark card.
OVERRIDES = {
    "HTML": "#f0553c",
    "Rust": "#dea584",
    "JavaScript": "#f4d35e",
    "CSS": "#a86fd1",
    "Python": "#3d8fc4",
    "TypeScript": "#4a90d9",
}
OTHER_COLOR = "#8b949e"

# ---- timing (seconds) ----
FIRST_BAR = 0.5         # first bar starts after this
BAR_DELAY = 0.18        # delay between rows
BAR_DUR = 2.2           # time for a bar to fill from 0 to its percentage
HOLD = 4.0              # finished card stays visible this long
FADE = 0.7              # fade out before the loop restarts (same as the jet card)
SHIP_SVG = "assets/contrib-ship.svg"
EASE = (0.2, 0.7, 0.3, 1.0)   # bar easing (fast start, soft landing); numbers follow it


def stops_xml():
    return "".join(f'<stop offset="{u}" stop-color="{c}"/>' for u, c in STOPS)


def visible(color):
    """Lighten colors that would almost disappear on the dark background."""
    h = color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    if lum >= 0.4:
        return "#" + h.lower()
    k = 0.4
    return "#%02x%02x%02x" % tuple(round(v + (255 - v) * k) for v in (r, g, b))


# ---------------- data ----------------
def fetch(user, token):
    query = """query($login:String!){user(login:$login){repositories(first:100,
    ownerAffiliations:OWNER,isFork:false,privacy:PUBLIC){nodes{languages(first:10,
    orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}}}}}"""
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": user}}).encode(),
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "language-stack",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if data.get("errors") or not (data.get("data") or {}).get("user"):
        sys.exit(f"GitHub API error: {data.get('errors') or 'user not found'}")

    weights, colors, n = {}, {}, 0
    for repo in data["data"]["user"]["repositories"]["nodes"]:
        edges = repo["languages"]["edges"]
        total = sum(e["size"] for e in edges)
        if not total:
            continue
        n += 1
        for e in edges:
            name = e["node"]["name"]
            weights[name] = weights.get(name, 0) + e["size"] / total
            colors[name] = e["node"]["color"] or OTHER_COLOR
    if not n:
        return []
    ranked = sorted(weights.items(), key=lambda kv: -kv[1])
    return [(name, w / n * 100, colors[name]) for name, w in ranked]


def demo():
    return [
        ("HTML", 76, "#e34c26"),
        ("Rust", 14, "#dea584"),
        ("JavaScript", 4, "#f1e05a"),
        ("CSS", 4, "#563d7c"),
        ("Python", 2, "#3572A5"),
    ]


# ---------------- easing (so the counter matches the bar exactly) ----------------
def _bez(s, a, b):
    return 3 * (1 - s) ** 2 * s * a + 3 * (1 - s) * s ** 2 * b + s ** 3


def ease(u):
    """Progress (0..1) of the bar after a fraction u of its duration."""
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if _bez(mid, EASE[0], EASE[2]) < u:
            lo = mid
        else:
            hi = mid
    return _bez((lo + hi) / 2, EASE[1], EASE[3])


def time_for(progress):
    """Fraction of the bar's duration at which it has reached `progress`."""
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if ease(mid) < progress:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def ship_cycle():
    """Loop length (s) of the contribution card, so both cards restart together."""
    try:
        with open(SHIP_SVG, encoding="utf-8") as fh:
            durs = [float(d) for d in re.findall(r'dur="([0-9.]+)s"', fh.read())]
    except OSError:
        return 0.0
    return max(durs, default=0.0)


# ---------------- svg helpers ----------------
def fmt(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


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


def anim(attr, values, times, T, extra=""):
    vals = ";".join(v if isinstance(v, str) else fmt(v) for v in values)
    return (
        f'<animate attributeName="{attr}" values="{vals}" keyTimes="{key_times(times, T)}" '
        f'dur="{T:.3f}s" repeatCount="indefinite"{extra}/>'
    )


def build(langs):
    rows = [(n, p, visible(OVERRIDES.get(n, c))) for n, p, c in langs[:TOP_N]]
    rest = sum(p for _, p, _ in langs[TOP_N:])
    if rest >= 1:
        rows.append(("Other", rest, OTHER_COLOR))

    n = max(1, len(rows))
    H = ROW_Y0 + (n - 1) * ROW_GAP + 60
    own = FIRST_BAR + (n - 1) * BAR_DELAY + BAR_DUR + FADE
    T = max(own + HOLD, ship_cycle())   # same loop length as the jet card
    font = FONT_STACK
    mono = FONT_STACK

    out = []
    a = out.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
      f'role="img" aria-label="Language stack">')
    a(f"""<defs>
<clipPath id="card"><rect x="6" y="6" width="{W - 12}" height="{H - 12}" rx="22"/></clipPath>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="#1d0316"/><stop offset=".45" stop-color="#0d0618"/><stop offset="1" stop-color="#04061a"/></linearGradient>
<radialGradient id="gPink"><stop offset="0" stop-color="#ff3fa8" stop-opacity=".30"/><stop offset="1" stop-color="#ff3fa8" stop-opacity="0"/></radialGradient>
<radialGradient id="gViolet"><stop offset="0" stop-color="#a24ff0" stop-opacity=".18"/><stop offset="1" stop-color="#a24ff0" stop-opacity="0"/></radialGradient>
<radialGradient id="gBlue"><stop offset="0" stop-color="#2563ff" stop-opacity=".28"/><stop offset="1" stop-color="#2563ff" stop-opacity="0"/></radialGradient>
<linearGradient id="frame" x1="0" y1="0" x2="1" y2="0">{stops_xml()}</linearGradient>
</defs>""")

    # card background, same as the contribution card
    a('<g clip-path="url(#card)">')
    a(f'<rect width="{W}" height="{H}" fill="url(#bg)"/>')
    a(f'<circle cx="{fmt(W * 0.12)}" cy="{fmt(H * 0.92)}" r="240" fill="url(#gPink)"/>')
    a(f'<circle cx="{fmt(W * 0.45)}" cy="0" r="210" fill="url(#gViolet)"/>')
    a(f'<circle cx="{fmt(W * 0.92)}" cy="{fmt(H * 0.28)}" r="240" fill="url(#gBlue)"/>')
    a(f'<circle cx="{fmt(W * 0.78)}" cy="{H}" r="170" fill="url(#gBlue)" opacity=".5"/>')
    a("</g>")
    a(f'<rect x="6" y="6" width="{W - 12}" height="{H - 12}" rx="22" fill="none" '
      f'stroke="url(#frame)" stroke-opacity=".65" stroke-width="1.5"/>')
    a(f'<rect x="28" y="28" width="{W - 56}" height="{H - 56}" rx="16" fill="#07030f" '
      f'fill-opacity=".45" stroke="url(#frame)" stroke-opacity=".4" stroke-width="1.2"/>')

    a(f'<text x="{GRID_X}" y="70" font-family="{font}" font-size="24" font-weight="700" '
      f'fill="#ffffff">Language Stack</text>')
    a(f'<text x="{GRID_X}" y="92" font-family="{font}" font-size="13" font-weight="600" fill="#ffffff">'
      f'Languages I use most across my repositories</text>')

    if not rows:
        a(f'<text x="{GRID_X}" y="{ROW_Y0 + 4}" font-family="{font}" font-size="13" fill="#ffffff">'
          f'No public repositories with code yet.</text>')

    # ---------------- bars (the whole block fades out and replays) ----------------
    a("<g>")
    a(anim("opacity", [0, 1, 1, 0], [0, 0.5, T - FADE, T], T))   # same fade in/out as the jet card

    for i, (name, p, color) in enumerate(rows):
        y = ROW_Y0 + i * ROW_GAP
        t0 = FIRST_BAR + i * BAR_DELAY
        label = name if len(name) <= 16 else name[:15] + "…"
        bar_w = max(6.0, p / 100 * BAR_W)
        shown = round(p)
        num_attrs = (f'x="{BAR_X - 16}" y="{y + 4.5}" text-anchor="end" font-family="{font}" '
                     f'font-size="12" font-weight="700" fill="#ffffff"')

        # dot and name fade in as the row starts
        a('<g opacity="0">')
        a(anim("opacity", [0, 0, 1, 1], [0, t0, t0 + 0.4, T], T))
        a(f'<circle cx="{GRID_X + 5}" cy="{y}" r="5" fill="{color}"/>')
        a(f'<text x="{GRID_X + 22}" y="{y + 4.5}" font-family="{font}" font-size="13" font-weight="700" '
          f'fill="#ffffff">{html.escape(label)}</text>')

        # counter: one text per number, shown one after another, in step with the bar
        if shown >= 1:
            starts = [0.0] + [t0 + BAR_DUR * time_for(k / shown) for k in range(1, shown + 1)]
            a('<g class="nums">')
            for k in range(shown + 1):
                if k == 0:
                    vals, times = ["visible", "hidden", "hidden"], [0, starts[1], T]
                elif k < shown:
                    vals, times = ["hidden", "visible", "hidden", "hidden"], [0, starts[k], starts[k + 1], T]
                else:
                    vals, times = ["hidden", "visible", "visible"], [0, starts[k], T]
                hid = "" if k == 0 else ' visibility="hidden"'
                a(f'<text {num_attrs}{hid}>{k}%'
                  + anim("visibility", vals, times, T, ' calcMode="discrete"') + "</text>")
            a("</g>")
        else:
            a(f'<text {num_attrs}>&lt;1%</text>')
        a("</g>")

        # track + bar that fills from 0 to its width
        a(f'<rect x="{BAR_X}" y="{y - BAR_H / 2}" width="{BAR_W}" height="{BAR_H}" rx="{BAR_H / 2}" '
          f'fill="#ffffff" fill-opacity=".09"/>')
        a(f'<rect class="bar" x="{BAR_X}" y="{y - BAR_H / 2}" width="0" height="{BAR_H}" '
          f'rx="{BAR_H / 2}" fill="{color}">')
        a(anim("width", [0, 0, bar_w, bar_w], [0, t0, t0 + BAR_DUR, T], T,
               ' calcMode="spline" keySplines="0 0 1 1;%s %s %s %s;0 0 1 1"' % EASE))
        a("</rect>")

    a("</g>")
    a("</svg>")
    return embed_fonts("\n".join(out))   # embed the Segoe UI font into the SVG


def main():
    if "--demo" in sys.argv:
        langs = demo()
    else:
        user = os.environ.get("GITHUB_USER")
        token = os.environ.get("GITHUB_TOKEN")
        if not user or not token:
            sys.exit("Set GITHUB_USER and GITHUB_TOKEN, or run with --demo")
        langs = fetch(user, token)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(build(langs))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
