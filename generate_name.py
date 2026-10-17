#!/usr/bin/env python3
"""
"Name" banner card, same look as the other cards (Nightmare background).

Your GitHub profile picture (round) on the left, and your GitHub username on the right.
The username is typed letter by letter, waits a while, is erased and typed again, forever.
The font is the same one the other cards use. The blinking cursor has the same purple as
the beam of the airplane in the contribution card.

Which picture is used (first one that works):
  1. your GitHub profile picture (downloaded by the script, shown exactly as it is)
  2. logo.svg / logo.png / logo.webp / logo.jpg in the repo root
  3. the first letter of your name
The name comes from GITHUB_USER (set by the workflow).

Usage:
  GITHUB_USER=yourname GITHUB_TOKEN=... python generate_name.py     # real name + picture
  python generate_name.py --demo                                    # sample name
  python generate_name.py --demo --morse all                        # all 4 Morse variants (A, B, C, D)
Output: assets/name-typing.svg   (with --morse all: assets/name-typing-A.svg ... -D.svg)
"""
import base64
import html
import json
import os
import sys
import urllib.request

OUT = "assets/name-typing.svg"

W = 782                 # same width as the other cards
H = 288                 # card height (taller than before: the Morse line lives under the picture)
CY = 112                # vertical center of the picture and the name
PIC_R = 62              # radius of the round picture (bigger = more detail)
RING_GAP = 6            # space between the picture and its ring
PIC_CX = 120            # center x of the picture (keeps ~24px free space to the inner frame)
TEXT_X = 222            # where the name starts
MAX_FONT = 40           # biggest font size (long names are made smaller so they always fit)
MIN_FONT = 14
CHAR_W = 0.62           # average letter width / font size, only used to make long names fit

USE_GITHUB_AVATAR = True   # True = use your GitHub profile picture (falls back to logo.*)
BOOST_PICTURE = False      # True = make thin / dark pictures (like neon outlines) bolder and brighter so they stay
                           # clear in the small circle. Needs Pillow (pip install pillow); skipped without it.
                           # Off by default: your picture is shown exactly as it is.

# ---- typing timing (seconds) ----
TYPE_STEP = 0.12        # time per typed letter           (bigger = slower typing)
FADE = 0.09             # each letter fades in / out this long (bigger = softer, 0 = hard jump)
HOLD = 3.5              # the finished name stays this long
ERASE_STEP = 0.05       # time per erased letter
GAP = 1.0               # empty pause before typing again
CURSOR_BLINK = 1.0      # cursor blink period

CURSOR_COLOR = "#a855f7"   # same purple as the airplane beam in the contribution card
FONT = "Segoe UI, Ubuntu, Helvetica, Arial, sans-serif"   # same font as the other cards

# ---- Morse subtitle (under the picture and the name) ----
MORSE_TEXT = ".. -- -. .. --. .... - -- .- .-. ."   # letters are separated by a space
MORSE_STYLE = "B"       # "A" typed text | "B" signal lamps | "C" karaoke + decoded letters | "D" telegraph wave | "off"
MORSE_UNIT = 0.09       # seconds of one Morse "dot" (dash = 3 units)  (bigger = slower)
MORSE_DELAY = 0.4       # wait after the name is fully typed, then the Morse starts
MORSE_LINGER = 1.6      # the finished Morse stays visible this long, then fades out
MORSE_FADE = 0.5        # fade-out time
MORSE_PAUSE = 0.8       # extra empty pause at the end of the cycle, then everything repeats
SUB_Y = 218             # vertical center of the Morse line
MORSE_COLOR = "#a855f7"  # same purple as the cursor
MORSE_SOFT = "#e9d5ff"   # soft light purple for finished symbols
MONO = "Consolas, 'DejaVu Sans Mono', 'Courier New', monospace"
DOT_CHAR, DASH_CHAR = "\u2022", "\u2014"          # how dots and dashes are drawn in the text variants (A, C)
_DECODE = {".-": "A", "-...": "B", "-.-.": "C", "-..": "D", ".": "E", "..-.": "F", "--.": "G",
           "....": "H", "..": "I", ".---": "J", "-.-": "K", ".-..": "L", "--": "M", "-.": "N",
           "---": "O", ".--.": "P", "--.-": "Q", ".-.": "R", "...": "S", "-": "T", "..-": "U",
           "...-": "V", ".--": "W", "-..-": "X", "-.--": "Y", "--..": "Z",
           "-----": "0", ".----": "1", "..---": "2", "...--": "3", "....-": "4",
           ".....": "5", "-....": "6", "--...": "7", "---..": "8", "----.": "9"}

