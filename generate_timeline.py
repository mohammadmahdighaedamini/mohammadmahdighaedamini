#!/usr/bin/env python3
"""
"My Project Journey" project timeline card (Nightmare background).

Repositories sit on a dashed line in the order they were created, alternating
above and below it. For every project the card shows:
  * the project name, written in the project's own color (5 colors, see PALETTE)
  * a ring in that same color; inside it the repo's own logo (if it has one), which
    breathes together with a ring that spreads out (see PULSE_STYLE)

Visible projects:
  At most VISIBLE (5) at the same time. With more than 5 the timeline keeps
  moving forward (oldest slides out on the left, next slides in on the right)
  until the LAST project, holds a few seconds, fades out and restarts.

Logos (nothing is drawn by the script itself):
  1. A file called logo.svg / logo.png / logo.webp / logo.jpg in the ROOT of the
     repo itself: it is picked up automatically (keep it small, ideally square).
  2. REPO_ICONS below (optional, empty by default): an icon you choose by hand.
  A repo with no logo shows only its ring (the ring itself breathes).

Which repositories?
  SOURCE = "all"   : newest MAX_REPOS public non-fork repos (new repos show up automatically).
  SOURCE = "pinned": pinned repos (max 6); if nothing is pinned, newest repos.

Usage:
  GITHUB_TOKEN=... GITHUB_USER=yourname python generate_timeline.py   # real data
  python generate_timeline.py --demo                                  # fake data
Output: assets/project-timeline.svg
"""
import base64
import html
import json
import math
import os
import sys
import urllib.request

OUT = "assets/project-timeline.svg"

W = 782                 # same width as the other cards
GRID_X = 48
VISIBLE = 5             # projects shown at the same time
MAX_REPOS = 12          # total projects the timeline will walk through
SOURCE = "all"          # "all" = every public non-fork repo, new repos appear by themselves (newest MAX_REPOS)
                        # "pinned" = only the repos you pinned on your profile (max 6)
HIDE_PROFILE_REPO = False   # False = the profile repo itself (named like your username) is shown too
REQUIRE_LOGO = True         # True = a repo WITHOUT a logo file (logo.svg/png/webp/jpg) is left out of the timeline
LINE_Y = 160            # y of the timeline
RING_R = 16
RING_DASHES = 6         # how many dashes the circle around a logo is made of (fewer = calmer)
PULSE_STYLE = "sync-breathe-ring"   # logo animation:
#   ALL logos beat together, at the same moment, again and again (no more one-after-another):
#     "sync-heartbeat" : lub-dub, like a real heart (two quick beats, then a rest)
#     "sync-pop"       : one strong pop that overshoots and settles
#     "sync-breathe"   : smooth, slow grow / shrink (calm)
#     "sync-glow"      : lub-dub + a soft glow flash behind the logo
#     "sync-ring"      : pop + a ring that spreads out like a sonar ping
#     "sync-breathe-ring" : smooth breathing + a ring spreading out on every breath
#   older styles (logos beat one after another / other effects):
#     "heartbeat" | "flash" | "heartbeat-glow" | "neon" | "none"
# "heartbeat" = ONE slow beat per logo, then the next logo beats (not a continuous pulse)
SYNC_PEAK = 1.5         # sync styles: how big the logo gets at the top of a beat (1.0 = no change)
                        # (it is automatically limited so the logo NEVER crosses the dashed circle)
SYNC_LOW = 0.8          # breathe styles: how small the logo gets when it breathes out
LOGO_MAX_R = 14.3       # farthest point of any built-in logo from its center (in the 24x24 box)
SYNC_PERIOD = 4.5       # sync styles: seconds for one full breath (bigger = slower and calmer)
SYNC_START = 1.5        # sync styles: first beat (the first logo has just appeared)
BEAT_MODE = "arrive"    # "arrive": each logo beats once as the line reaches it (a beat travelling along the line)
                        # "sequence": after the line is done, the visible logos beat one after another
BEAT_SCALE = 1.25       # how big the logo gets at the peak of its beat
BEAT_UP = 0.6           # seconds to swell up (slow)
BEAT_DOWN = 1.4         # seconds to relax back (slower)
BEAT_STEP = 1.5         # "sequence" mode: seconds between one logo's beat and the next
LOGO_FILES = ("logo.svg", "logo.png", "logo.webp", "logo.jpg", "logo.jpeg")  # looked up in each repo's root
MAX_LOGO_KB = 150       # bigger logo files are skipped (they would make the card heavy)
H = LINE_Y + 130

# ---------------------------------------------------------------------------
# CHOOSE YOUR OWN LOGO FOR A REPO (optional)
#
# Key = repository name. Value = either just the icon, or a dict with any of:
#   "icon"  : what to draw inside the ring. One of
#               - a built-in icon name (see GENERIC_ICONS below), e.g. "book"
#               - a language name to use its logo, e.g. "Python"
#               - "file:assets/my-logo.png"   your own image (png/svg/jpg/webp, keep it small)
#               - "path:M12 2L2 22h20z"       any 24x24 path, e.g. copied from simpleicons.org
#   "color" : hex color for the ring + icon + label, e.g. "#ffb86b"
#   "label" : text under the name (default: the repo's main language)
#
# Examples (remove the # to use them):
REPO_ICONS = {
    # "my-notes":       {"icon": "book", "label": "Notes"},
    # "my-blog":        {"icon": "globe", "color": "#4ec9b0", "label": "Website"},
    # "robot-project":  "robot",
    # "brand-logo":     {"icon": "file:assets/logo.png", "label": "Design"},
}
# ---------------------------------------------------------------------------

