#!/usr/bin/env python3
"""
"Where the work went next" project timeline card, same look as the other cards
(Nightmare background).

Your pinned repositories (or, if you have none pinned, your newest public ones)
sit on a dashed line in the order they were created, alternating above and below
it. Only the project name is written. A glowing line travels from left to right
and each project pops in as the line reaches it. The card holds for a few seconds,
fades and plays again.

How many repositories are shown?
  At most MAX_REPOS (default 8). If you have more, only the pinned ones are used
  (GitHub allows 6 pins), or the newest ones when nothing is pinned. The rest are
  simply not drawn, so the card never gets crowded.

Usage:
  GITHUB_TOKEN=... GITHUB_USER=yourname python generate_timeline.py   # real data
  python generate_timeline.py --demo                                  # fake data
Output: assets/project-timeline.svg
"""
import html
import json
import os
import sys
import urllib.request

OUT = "assets/project-timeline.svg"

W = 782                 # same width as the other cards
GRID_X = 48
MAX_REPOS = 8           # most projects drawn on the line (8 fits comfortably)
LINE_Y = 150            # y of the timeline
RING_R = 16
H = LINE_Y + 130

# ---- banner colors, used for the card background / frame / traveling line ----
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
DEFAULT_COLOR = "#8b949e"

# ---- timing (seconds) ----
LINE_START = 0.5        # the traveling line starts after this
LINE_DUR = 2.6          # time for the line to cross the card
HOLD = 4.5              # finished card stays visible this long
FADE = 0.6              # fade out before the loop restarts


def stops_xml():
    return "".join(f'<stop offset="{u}" stop-color="{c}"/>' for u, c in STOPS)


def visible(color):
    """Lighten colors that would almost disappear on the dark background."""
    h = color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    if lum >= 0.4:
        return "#" + h.lower()
    return "#%02x%02x%02x" % tuple(round(v + (255 - v) * 0.4) for v in (r, g, b))


# ---------------- data ----------------
def fetch(user, token):
    frag = "name createdAt primaryLanguage{name color}"
    query = ("query($login:String!){user(login:$login){"
             "pinnedItems(first:6,types:REPOSITORY){nodes{... on Repository{%s}}}"
             "repositories(first:20,ownerAffiliations:OWNER,isFork:false,privacy:PUBLIC,"
             "orderBy:{field:CREATED_AT,direction:DESC}){nodes{%s}}}}") % (frag, frag)
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": user}}).encode(),
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "project-timeline",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if data.get("errors") or not (data.get("data") or {}).get("user"):
        sys.exit(f"GitHub API error: {data.get('errors') or 'user not found'}")
    u = data["data"]["user"]

    pinned = [n for n in u["pinnedItems"]["nodes"] if n and n.get("name")]
    if pinned:
        repos, kind = pinned[:MAX_REPOS], "featured"
    else:  # nothing pinned: newest repos, without the profile repo itself
        recent = [n for n in u["repositories"]["nodes"] if n["name"].lower() != user.lower()]
        repos, kind = recent[:MAX_REPOS], "newest"

    items = []
    for n in sorted(repos, key=lambda x: x["createdAt"]):
        lang = n.get("primaryLanguage") or {}
        items.append({
            "name": n["name"],
            "lang": lang.get("name"),
            "color": lang.get("color") or DEFAULT_COLOR,
        })
    return items, kind


def demo():
    return [
        {"name": "mohammadmahdighaedamin", "lang": "Python", "color": "#3572A5"},
        {"name": "proxy-extension", "lang": "JavaScript", "color": "#f1e05a"},
        {"name": "widgetpanel", "lang": "HTML", "color": "#e34c26"},
    ], "featured"


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


def clip(text, max_chars):
    return text if len(text) <= max_chars else text[:max(1, max_chars - 1)].rstrip() + "…"