LOGO_FILES = ("logo.svg", "logo.png", "logo.webp", "logo.jpg", "logo.jpeg")   # looked up in the repo root
MAX_LOGO_KB = 400       # bigger files are skipped (they would make the card heavy)
_MIME = {"svg": "image/svg+xml", "png": "image/png", "jpg": "image/jpeg",
         "jpeg": "image/jpeg", "webp": "image/webp"}

# ---- banner colors, same as the other cards ----
STOPS = [(0.0, "#ff4fb8"), (0.35, "#c04ee8"), (0.65, "#7a5cf5"), (1.0, "#1f6bff")]


def stops_xml():
    return "".join(f'<stop offset="{u}" stop-color="{c}"/>' for u, c in STOPS)


def fmt(v):
    return f"{v:.3f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


# ---------------- picture ----------------
def fetch_avatar(user, token):
    """Your GitHub profile picture -> (mime, base64) or None."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "name-card"}
    if token:
        headers["Authorization"] = f"bearer {token}"
    try:
        req = urllib.request.Request(f"https://api.github.com/users/{user}", headers=headers)
        with urllib.request.urlopen(req, timeout=20) as r:
            url = json.load(r)["avatar_url"]
        url += ("&" if "?" in url else "?") + "s=512"          # 512x512: sharp even on high-resolution screens
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "name-card"}),
                                    timeout=20) as r:
            mime = (r.headers.get("Content-Type") or "image/png").split(";")[0].strip()
            data = r.read()
        return mime, base64.b64encode(data).decode()
    except Exception as exc:                                    # the card must never break
        print(f"warning: could not load the GitHub profile picture: {exc}", file=sys.stderr)
        return None


def boost(picture):
    """Thicken thin bright lines + a little brighter/more colorful, so the picture stays clear
    in a small circle. Returns the same (mime, base64) form. Needs Pillow, else unchanged."""
    mime, b64 = picture
    if mime == "image/svg+xml":
        return picture
    try:
        import io
        from PIL import Image, ImageEnhance, ImageFilter
    except ImportError:
        print("warning: Pillow is not installed, picture not enhanced (pip install pillow)", file=sys.stderr)
        return picture
    try:
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        img = img.convert("RGBA")
        alpha = img.getchannel("A")
        rgb = img.convert("RGB")
        rgb.thumbnail((320, 320), Image.LANCZOS)                 # also keeps the SVG light
        alpha = alpha.resize(rgb.size, Image.LANCZOS)
        rgb = rgb.filter(ImageFilter.MaxFilter(3))
        rgb = ImageEnhance.Brightness(rgb).enhance(1.2)
        rgb = ImageEnhance.Color(rgb).enhance(1.2)
        rgb.putalpha(alpha)
        buf = io.BytesIO()
        rgb.save(buf, "PNG", optimize=True)
        return "image/png", base64.b64encode(buf.getvalue()).decode()
    except Exception as exc:                                     # the card must never break
        print(f"warning: could not enhance the picture: {exc}", file=sys.stderr)
        return picture


def load_logo(files=LOGO_FILES):
    """First existing file of `files` in the repo root -> (mime, base64) or None."""
    for name in files:
        if os.path.isfile(name):
            size = os.path.getsize(name)
            if size > MAX_LOGO_KB * 1000:
                print(f"warning: {name} is {size // 1000} KB, skipped (limit {MAX_LOGO_KB} KB)",
                      file=sys.stderr)
                continue
            with open(name, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode()
            return _MIME[name.rsplit(".", 1)[-1].lower()], b64
    return None


# ---------------- morse subtitle ----------------
def morse_schedule(text, u):
    """-> (groups, schedule, total). schedule[g] = [(start, length, '.' or '-'), ...] in seconds.
    Real Morse timing: dot = 1 unit, dash = 3, gap inside a letter = 1, gap between letters = 3."""
    groups = text.split()
    sched, t = [], 0.0
    for gi, g in enumerate(groups):
        syms = []
        for si, s in enumerate(g):
            d = u if s == "." else 3 * u
            syms.append((t, d, s))
            t += d
            if si < len(g) - 1:
                t += u
        sched.append(syms)
        if gi < len(groups) - 1:
            t += 3 * u
    return groups, sched, t


def anim(attr, T, v0, changes):
    """One <animate> over the whole cycle T. Starts at v0; changes = [(time, new_value, fade_seconds), ...]
    in time order. Whatever the value is at the end of the cycle must equal v0 (so the loop is seamless)."""
    pts, cur = [(0.0, v0)], v0
    for t, v, dur in changes:
        t = min(max(t, pts[-1][0]), T)
        pts.append((t, cur))
        pts.append((min(max(t + dur, t), T), v))
        cur = v
    pts.append((T, cur))
    kt = ";".join(f"{t / T:.5f}" for t, _ in pts)
    vals = ";".join(f"{v:g}" for _, v in pts)
    return (f'<animate attributeName="{attr}" values="{vals}" keyTimes="{kt}" dur="{T:.3f}s" '
            f'calcMode="linear" repeatCount="indefinite"/>')


def _wrap(inner, ts0, te, T):
    """Whole Morse line: fades in just before it starts, fades out at `te`."""
    fade = anim("opacity", T, 0, [(max(0.0, ts0 - 0.2), 1, 0.2), (te, 0, MORSE_FADE)])
    return [f'<g opacity="0">{fade}'] + inner + ["</g>"]


def _glyphs(group):
    return "".join(DOT_CHAR if c == "." else DASH_CHAR for c in group)


# A: the dots and dashes are typed one by one, with the real Morse rhythm
def _morse_A(m, ts0, te, T):
    groups, sched, D = m
    tr = te + MORSE_FADE + 0.03                      # everything is invisible now: safe to reset
    spans = []
    for gi, syms in enumerate(sched):
        for t, d, s in syms:
            an = anim("fill-opacity", T, 0, [(ts0 + t, 1, 0.05), (tr, 0, 0.01)])
            spans.append(f'<tspan fill-opacity="0">{an}{DOT_CHAR if s == "." else DASH_CHAR}</tspan>')
        if gi < len(sched) - 1:
            spans.append("<tspan>&#160;</tspan>")
    txt = (f'<text x="{fmt(W / 2)}" y="{SUB_Y + 7}" text-anchor="middle" font-family="{MONO}" font-size="22" '
           f'font-weight="700" letter-spacing="6" fill="{MORSE_SOFT}">{"".join(spans)}</text>')
    return _wrap([txt], ts0, te, T)


# B: a row of signal lamps; each lamp flashes for exactly as long as its dot / dash
def _morse_B(m, ts0, te, T):
    groups, sched, D = m
    tr = te + MORSE_FADE + 0.03
    h, dot_w, dash_w, ig, lg = 8, 8, 26, 7, 18
    items, x = [], 0.0
    for gi, syms in enumerate(sched):
        for si, (t, d, s) in enumerate(syms):
            items.append((x, dot_w if s == "." else dash_w, t, d))
            x += (dot_w if s == "." else dash_w) + (ig if si < len(syms) - 1 else 0)
        if gi < len(sched) - 1:
            x += lg
    total = x
    sc = min(1.0, 620 / total)
    base, settled, flash = [], [], []
    for x, w, t, d in items:
        r = f'x="{fmt(x)}" y="{-h // 2}" width="{w}" height="{h}" rx="{h // 2}"'
        s0 = ts0 + t
        base.append(f'<rect {r} fill="{MORSE_SOFT}" fill-opacity=".16"/>')
        settled.append(f'<rect {r} fill="{MORSE_COLOR}" opacity="0">'
                       f'{anim("opacity", T, 0, [(s0, 1, 0.03), (tr, 0, 0.01)])}</rect>')
        flash.append(f'<rect {r} fill="#ffe9fb" opacity="0" filter="url(#mglow)">'
                     f'{anim("opacity", T, 0, [(s0, 1, 0.02), (s0 + d, 0, 0.15)])}</rect>')
    defs = (f'<defs><filter id="mglow" filterUnits="userSpaceOnUse" x="-20" y="-24" width="{fmt(total + 40)}" '
            f'height="48"><feGaussianBlur stdDeviation="3.2" result="b"/>'
            f'<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>')
    g = (f'<g transform="translate({fmt(W / 2)} {SUB_Y}) scale({sc:.4f}) translate({fmt(-total / 2)} 0)">'
         + "".join(base) + "".join(settled) + "".join(flash) + "</g>")
    return [defs] + _wrap([g], ts0, te, T)


# C: subtitle / karaoke style. Each letter's code lights up purple while it "plays",
#    then the decoded letter appears under it.
def _morse_C(m, ts0, te, T):
    groups, sched, D = m
    tr = te + MORSE_FADE + 0.03
    N = len(groups)
    maxlen = max(len(g) for g in groups)
    fs, ls = 17.0, 3.0
    colw = maxlen * (fs * 0.6 + ls) + 7
    if colw * N > 660:                               # long texts: shrink so they always fit
        k = 660 / (colw * N)
        fs, ls, colw = fs * k, ls * k, colw * k
    out = []
    for i, (g, syms) in enumerate(zip(groups, sched)):
        x = fmt(W / 2 + (i - (N - 1) / 2) * colw)
        gs = ts0 + syms[0][0]
        ge = ts0 + syms[-1][0] + syms[-1][1]
        txt = _glyphs(g)
        common = (f'x="{x}" y="{SUB_Y - 2}" text-anchor="middle" font-family="{MONO}" font-size="{fs:.2f}" '
                  f'font-weight="700" letter-spacing="{ls:.2f}"')
        out.append(f'<text {common} fill="{MORSE_SOFT}" fill-opacity=".22">{txt}</text>')
        out.append(f'<text {common} fill="{MORSE_COLOR}" opacity="0">'
                   f'{anim("opacity", T, 0, [(gs, 1, 0.04), (ge, 0, 0.05)])}{txt}</text>')
        out.append(f'<text {common} fill="{MORSE_SOFT}" opacity="0">'
                   f'{anim("opacity", T, 0, [(ge, 1, 0.05), (tr, 0, 0.01)])}{txt}</text>')
        out.append(f'<text x="{x}" y="{SUB_Y + 24}" text-anchor="middle" font-family="{FONT}" font-size="20" '
                   f'font-weight="700" fill="#ffffff" opacity="0">'
                   f'{anim("opacity", T, 0, [(ge, 1, 0.2), (tr, 0, 0.01)])}{html.escape(_DECODE.get(g, "?"))}</text>')
    return _wrap(out, ts0, te, T)


# D: telegraph / oscilloscope line: the signal is drawn from left to right, a bright scan line leads the way.
#    The width of every pulse is proportional to its real Morse duration.
def _morse_D(m, ts0, te, T):
    groups, sched, D = m
    tr = te + MORSE_FADE + 0.03
    wd = 600.0
    x0 = W / 2 - wd / 2
    px = wd / D
    yl, yh = SUB_Y + 9, SUB_Y - 13
    d = [f"M{x0:.2f} {yl}"]
    for syms in sched:
        for t, dur, s in syms:
            d.append(f"H{x0 + t * px:.2f}V{yh}H{x0 + (t + dur) * px:.2f}V{yl}")
    d.append(f"H{x0 + wd:.2f}")
    path = "".join(d)
    run = [(ts0, 1, D), (tr, 0, 0.01)]
    defs = (f'<defs><clipPath id="mclip"><rect x="{x0 - 8:.2f}" y="{SUB_Y - 34}" width="0" height="68">'
            f'{anim("width", T, 0, [(ts0, wd + 16, D), (tr, 0, 0.01)])}</rect></clipPath></defs>')
    scan = (f'<rect x="{x0 - 8:.2f}" y="{SUB_Y - 22}" width="2" height="44" rx="1" fill="#ffe9fb" opacity="0">'
            f'{anim("x", T, x0 - 8, [(ts0, x0 + wd + 8, D), (tr, x0 - 8, 0.01)])}'
            f'{anim("opacity", T, 0, [(ts0, 1, 0.05), (ts0 + D, 0, 0.25)])}</rect>'
            f'<rect x="{x0 - 10:.2f}" y="{SUB_Y - 22}" width="6" height="44" rx="3" fill="{MORSE_COLOR}" '
            f'fill-opacity=".35" opacity="0">'
            f'{anim("x", T, x0 - 10, [(ts0, x0 + wd + 6, D), (tr, x0 - 10, 0.01)])}'
            f'{anim("opacity", T, 0, [(ts0, 1, 0.05), (ts0 + D, 0, 0.25)])}</rect>')
    body = [f'<path d="{path}" fill="none" stroke="{MORSE_SOFT}" stroke-opacity=".14" stroke-width="2" '
            f'stroke-linejoin="round"/>',
            f'<g clip-path="url(#mclip)">'
            f'<path d="{path}" fill="none" stroke="url(#frame)" stroke-opacity=".28" stroke-width="7" '
            f'stroke-linejoin="round"/>'
            f'<path d="{path}" fill="none" stroke="url(#frame)" stroke-width="2.4" stroke-linejoin="round" '
            f'stroke-linecap="round"/></g>',
            scan]
    return [defs] + _wrap(body, ts0, te, T)


MORSE_RENDERERS = {"A": _morse_A, "B": _morse_B, "C": _morse_C, "D": _morse_D}


# ---------------- svg ----------------
def build(name, picture, morse_style=None):
    n = max(1, len(name))
    fs = max(MIN_FONT, min(MAX_FONT, (W - 28 - 26 - TEXT_X) / (n * CHAR_W)))
    cy = CY
    base_y = cy + fs * 0.35

    # timeline: which part of the name is shown at which moment
    style = str(MORSE_STYLE if morse_style is None else morse_style).upper()
    morse = None
    hold, gap = HOLD, GAP
    if style in MORSE_RENDERERS:                       # the name waits until the Morse has finished
        morse = morse_schedule(MORSE_TEXT, MORSE_UNIT)
        hold = max(HOLD, MORSE_DELAY + morse[2] + MORSE_LINGER)
        gap = max(GAP, MORSE_FADE + MORSE_PAUSE)
    t0 = n * TYPE_STEP + hold
    T = t0 + n * ERASE_STEP + gap
    segs = [(i * TYPE_STEP, i) for i in range(n + 1)]                 # typing 0..n letters
    segs += [(t0 + j * ERASE_STEP, n - j) for j in range(1, n + 1)]   # erasing n-1..0 letters
    windows = {k: [] for k in range(n + 1)}
    for idx, (s, k) in enumerate(segs):
        e = segs[idx + 1][0] if idx + 1 < len(segs) else T
        windows[k].append((s, e, idx <= n, n < idx + 1 < len(segs)))   # typing window? / fades out at its end?

    out = []
    a = out.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
      f'role="img" aria-label="{html.escape(name)}">')
    a(f"""<defs>