# ---- the 5 project colors: repo 1, 2, 3, 4, 5, then the cycle starts again ----
# (chosen to stand out from the pink / violet / blue of the background)
PALETTE = ["#58b9ff", "#ff6070", "#4fdc7c", "#e39a45", "#d4e84f"]   # sky blue, red, green, amber-brown, lime

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
DARK = "#0b0614"        # color of the details drawn on top of a filled logo

# ---- timing (seconds) ----
LINE_START = 0.5        # the traveling line starts after this
LINE_DUR = 2.6          # time for the line to cross the card
SHIFT = 0.9             # one step of the timeline moving forward
PAUSE = 0.6             # short rest between two steps
HOLD = 4.5              # finished card stays visible this long
FADE = 0.6              # fade out before the loop restarts

# ---------------------------------------------------------------------------
# LOGOS. Every logo is drawn in a 24x24 box. COL = the language color,
# DRK = dark detail color. (Simplified, single-color versions of the real logos.)
# ---------------------------------------------------------------------------
_FONT = 'font-family="Arial,Helvetica,sans-serif"'


def _hex(label, size):
    return ('<path d="M12 1.5l9.1 5.25v10.5L12 22.5l-9.1-5.25V6.75z" fill="COL"/>'
            f'<text x="12" y="12.3" dy=".35em" text-anchor="middle" {_FONT} font-size="{size}" '
            f'font-weight="800" fill="DRK">{label}</text>')


def _square(label):
    return ('<rect x="2" y="2" width="20" height="20" rx="2.2" fill="COL"/>'
            f'<text x="20.6" y="20" text-anchor="end" {_FONT} font-size="9.5" '
            f'font-weight="800" fill="DRK">{label}</text>')


_SHIELD = '<path d="M3 2h18l-1.6 18L12 22.5 4.6 20z" fill="COL"/>'
_STROKE = 'fill="none" stroke="DRK" stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round"'

LOGOS = {
    "HTML": ('<path d="M3 2h9v20.4l-7.4-2.3z" fill="#e34f26"/>'
             '<path d="M12 2h9l-1.6 18.1L12 22.4z" fill="#ef652a"/>'
             '<path d="M16.6 7H8.3l.4 4.7h6.6l-.4 4.2L12 17l-2.9-1" fill="none" stroke="#fff" '
             'stroke-width="2" stroke-linejoin="miter" stroke-miterlimit="4"/>'),
    "CSS": _SHIELD + f'<path d="M8.8 7.2h6.4l-3 4c2.6-.2 3.6 1.7 3 3.7-.5 1.6-2 2.1-3 2.1s-2.2-.4-2.9-1.2" {_STROKE}/>',
    "JavaScript": _square("JS"),
    "TypeScript": _square("TS"),
    "Python": (
        '<path d="M11.9 2C7.5 2 7.8 3.9 7.8 3.9v2.2H12v.7H5.9S3 6.5 3 11.2s2.5 4.5 2.5 4.5H7v-2.2S6.9 11 9.5 11h4.8s2.3 0 2.3-2.3V4.4S17 2 11.9 2z" fill="COL"/>'
        '<path d="M12.1 22c4.4 0 4.1-1.9 4.1-1.9v-2.2H12v-.7h6.1S21 17.5 21 12.8s-2.5-4.5-2.5-4.5H17v2.2S17.1 13 14.5 13H9.7s-2.3 0-2.3 2.3v4.3S7 22 12.1 22z" fill="COL"/>'
        '<circle cx="9.6" cy="4.7" r=".9" fill="DRK"/><circle cx="14.4" cy="19.3" r=".9" fill="DRK"/>'),
    "Rust": ('<circle cx="12" cy="12" r="8" fill="none" stroke="COL" stroke-width="2.2"/>'
             '<circle cx="12" cy="12" r="10.2" fill="none" stroke="COL" stroke-width="2.6" stroke-dasharray="2.8 2.6"/>'
             f'<text x="12" y="12.3" dy=".35em" text-anchor="middle" {_FONT} font-size="9.5" font-weight="900" fill="COL">R</text>'),
    "Go": ('<path d="M1 9.5h4.5M0 12.5h4.5M2 15.5h3.5" stroke="COL" stroke-width="1.3" stroke-linecap="round"/>'
           f'<text x="15" y="16.3" text-anchor="middle" {_FONT} font-size="11.5" font-weight="900" font-style="italic" fill="COL">GO</text>'),
    "Java": ('<path d="M5 11h12v5c0 2.8-2.2 4.5-5 4.5h-2c-2.8 0-5-1.7-5-4.5z" fill="COL"/>'
             '<path d="M17 12.5h1.4c1.6 0 2.3 1 2.3 2.2s-.9 2.3-2.4 2.3H17" fill="none" stroke="COL" stroke-width="1.6"/>'
             '<path d="M3.5 22.5h15M8.2 3.2c-1.6 2.2 1.4 3.2 0 5.3M12.2 2c-1.8 2.6 1.6 3.8 0 6.5" fill="none" stroke="COL" stroke-width="1.5" stroke-linecap="round"/>'),
    "C": _hex("C", 11),
    "C++": _hex("C++", 7.2),
    "C#": _hex("C#", 8.6),
    "PHP": ('<ellipse cx="12" cy="12" rx="11" ry="6.8" fill="COL"/>'
            f'<text x="12" y="12.3" dy=".35em" text-anchor="middle" {_FONT} font-size="8.6" font-weight="900" font-style="italic" fill="DRK">php</text>'),
    "Ruby": ('<path d="M6.5 3h11L22 8.8 12 22 2 8.8z" fill="COL"/>'
             '<path d="M2 8.8h20M6.5 3L9 8.8 12 22M17.5 3L15 8.8 12 22M9 8.8L12 3l3 5.8" fill="none" stroke="DRK" stroke-width="1" stroke-linejoin="round" stroke-opacity=".7"/>'),
    "Shell": ('<rect x="2" y="4" width="20" height="16" rx="3" fill="COL"/>'
              '<path d="M6 9l4 3-4 3M12.5 16H18" fill="none" stroke="DRK" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'),
    "Kotlin": '<path d="M2 2h20L12 12l10 10H2z" fill="COL"/>',
    "Vue": ('<path d="M1.5 3h5L12 12.4 17.5 3h5L12 21z" fill="COL"/>'
            '<path d="M6.5 3h3.3L12 6.9 14.2 3h3.3L12 12.4z" fill="DRK" fill-opacity=".8"/>'),
    "Code": ('<path d="M8 7l-5 5 5 5M16 7l5 5-5 5M13.8 5l-3.6 14" fill="none" stroke="COL" '
             'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'),
}

