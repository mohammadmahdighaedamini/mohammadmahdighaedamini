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
Output: assets/name-typing.svg
"""
import base64
import html
import json
import os
import sys
import urllib.request

OUT = "assets/name-typing.svg"

W = 782                 # same width as the other cards
H = 240
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


# ---------------- svg ----------------
def build(name, picture):
    n = max(1, len(name))
    fs = max(MIN_FONT, min(MAX_FONT, (W - 28 - 26 - TEXT_X) / (n * CHAR_W)))
    cy = H / 2
    base_y = cy + fs * 0.35

    # timeline: which part of the name is shown at which moment
    t0 = n * TYPE_STEP + HOLD
    T = t0 + n * ERASE_STEP + GAP
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
    for k in range(n + 1):
        ev = []
        for w in windows[k]:
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
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(build(name, picture))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