<clipPath id="card"><rect x="6" y="6" width="{W - 12}" height="{H - 12}" rx="22"/></clipPath>
<clipPath id="pic"><circle cx="{PIC_CX}" cy="{fmt(cy)}" r="{PIC_R}"/></clipPath>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="#1d0316"/><stop offset=".45" stop-color="#0d0618"/><stop offset="1" stop-color="#04061a"/></linearGradient>
<radialGradient id="gPink"><stop offset="0" stop-color="#ff3fa8" stop-opacity=".30"/><stop offset="1" stop-color="#ff3fa8" stop-opacity="0"/></radialGradient>
<radialGradient id="gViolet"><stop offset="0" stop-color="#a24ff0" stop-opacity=".18"/><stop offset="1" stop-color="#a24ff0" stop-opacity="0"/></radialGradient>
<radialGradient id="gBlue"><stop offset="0" stop-color="#2563ff" stop-opacity=".28"/><stop offset="1" stop-color="#2563ff" stop-opacity="0"/></radialGradient>
<linearGradient id="frame" x1="0" y1="0" x2="1" y2="0">{stops_xml()}</linearGradient>
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

    # the round picture
    a(f'<circle cx="{PIC_CX}" cy="{fmt(cy)}" r="{PIC_R}" fill="#0b0716"/>')
    if picture:
        mime, b64 = picture
        a(f'<image href="data:{mime};base64,{b64}" x="{PIC_CX - PIC_R}" y="{fmt(cy - PIC_R)}" '
          f'width="{2 * PIC_R}" height="{2 * PIC_R}" preserveAspectRatio="xMidYMid slice" '
          f'clip-path="url(#pic)"/>')
    else:                                             # nothing found: show the first letter
        a(f'<text x="{PIC_CX}" y="{fmt(cy + 14)}" text-anchor="middle" font-family="{FONT}" '
          f'font-size="40" font-weight="700" fill="#ffffff">{html.escape(name[:1].upper())}</text>')
    a(f'<circle cx="{PIC_CX}" cy="{fmt(cy)}" r="{PIC_R + RING_GAP}" fill="none" '
      f'stroke="url(#frame)" stroke-width="2"/>')

    # the typed name: ONE <text> with one <tspan> per letter. Every letter fades in / out by itself,
    # so nothing is drawn twice (no flicker, no shaking). The browser lays the letters out itself,
    # so any font works.
    f = max(FADE, 0.001)
    spans = []
    for i, ch in enumerate(name):
        ts = i * TYPE_STEP                           # this letter is typed
        te = t0 + (n - 1 - i) * ERASE_STEP           # this letter is erased (last letter first)
        pts = [(0.0, 0.0)] + ([(ts, 0.0)] if ts > 0 else []) + [(ts + f, 1.0), (te, 1.0), (te + f, 0.0), (T, 0.0)]
        kt = ";".join(f"{t_ / T:.5f}" for t_, _ in pts)
        vals = ";".join(f"{v_:g}" for _, v_ in pts)
        spans.append(f'<tspan fill-opacity="0"><animate attributeName="fill-opacity" values="{vals}" '
                     f'keyTimes="{kt}" dur="{T:.3f}s" calcMode="linear" repeatCount="indefinite"/>'
                     f'{html.escape(ch)}</tspan>')
    a(f'<text x="{TEXT_X}" y="{fmt(base_y)}" font-family="{FONT}" font-size="{fmt(fs)}" '
      f'font-weight="700" fill="#ffffff">{"".join(spans)}</text>')

    # the blinking cursor: invisible copies of the first k letters keep its place; only one copy shows at a time
    # the cursor jumps one place AS a letter starts to appear (typing) or to vanish (erasing), so a
    # letter is always on the LEFT of the cursor, never behind it
    cw = {k: [] for k in range(n + 1)}
    for k in range(1, n):
        cw[k].append(((k - 1) * TYPE_STEP, k * TYPE_STEP))                    # typing
    cw[n].append(((n - 1) * TYPE_STEP, t0))                                   # typing + hold
    for j in range(1, n):
        cw[n - j].append((t0 + (j - 1) * ERASE_STEP, t0 + j * ERASE_STEP))   # erasing
    cw[0].append((t0 + (n - 1) * ERASE_STEP, T))                              # empty, before typing again
    for k in range(n + 1):
        ev = []
        for w in sorted(cw[k]):
            ev.append((w[0], 1))
            if w[1] < T:
                ev.append((w[1], 0))
        if ev[0][0] > 0:
            ev.insert(0, (0.0, 0))
        kt = ";".join(f"{min(1.0, t / T):.5f}" for t, _ in ev)
        vals = ";".join(str(v) for _, v in ev)
        a(f'<text x="{TEXT_X}" y="{fmt(base_y)}" font-family="{FONT}" font-size="{fmt(fs)}" '
          f'font-weight="700" fill-opacity="0" opacity="0">'
          f'<animate attributeName="opacity" values="{vals}" keyTimes="{kt}" dur="{T:.3f}s" '
          f'calcMode="discrete" repeatCount="indefinite"/>'
          f'{html.escape(name[:k])}'
          f'<tspan fill="{CURSOR_COLOR}" fill-opacity="1" font-weight="400"><animate attributeName="fill-opacity" '
          f'values="1;0;1" keyTimes="0;.5;1" dur="{CURSOR_BLINK}s" calcMode="linear" repeatCount="indefinite"/>|</tspan>'
          f'</text>')

    if morse:                                          # the Morse subtitle under the picture and the name
        for line in MORSE_RENDERERS[style](morse, n * TYPE_STEP + MORSE_DELAY, t0, T):
            a(line)

    a("</svg>")
    return "\n".join(out)


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if "--demo" in sys.argv:
        name = "mohammadmahdighaedamini"
    else:
        name = os.environ.get("GITHUB_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER")
        if not name:
            sys.exit("Set GITHUB_USER (your GitHub username), or run with --demo")
    picture = fetch_avatar(name, token) if USE_GITHUB_AVATAR else None   # 1. GitHub profile picture
    picture = picture or load_logo()                                     # 2. logo.*  (3. letter)
    if picture and BOOST_PICTURE:
        picture = boost(picture)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    style = None                                   # --morse A|B|C|D|all|off  (default: MORSE_STYLE)
    if "--morse" in sys.argv:
        i = sys.argv.index("--morse")
        style = sys.argv[i + 1] if i + 1 < len(sys.argv) else sys.exit("--morse needs A, B, C, D, all or off")
    styles = sorted(MORSE_RENDERERS) if (style or "").lower() == "all" else [style]
    for st in styles:
        out = OUT if len(styles) == 1 else OUT.replace(".svg", f"-{st}.svg")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(build(name, picture, st))
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