# Icons for repos that are not about a programming language (choose them in REPO_ICONS).
GENERIC_ICONS = {
    "book": '<path d="M4 19V5a2 2 0 0 1 2-2h13v15H6a2 2 0 0 0 0 4h13"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
    "gear": ('<circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="6.5"/>'
             '<circle cx="12" cy="12" r="9" stroke-width="3" stroke-dasharray="3 4.06"/>'),
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.8"/><path d="M3 17l5-4 4 3 3-2 6 4"/>',
    "game": ('<path d="M6 8h12a4 4 0 0 1 4 4v1a3 3 0 0 1-5.2 2L16 14H8l-.8 1A3 3 0 0 1 2 13v-1a4 4 0 0 1 4-4z"/>'
             '<path d="M8 10.5v3M6.5 12h3"/><circle cx="16.5" cy="11" r=".6"/><circle cx="18.5" cy="13" r=".6"/>'),
    "robot": ('<rect x="5" y="8" width="14" height="11" rx="2.5"/><path d="M12 8V5"/><circle cx="12" cy="3.8" r="1.2"/>'
              '<circle cx="9" cy="13" r=".8"/><circle cx="15" cy="13" r=".8"/><path d="M9.5 16h5"/>'),
    "rocket": ('<path d="M12 2c3 2 5 6 5 10l-2.5 3h-5L7 12c0-4 2-8 5-10z"/><circle cx="12" cy="9" r="1.8"/>'
               '<path d="M7 12l-3 4 4 .5M17 12l3 4-4 .5M10.5 18.5L12 22l1.5-3.5"/>'),
    "star": '<path d="M12 2.5l2.8 6.5 6.7.5-5.2 4.5 1.7 7-6-3.7-6 3.7 1.7-7L2.5 9.5l6.7-.5z"/>',
    "heart": '<path d="M12 20.5s-8-4.8-8-10.3A4.3 4.3 0 0 1 12 7.8a4.3 4.3 0 0 1 8 2.4c0 5.5-8 10.3-8 10.3z"/>',
    "folder": '<path d="M3 6.5a2 2 0 0 1 2-2h4.5l2 2.5H19a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "music": '<path d="M9 18V5l11-2v13"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/>',
    "bolt": '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
    "chat": '<path d="M4 5h16v11H10l-5 4v-4H4z"/>',
    "camera": '<path d="M3 8h4l1.5-2.5h7L17 8h4v11H3z"/><circle cx="12" cy="13.5" r="3.5"/>',
    "shield": '<path d="M12 2.5l8 3v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10v-6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    "database": ('<path d="M4 6c0 2 3.6 3 8 3s8-1 8-3-3.6-3-8-3-8 1-8 3z"/><path d="M4 6v12c0 2 3.6 3 8 3s8-1 8-3V6"/>'
                 '<path d="M4 12c0 2 3.6 3 8 3s8-1 8-3"/>'),
}