def build(items, kind="featured"):
    n = len(items)
    x0, x1 = GRID_X, W - GRID_X
    span = x1 - x0
    spacing = span / max(1, n)
    ring = min(RING_R, spacing * 0.36)          # rings shrink if the line gets crowded
    T = LINE_START + LINE_DUR + 0.8 + HOLD + FADE
    font = "Segoe UI, Ubuntu, Helvetica, Arial, sans-serif"
    mono = "Consolas, 'SF Mono', Menlo, monospace"

    out = []
    a = out.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
      f'role="img" aria-label="Project timeline">')
    a(f"""<defs>
<clipPath id="card"><rect x="6" y="6" width="{W - 12}" height="{H - 12}" rx="22"/></clipPath>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="#1d0316"/><stop offset=".45" stop-color="#0d0618"/><stop offset="1" stop-color="#04061a"/></linearGradient>
<radialGradient id="gPink"><stop offset="0" stop-color="#ff3fa8" stop-opacity=".30"/><stop offset="1" stop-color="#ff3fa8" stop-opacity="0"/></radialGradient>
<radialGradient id="gViolet"><stop offset="0" stop-color="#a24ff0" stop-opacity=".18"/><stop offset="1" stop-color="#a24ff0" stop-opacity="0"/></radialGradient>
<radialGradient id="gBlue"><stop offset="0" stop-color="#2563ff" stop-opacity=".28"/><stop offset="1" stop-color="#2563ff" stop-opacity="0"/></radialGradient>
<linearGradient id="frame" x1="0" y1="0" x2="1" y2="0">{stops_xml()}</linearGradient>
<linearGradient id="lineGrad" gradientUnits="userSpaceOnUse" x1="{x0}" y1="0" x2="{x1}" y2="0">{stops_xml()}</linearGradient>
<filter id="glow" x="-300%" y="-300%" width="700%" height="700%">
<feGaussianBlur stdDeviation="2.2" result="b"/>
<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>""")

    # card background, same as the other cards
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
      f'fill="#ffffff">Where the work went next</text>')
    a(f'<text x="{GRID_X}" y="92" font-family="{font}" font-size="13" font-weight="600" fill="#ffffff">'
      f'Project launch sequence</text>')

    # ---------------- animated block (fades out and replays) ----------------
    a("<g>")
    a(anim("opacity", [1, 1, 0, 0], [0, T - FADE, T - 0.05, T], T))

    # the dashed timeline
    a(f'<line x1="{x0}" y1="{LINE_Y}" x2="{x1}" y2="{LINE_Y}" stroke="#ffffff" stroke-opacity=".2" '
      f'stroke-width="1.2" stroke-dasharray="5 6"/>')

    if not items:
        a(f'<text x="{W / 2}" y="{LINE_Y - 12}" text-anchor="middle" font-family="{font}" font-size="13" '
          f'fill="#ffffff">No public repositories yet.</text>')
    else:
        # the traveling line: a gradient bar that grows left -> right, with a glowing head
        end = LINE_START + LINE_DUR
        a(f'<rect x="{x0}" y="{LINE_Y - 1}" width="0" height="2" rx="1" fill="url(#lineGrad)">')
        a(anim("width", [0, 0, span, span], [0, LINE_START, end, T], T))
        a("</rect>")
        a(f'<circle cx="{x0}" cy="{LINE_Y}" r="3.2" fill="#ffffff" filter="url(#glow)" opacity="0">')
        a(anim("cx", [x0, x0, x1, x1], [0, LINE_START, end, T], T))
        a(anim("opacity", [0, 1, 1, 0, 0], [0, LINE_START, end, end + 0.3, T], T))
        a("</circle>")

    for i, it in enumerate(items):
        x = x0 + spacing * (i + 0.5)
        ti = LINE_START + LINE_DUR * (x - x0) / span      # the moment the line reaches this project
        color = visible(OVERRIDES.get(it["lang"], it["color"]))
        above = i % 2 == 0

        # keep the name inside the card and away from the neighbours on the same side
        half = min(x - 40, W - 40 - x, spacing * 0.95)
        name = clip(it["name"], max(6, int(2 * half / 8.2)))

        # node: dashed ring + soft core + a ping, pops in when the line arrives
        a(f'<g transform="translate({fmt(x)},{LINE_Y})" opacity="0">')
        a(f'<animateTransform attributeName="transform" type="scale" additive="sum" '
          f'values="0.5;0.5;1;1" keyTimes="{key_times([0, ti, ti + 0.5, T], T)}" calcMode="spline" '
          f'keySplines="0 0 1 1;0.2 0.7 0.3 1;0 0 1 1" dur="{T:.3f}s" repeatCount="indefinite"/>')
        a(anim("opacity", [0, 0, 1, 1], [0, ti, ti + 0.3, T], T))
        a(f'<circle r="{fmt(ring * 0.75)}" fill="none" stroke="{color}" stroke-width="1.2" opacity="0">'
          f'<animate attributeName="r" values="{fmt(ring * 0.75)};{fmt(ring * 1.65)}" dur="2.6s" repeatCount="indefinite"/>'
          f'<animate attributeName="opacity" values="0.6;0" dur="2.6s" repeatCount="indefinite"/></circle>')
        a(f'<circle r="{fmt(ring)}" fill="#07030f" fill-opacity=".7"/>')
        a(f'<circle r="{fmt(ring)}" fill="none" stroke="{color}" stroke-width="1.6" stroke-dasharray="4 3.4" '
          f'stroke-linecap="round"><animateTransform attributeName="transform" type="rotate" '
          f'values="0;360" dur="14s" repeatCount="indefinite"/></circle>')
        a(f'<circle r="{fmt(ring * 0.66)}" fill="{color}" fill-opacity=".22"/>')
        a(f'<circle r="{fmt(max(2.4, ring * 0.25))}" fill="{color}" filter="url(#glow)"/>')
        a("</g>")

        # project name only, fades in right after the node
        y = LINE_Y - 30 if above else LINE_Y + 44
        a('<g opacity="0">')
        a(anim("opacity", [0, 0, 1, 1], [0, ti + 0.2, ti + 0.7, T], T))
        a(f'<text x="{fmt(x)}" y="{y}" text-anchor="middle" font-family="{mono}" font-size="13" '
          f'font-weight="700" fill="#ffffff">{html.escape(name)}</text>')
        a("</g>")

    # footer
    if items:
        a(f'<text x="{GRID_X}" y="{LINE_Y + 84}" font-family="{font}" font-size="11" fill="#ffffff" '
          f'fill-opacity=".75">{n} {kind} repositor{"y" if n == 1 else "ies"} · '
          f'follow the line from first signal to latest motion</text>')

    a("</g>")
    a("</svg>")
    return "\n".join(out)


def main():
    if "--demo" in sys.argv:
        items, kind = demo()
    else:
        user = os.environ.get("GITHUB_USER")
        token = os.environ.get("GITHUB_TOKEN")
        if not user or not token:
            sys.exit("Set GITHUB_USER and GITHUB_TOKEN, or run with --demo")
        items, kind = fetch(user, token)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(build(items, kind))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