_LOGO_KEYS = {k.lower(): k for k in LOGOS}
_GENERIC_KEYS = {k.lower(): k for k in GENERIC_ICONS}
_MIME = {"svg": "image/svg+xml", "png": "image/png", "jpg": "image/jpeg",
         "jpeg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}


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


def image_markup(mime, b64):
    return (f'<image href="data:{mime};base64,{b64}" x="-1" y="-1" width="26" height="26" '
            f'preserveAspectRatio="xMidYMid meet"/>')


def icon_markup(key, color):
    """SVG for one icon in a 24x24 box, or None if `key` is unknown."""
    if not key:
        return None
    if key.startswith("path:"):
        return f'<path d="{html.escape(key[5:].strip())}" fill="{color}"/>'
    if key.startswith("file:"):
        path = key[5:].strip()
        mime = _MIME.get(path.rsplit(".", 1)[-1].lower())
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError:
            print(f"warning: icon file not found: {path}", file=sys.stderr)
            return None
        if not mime:
            print(f"warning: unsupported icon type: {path}", file=sys.stderr)
            return None
        if len(raw) > 80_000:
            print(f"warning: {path} is large ({len(raw) // 1000} KB), the card gets heavy", file=sys.stderr)
        return image_markup(mime, base64.b64encode(raw).decode())
    low = key.lower()
    if low in _LOGO_KEYS:
        return LOGOS[_LOGO_KEYS[low]].replace("COL", color).replace("DRK", DARK)
    if low in _GENERIC_KEYS:
        body = GENERIC_ICONS[_GENERIC_KEYS[low]].replace("COL", color)
        return (f'<g fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" '
                f'stroke-linejoin="round">{body}</g>')
    return None


def describe(it, idx=0):
    """Work out the logo markup (or None) and the color for one repository."""
    name = it["name"]
    ov = {k.lower(): v for k, v in REPO_ICONS.items()}.get(name.lower(), {})
    if isinstance(ov, str):
        ov = {"icon": ov}
    color = visible(ov["color"]) if ov.get("color") else PALETTE[idx % len(PALETTE)]
    wanted = ov.get("icon") or it.get("icon")
    markup = icon_markup(wanted, color)
    if wanted and markup is None:
        print(f"warning: unknown icon '{wanted}' for {name}", file=sys.stderr)
    if markup is None and it.get("logo_data"):
        markup = image_markup(*it["logo_data"])     # logo.* found in the repo itself
    return markup, color                            # no logo in the repo -> None (only the ring)


# ---------------- data ----------------
def fetch(user, token):
    frag = ("name nameWithOwner createdAt primaryLanguage{name color} "
            "object(expression:\"HEAD:\"){... on Tree{entries{name type}}} "
            "languages(first:1,orderBy:{field:SIZE,direction:DESC}){nodes{name color}}")
    query = ("query($login:String!){user(login:$login){"
             "pinnedItems(first:6,types:REPOSITORY){nodes{... on Repository{%s}}}"
             "repositories(first:30,ownerAffiliations:OWNER,isFork:false,privacy:PUBLIC,"
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
    recent = [n for n in u["repositories"]["nodes"]
              if n and not (HIDE_PROFILE_REPO and n["name"].lower() == user.lower())]
    if SOURCE == "pinned" and pinned:
        candidates, kind = pinned, "featured"
    else:  # newest repos (the profile repo is shown unless HIDE_PROFILE_REPO is True)
        candidates, kind = recent, "newest"

    # walk from newest to oldest; repos without a logo are skipped (if REQUIRE_LOGO),
    # so they never use up one of the MAX_REPOS places
    picked = []
    for n in sorted(candidates, key=lambda x: x["createdAt"], reverse=True):
        if len(picked) >= MAX_REPOS:
            break
        top = (n.get("languages") or {}).get("nodes") or []
        lang = top[0] if top else (n.get("primaryLanguage") or {})  # most used language
        item = {
            "name": n["name"],
            "lang": lang.get("name"),
            "color": lang.get("color") or DEFAULT_COLOR,
        }
        entries = ((n.get("object") or {}).get("entries")) or []
        found = {e["name"].lower(): e["name"] for e in entries if e.get("type") == "blob"}
        for cand in LOGO_FILES:                       # first match in LOGO_FILES order
            if cand in found:
                data = fetch_logo(n["nameWithOwner"], found[cand], token)
                if data:
                    item["logo_data"] = data
                break
        has_logo = "logo_data" in item or n["name"] in REPO_ICONS   # own icon from REPO_ICONS counts too
        if REQUIRE_LOGO and not has_logo:
            continue
        picked.append((n["createdAt"], item))

    items = [it for _, it in sorted(picked, key=lambda x: x[0])]   # oldest -> newest
    return items, kind


def fetch_logo(nwo, filename, token):
    """Download one logo file of a repo -> (mime, base64) or None."""
    ext = filename.rsplit(".", 1)[-1].lower()
    mime = _MIME.get(ext)
    req = urllib.request.Request(
        f"https://api.github.com/repos/{nwo}/contents/{filename}",
        headers={"Authorization": f"bearer {token}", "Accept": "application/vnd.github+json",
                 "User-Agent": "project-timeline"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            info = json.load(r)
        if info.get("size", 0) > MAX_LOGO_KB * 1000:
            print(f"warning: {nwo}/{filename} is {info['size'] // 1000} KB, skipped "
                  f"(limit {MAX_LOGO_KB} KB)", file=sys.stderr)
            return None
        b64 = "".join((info.get("content") or "").split())
        return (mime, b64) if mime and b64 else None
    except Exception as exc:                          # a missing logo must never break the card
        print(f"warning: could not read {nwo}/{filename}: {exc}", file=sys.stderr)
        return None


def demo():
    return [
        {"name": "mohammadmahdighaedamin", "lang": "Python", "color": "#3572A5"},
        {"name": "proxy-extension", "lang": "JavaScript", "color": "#f1e05a"},
        {"name": "widgetpanel", "lang": "HTML", "color": "#e34c26"},
        {"name": "rust-cli-tool", "lang": "Rust", "color": "#dea584"},
        {"name": "portfolio-site", "lang": "TypeScript", "color": "#3178c6"},
        {"name": "dotfiles", "lang": "Shell", "color": "#89e051"},
        {"name": "swift-app", "lang": "Swift", "color": "#F05138"},
        {"name": "notes-app", "lang": None, "color": "#ffb86b"},
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


# ---------------- logo animations ----------------
def _kt(kts):
    return ";".join(f"{k:.3f}" for k in kts)


def _cycle(tag, attr, values, kts, dur, begin, spline=None, typ=None):
    """A looping animation; `begin` is negative so every logo is out of step."""
    cm = ""
    if spline:
        cm = f' calcMode="spline" keySplines="{";".join([spline] * (len(kts) - 1))}"'
    t = f' type="{typ}"' if typ else ""
    return (f'<{tag} attributeName="{attr}"{t} values="{";".join(values)}" keyTimes="{_kt(kts)}" '
            f'dur="{dur}s" begin="-{fmt(begin)}s" repeatCount="indefinite"{cm}/>')


# ---------------- synchronized beat: every logo uses the SAME timeline ----------------
_UP = "0.2 0.7 0.3 1"        # fast start, soft landing
_DOWN = "0.4 0 0.4 1"        # smooth return
_SMOOTH = "0.45 0 0.55 1"    # slow in, slow out


def _beat_points(kind, peak):
    """One beat as [(seconds from the start of the beat, scale), ...]; first value = resting size."""
    a = peak - 1.0
    if kind == "lubdub":
        return [(0, 1), (0.14, peak), (0.30, 1 + 0.1 * a), (0.44, 1 + 0.65 * a), (0.90, 1)]
    if kind == "pop":
        return [(0, 1), (0.12, peak), (0.30, 0.92), (0.44, 1.06), (0.60, 1)]
    return [(0, SYNC_LOW), (SYNC_PERIOD / 2, peak), (SYNC_PERIOD, SYNC_LOW)]   # breathe: small -> big -> small


def _sync_anim(tag, attr, points, T, up=_UP, down=_DOWN, typ=None):
    """Repeat one beat every SYNC_PERIOD seconds on the card's own timeline.
    Every logo gets exactly the same times, so they all beat at the same moment."""
    rest = points[0][1]
    length = points[-1][0]
    times, vals = [0.0], [rest]
    k = 0
    while True:
        t0 = SYNC_START + k * SYNC_PERIOD
        if t0 + length > T - FADE + 0.2:        # never start a beat that would run into the fade-out
            break
        for dt, v in points:
            times.append(t0 + dt)
            vals.append(v)
        k += 1
    times.append(T)
    vals.append(rest)
    spl = []
    for j in range(len(vals) - 1):
        spl.append("0 0 1 1" if abs(vals[j + 1] - vals[j]) < 1e-9 else (up if vals[j + 1] > vals[j] else down))
    t = f' type="{typ}"' if typ else ""
    return (f'<{tag} attributeName="{attr}"{t} values="{";".join(fmt(v) for v in vals)}" '
            f'keyTimes="{key_times(times, T)}" calcMode="spline" keySplines="{";".join(spl)}" '
            f'dur="{T:.3f}s" repeatCount="indefinite"/>')


_RING_OUT = "0.25 0.5 0.4 1"      # the ring spreads out fast at first, then slows down
BREATH_IN = 0.45                  # share of one breath spent breathing in (the rest is breathing out)


def _free_anim(tag, attr, values, kts, spl, typ=None):
    """Runs forever with the SAME clock for every logo and ring (so they all breathe together),
    one cycle = one breath = SYNC_PERIOD seconds."""
    t = f' type="{typ}"' if typ else ""
    return (f'<{tag} attributeName="{attr}"{t} values="{";".join(fmt(v) for v in values)}" '
            f'keyTimes="{";".join(f"{x:.3f}" for x in kts)}" calcMode="spline" '
            f'keySplines="{";".join(spl)}" dur="{SYNC_PERIOD}s" repeatCount="indefinite"/>')


def _breath_scale(peak, low=None):
    low = SYNC_LOW if low is None else low
    return _free_anim("animateTransform", "transform", [low, peak, low], [0, BREATH_IN, 1],
                      [_SMOOTH, _SMOOTH], "scale")


def _breath_ring(color, R):
    """ONE ring per breath: starts when the breath-in starts and fades out as the breath ends."""
    return (f'<circle r="{fmt(R)}" fill="none" stroke="{color}" stroke-width="1.5" opacity="0">'
            + _free_anim("animate", "r", [R, R * 1.7], [0, 1], [_RING_OUT])
            + _free_anim("animate", "opacity", [0, .75, 0], [0, .22, 1], [_UP, _SMOOTH])
            + '</circle>')


def _empty_core(color, ring):
    """Repo without a logo: just the ring; its soft core breathes (only in the breathe styles)."""
    r = ring * 0.66
    if PULSE_STYLE not in ("sync-breathe", "sync-breathe-ring"):
        return f'<circle r="{fmt(r)}" fill="{color}" fill-opacity=".22"/>'
    peak = min(SYNC_PEAK, (ring - 1.8) / r)
    out = (f'<circle r="{fmt(r)}" fill="{color}" fill-opacity=".16">'
           + _breath_scale(peak)
           + _free_anim("animate", "fill-opacity", [.16, .42, .16], [0, BREATH_IN, 1], [_SMOOTH, _SMOOTH])
           + '</circle>')
    if PULSE_STYLE == "sync-breathe-ring":
        out = _breath_ring(color, ring) + out
    return out


def _sync_fx(style, color, inner, R, T, k):
    if style == "sync-pop" or style == "sync-ring":
        kind, up, down = "pop", _UP, _DOWN
    elif style in ("sync-breathe", "sync-breathe-ring"):
        kind, up, down = "breathe", _SMOOTH, _SMOOTH
    else:                                                   # sync-heartbeat / sync-glow
        kind, up, down = "lubdub", _UP, _DOWN
    # the biggest the logo may get: its farthest point must stay inside the dashed circle
    # a picture logo (logo.png ...) is a full square, its corners reach further than any built-in shape
    max_r = 18.4 if "<image" in inner else LOGO_MAX_R
    peak = min(SYNC_PEAK, (R - 1.8) / (max_r * k))
    low = min(SYNC_LOW, peak / 1.5)                         # keeps the grow/shrink clearly visible
    if kind == "breathe":
        anim_xml = _breath_scale(peak, low)                      # same clock for all logos, any card length
    else:
        anim_xml = _sync_anim("animateTransform", "transform", _beat_points(kind, peak), T, up, down, "scale")
    logo = ('<g clip-path="url(#beatClip)"><g filter="url(#glowSoft)"><g>'      # clip = hard stop at the ring
            + anim_xml + inner + '</g></g></g>')
    extra = ""
    if style == "sync-glow":                                # soft color flash that follows the beat
        a = SYNC_PEAK - 1.0
        op = [(0, 0), (0.14, .85), (0.30, .2), (0.44, .6), (0.90, 0)]
        extra = (f'<circle r="{fmt(R * 0.95)}" fill="{color}" filter="url(#glow)" opacity="0">'
                 + _sync_anim("animate", "opacity", op, T) + '</circle>')
    if style == "sync-breathe-ring":                        # one ring per breath, tuned to the breath
        extra = _breath_ring(color, R)
    if style == "sync-ring":                                # a ring spreading out, once per beat
        d = 0.65
        r_pts = [(0, R), (0.02, R), (d, R * 1.75), (d + 0.01, R)]
        o_pts = [(0, 0), (0.02, .9), (d, 0), (d + 0.01, 0)]
        extra = (f'<circle r="{fmt(R)}" fill="none" stroke="{color}" stroke-width="1.8" opacity="0">'
                 + _sync_anim("animate", "r", r_pts, T, _UP, _UP)
                 + _sync_anim("animate", "opacity", o_pts, T, _UP, _SMOOTH) + '</circle>')
    return extra + logo


_BEAT_KT = [0, .09, .20, .30, .42, 1]       # lub-dub: two quick beats, then a rest


def logo_fx(style, i, color, logo, ring, k, T=10.0, tb=None):
    """The logo plus its animation. Returns SVG for the middle of a node."""
    inner = f'<g transform="scale({fmt(k)}) translate(-12 -12)">{logo}</g>'
    R = ring
    plain = f'<g filter="url(#glowSoft)">{inner}</g>'
    if style.startswith("sync-"):                  # all logos beat together
        return _sync_fx(style, color, inner, R, T, k)
    if style == "heartbeat":                       # ONE slow beat at time `tb`, then rest
        if tb is None:
            return plain
        times = [0, tb, tb + BEAT_UP, tb + BEAT_UP + BEAT_DOWN, T]
        vals = ["1", "1", fmt(BEAT_SCALE), "1", "1"]
        sp = "0 0 1 1;0.15 0.85 0.3 1;0.4 0 0.25 1;0 0 1 1"
        return ('<g filter="url(#glowSoft)"><g>'
                f'<animateTransform attributeName="transform" type="scale" values="{";".join(vals)}" '
                f'keyTimes="{key_times(times, T)}" calcMode="spline" keySplines="{sp}" '
                f'dur="{T:.3f}s" repeatCount="indefinite"/>'
                + inner + '</g></g>')
    if style == "flash":                           # a lightning flash: halo + white wash
        D = 2.2
        b = (i * 0.53) % D
        kts = [0, .30, .33, .37, .40, .62, 1]
        halo = (f'<circle r="{fmt(R * 1.1)}" fill="{color}" filter="url(#glow)" opacity="0">'
                + _cycle("animate", "opacity", ["0", "0", ".85", ".15", ".7", "0", "0"], kts, D, b)
                + '</circle>')
        wash = (f'<circle r="{fmt(R * 0.7)}" fill="#ffffff" filter="url(#glow)" opacity="0">'
                + _cycle("animate", "opacity", ["0", "0", ".8", ".1", ".55", "0", "0"], kts, D, b)
                + '</circle>')
        return halo + plain + wash
    if style == "heartbeat-glow":                  # heartbeat + glow + shock rings
        D = 1.5
        b = (i * 0.37) % D
        glow = (f'<circle r="{fmt(R * 0.9)}" fill="{color}" filter="url(#glow)" opacity="0">'
                + _cycle("animate", "opacity", ["0", ".7", "0", ".5", "0", "0"], _BEAT_KT, D, b)
                + '</circle>')
        rings = ""
        for r_end, op, t_on, t_off in ((1.75, .8, .09, .5), (1.5, .55, .30, .62)):
            rings += (f'<circle r="{fmt(R)}" fill="none" stroke="{color}" stroke-width="1.4" opacity="0">'
                      + _cycle("animate", "r", [fmt(R), fmt(R), fmt(R * r_end), fmt(R * r_end)],
                               [0, t_on, t_off, 1], D, b)
                      + _cycle("animate", "opacity", ["0", str(op), "0", "0"], [0, t_on, t_off, 1], D, b)
                      + '</circle>')
        return (glow + rings + '<g filter="url(#glowSoft)"><g>'
                + _cycle("animateTransform", "transform", ["1", "1.14", "1", "1.09", "1", "1"],
                         _BEAT_KT, D, b, "0.2 0.8 0.3 1", "scale")
                + inner + '</g></g>')
    if style == "neon":                            # broken-neon flicker, no scaling
        D = 3.2
        b = (i * 0.9) % D
        kts = [0, .50, .52, .55, .57, .61, .63, .67, .69, .72, 1]
        glow = (f'<circle r="{fmt(R * 0.95)}" fill="{color}" filter="url(#glow)" opacity="0">'
                + _cycle("animate", "opacity",
                         ["0", "0", ".8", ".1", ".6", ".1", ".9", ".1", ".5", "0", "0"], kts, D, b)
                + '</circle>')
        flick = ('<g filter="url(#glowSoft)"><g>'
                 + _cycle("animate", "opacity",
                          ["1", "1", ".2", "1", ".45", "1", ".1", "1", ".6", "1", "1"], kts, D, b)
                 + inner + '</g></g>')
        return glow + flick
    return plain


def build(items, kind="featured"):
    n = len(items)
    x0, x1 = GRID_X, W - GRID_X
    span = x1 - x0
    shown = max(1, min(n, VISIBLE))             # projects visible at once
    slot = span / shown                         # width of one project slot
    extra = max(0, n - shown)                   # how many steps the timeline moves forward
    ring = min(RING_R, slot * 0.36)

    end = LINE_START + LINE_DUR                 # the line has crossed the card
    first_shift = end + 0.6

    def shift_start(s):                         # s = 1..extra
        return first_shift + (s - 1) * (SHIFT + PAUSE)

    last_motion = (shift_start(extra) + SHIFT) if extra else end + 0.8
    T = last_motion + HOLD + FADE
    seq_start = last_motion + 0.5
    if PULSE_STYLE == "heartbeat" and BEAT_MODE == "sequence":
        T = max(T, seq_start + (shown - 1) * BEAT_STEP + BEAT_UP + BEAT_DOWN + 0.6 + FADE)

    font = "Segoe UI, Ubuntu, Helvetica, Arial, sans-serif"
    mono = "Consolas, 'SF Mono', Menlo, monospace"

    out = []
    a = out.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
      f'role="img" aria-label="Project timeline">')
    a(f"""<defs>
<clipPath id="card"><rect x="6" y="6" width="{W - 12}" height="{H - 12}" rx="22"/></clipPath>
<clipPath id="track"><rect x="{x0 - 14}" y="30" width="{span + 28}" height="{H - 60}"/></clipPath>
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
<clipPath id="beatClip"><circle r="{fmt(ring - 0.9)}"/></clipPath>
<filter id="glowSoft" x="-60%" y="-60%" width="220%" height="220%">
<feGaussianBlur stdDeviation="1.3" result="b"/>
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
      f'fill="#ffffff">My Project Journey</text>')
    a(f'<text x="{GRID_X}" y="92" font-family="{font}" font-size="13" font-weight="600" fill="#ffffff">'
      f'From my first project to my latest</text>')

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
        a(f'<rect x="{x0}" y="{LINE_Y - 1}" width="0" height="2" rx="1" fill="url(#lineGrad)">')
        a(anim("width", [0, 0, span, span], [0, LINE_START, end, T], T))
        a("</rect>")
        a(f'<circle cx="{x0}" cy="{LINE_Y}" r="3.2" fill="#ffffff" filter="url(#glow)" opacity="0">')
        a(anim("cx", [x0, x0, x1, x1], [0, LINE_START, end, T], T))
        a(anim("opacity", [0, 1, 1, 0, 0], [0, LINE_START, end, end + 0.3, T], T))
        a("</circle>")

    # ---- the "world": every project lives here; it slides left step by step ----
    a('<g clip-path="url(#track)"><g>')
    if extra:
        times, vals = [0], ["0 0"]
        for s in range(1, extra + 1):
            times += [shift_start(s), shift_start(s) + SHIFT]
            vals += [f"{fmt(-(s - 1) * slot)} 0", f"{fmt(-s * slot)} 0"]
        times.append(T)
        vals.append(vals[-1])
        splines = ";".join(
            "0 0 1 1" if vals[k] == vals[k + 1] else "0.45 0 0.2 1" for k in range(len(vals) - 1)
        )
        a(f'<animateTransform attributeName="transform" type="translate" values="{";".join(vals)}" '
          f'keyTimes="{key_times(times, T)}" calcMode="spline" keySplines="{splines}" '
          f'dur="{T:.3f}s" repeatCount="indefinite"/>')

    # dashed ring: RING_DASHES dashes with equal gaps around the circle
    circ = 2 * math.pi * ring
    period = circ / max(1, RING_DASHES)
    dash_on, dash_off = period * 0.55, period * 0.45
    logo_scale = ring * 1.15 / 24

    for i, it in enumerate(items):
        x = x0 + slot * (i + 0.5)                   # position in the world
        if i < shown:                               # first window: appears as the line reaches it
            ta = LINE_START + LINE_DUR * ((i + 0.5) * slot) / span
            fade_in, tp = 0.3, ta
        else:                                       # later ones: slide in from the right
            ta = shift_start(i - shown + 1)
            fade_in, tp = SHIFT, ta + SHIFT * 0.5
        te = shift_start(i + 1) if i + 1 <= extra else None   # when it slides out on the left

        logo, color = describe(it, i)
        above = i % 2 == 0

        # keep the name inside the card and away from the neighbours on the same side
        half = min(slot * 0.95, slot * 0.5 + GRID_X - 36)
        name = clip(it["name"], max(6, int(2 * half / 8.2)))

        # whole project: visible only while it is inside the window
        ot, ov = [0, ta, ta + fade_in], [0, 0, 1]
        if te is not None:
            ot += [te, te + SHIFT]
            ov += [1, 0]
        ot.append(T)
        ov.append(ov[-1])
        a('<g opacity="0">')
        a(anim("opacity", ov, ot, T))

        # node: ping + dashed ring + soft core + breathing logo
        a(f'<g transform="translate({fmt(x)},{LINE_Y})">')
        a(f'<animateTransform attributeName="transform" type="scale" additive="sum" '
          f'values="0.5;0.5;1;1" keyTimes="{key_times([0, tp, tp + 0.5, T], T)}" calcMode="spline" '
          f'keySplines="0 0 1 1;0.2 0.7 0.3 1;0 0 1 1" dur="{T:.3f}s" repeatCount="indefinite"/>')
        if PULSE_STYLE != "sync-breathe-ring":      # (that style has its own ring, tuned to the breath)
            a(f'<circle r="{fmt(ring * 0.75)}" fill="none" stroke="{color}" stroke-width="1.2" opacity="0">'
              f'<animate attributeName="r" values="{fmt(ring * 0.75)};{fmt(ring * 1.65)}" dur="2.6s" repeatCount="indefinite"/>'
              f'<animate attributeName="opacity" values="0.6;0" dur="2.6s" repeatCount="indefinite"/></circle>')
        a(f'<circle r="{fmt(ring)}" fill="#07030f" fill-opacity=".7"/>')
        a(f'<circle r="{fmt(ring)}" fill="none" stroke="{color}" stroke-width="1.6" '
          f'stroke-dasharray="{fmt(dash_on)} {fmt(dash_off)}" stroke-linecap="round">'
          f'<animateTransform attributeName="transform" type="rotate" values="0;360" dur="14s" '
          f'repeatCount="indefinite"/></circle>')
        if logo is None:                            # no logo in the repo: only the ring
            a(_empty_core(color, ring))
        else:
            a(f'<circle r="{fmt(ring * 0.66)}" fill="{color}" fill-opacity=".22"/>')
            if BEAT_MODE == "sequence":             # final window beats left -> right, one at a time
                pos = i - (n - shown)
                tb = seq_start + pos * BEAT_STEP if pos >= 0 else None
            else:                                   # "arrive": beat once right after appearing
                tb = max(tp + 0.5, ta + fade_in) + 0.1
            a(logo_fx(PULSE_STYLE, i, color, logo, ring, logo_scale, T, tb))
        a("</g>")

        # project name (same color as its ring), fades in right after the node
        y_name = LINE_Y - 30 if above else LINE_Y + 42
        a('<g opacity="0">')
        a(anim("opacity", [0, 0, 1, 1], [0, tp + 0.2, tp + 0.7, T], T))
        a(f'<text x="{fmt(x)}" y="{y_name}" text-anchor="middle" font-family="{mono}" font-size="13" '
          f'font-weight="700" fill="{color}">{html.escape(name)}</text>')
        a("</g>")
        a("</g>")
    a("</g></g>")

    # footer
    if items:
        more = f" · showing {shown} at a time" if extra else ""
        a(f'<text x="{GRID_X}" y="{LINE_Y + 84}" font-family="{font}" font-size="11" fill="#ffffff" '
          f'fill-opacity=".75">{n} {kind} project{"" if n == 1 else "s"}{more} · '
          f'from oldest to newest</text>')

    a("</g>")
    a("</svg>")
    return "\n".join(out)


def main():
    global PULSE_STYLE, OUT
    for arg in sys.argv[1:]:                        # optional: --pulse=sync-pop  --out=assets/x.svg
        if arg.startswith("--pulse="):
            PULSE_STYLE = arg.split("=", 1)[1]
        elif arg.startswith("--out="):
            OUT = arg.split("=", 1)[1]
    if "--demo" in sys.argv:
        items, kind = demo()
        if "--few" in sys.argv:
            items = items[:3]
    else:
        user = os.environ.get("GITHUB_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER")  # (set by GitHub Actions)
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
