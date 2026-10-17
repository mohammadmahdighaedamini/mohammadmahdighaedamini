#!/usr/bin/env python3
"""
"Name" banner card, same look as the other cards (Nightmare background).

Your GitHub profile picture (round) on the left, and your GitHub username on the right.
The username is typed letter by letter, waits a while, is erased and typed again, forever.
The font is the same one the other cards use. The blinking cursor has the same purple as
the beam of the airplane in the contribution card.

Which picture is used (first one that exists):
  1. a file called profile.png / profile.jpg / profile.webp / profile.svg in the repo root
     (upload your own square picture, e.g. 512x512, and it is used automatically)
  2. your GitHub profile picture (downloaded by the script)
  3. logo.svg / logo.png / logo.webp / logo.jpg in the repo root
  4. the first letter of your name
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

PROFILE_FILES = ("profile.png", "profile.jpg", "profile.jpeg", "profile.webp", "profile.svg")   # step 1 above
USE_GITHUB_AVATAR = True   # step 2: True = use your GitHub profile picture when there is no profile.* file
BOOST_PICTURE = False      # True = make thin / dark pictures (like neon outlines) bolder and brighter so they stay
                           # clear in the small circle. Needs Pillow (pip install pillow); skipped without it.
                           # Off by default: your picture is shown exactly as it is.
                           # Not applied to your own profile.* file. Set False for a normal photo.

# ---- typing timing (seconds) ----
TYPE_STEP = 0.13        # time per typed letter           (bigger = slower typing)
HOLD = 3.5              # the finished name stays this long
ERASE_STEP = 0.06       # time per erased letter
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


def fit_square(picture, size=480, margin=1.1):
    """A wide / non-square picture (like a neon banner) would be cut off by the round frame.
    Find where the bright content is, crop a square around it, and resample to `size` px
    (about 4x the circle, sharp on retina screens). Square pictures are left as they are.
    Needs Pillow; without it the picture is used unchanged."""
    mime, b64 = picture
    if mime == "image/svg+xml":
        return picture
    try:
        import io
        from PIL import Image
    except ImportError:
        print("warning: Pillow is not installed, picture not cropped (pip install pillow)", file=sys.stderr)
        return picture
    try:
        img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
        w, h = img.size
        if abs(w - h) <= 0.03 * max(w, h):
            return picture
        lum = img.convert("L").point(lambda v: 255 if v > 70 else 0)
        box = lum.getbbox() or (0, 0, w, h)
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        side = min(max(box[2] - box[0], box[3] - box[1]) * margin, w, h)
        left = min(max(cx - side / 2, 0), w - side)
        top = min(max(cy - side / 2, 0), h - side)
        sq = img.crop((round(left), round(top), round(left + side), round(top + side)))
        sq = sq.resize((size, size), Image.LANCZOS)
        from PIL import ImageEnhance, ImageFilter            # thin neon lines: a little bolder + brighter
        sq = sq.filter(ImageFilter.MaxFilter(3))
        sq = ImageEnhance.Brightness(sq).enhance(1.25)
        sq = ImageEnhance.Color(sq).enhance(1.25)
        buf = io.BytesIO()
        sq.save(buf, "JPEG", quality=92, optimize=True, subsampling=0)
        return "image/jpeg", base64.b64encode(buf.getvalue()).decode()
    except Exception as exc:                                     # the card must never break
        print(f"warning: could not crop the picture: {exc}", file=sys.stderr)
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
        windows[k].append((s, e))

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

    # the typed name: one <text> per step (the first k letters + the cursor); only one is visible
    # at a time. The browser lays the letters out itself, so any font works and the cursor
    # always sits right after the last letter.
    for k in range(n + 1):
        ev = []
        for s, e in windows[k]:
            ev.append((s, 1))
            if e < T:
                ev.append((e, 0))
        if ev[0][0] > 0:
            ev.insert(0, (0.0, 0))
        kt = ";".join(f"{min(1.0, t / T):.5f}" for t, _ in ev)
        vals = ";".join(str(v) for _, v in ev)
        a(f'<text x="{TEXT_X}" y="{fmt(base_y)}" font-family="{FONT}" font-size="{fmt(fs)}" '
          f'font-weight="700" fill="#ffffff" opacity="0">'
          f'<animate attributeName="opacity" values="{vals}" keyTimes="{kt}" dur="{T:.3f}s" '
          f'calcMode="discrete" repeatCount="indefinite"/>'
          f'{html.escape(name[:k])}'
          f'<tspan fill="{CURSOR_COLOR}" font-weight="400"><animate attributeName="fill-opacity" values="1;0" '
          f'keyTimes="0;.5" dur="{CURSOR_BLINK}s" calcMode="discrete" repeatCount="indefinite"/>|</tspan>'
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
    picture = load_logo(PROFILE_FILES)                              # 1. your own profile.* file
    if picture:
        picture = fit_square(picture)                               #    (wide pictures are centered + sharpened)
    if not picture:
        picture = fetch_avatar(name, token) if USE_GITHUB_AVATAR else None   # 2. GitHub profile picture
        picture = picture or load_logo()                            # 3. logo.*  (4. letter)
        if picture and BOOST_PICTURE:
            picture = boost(picture)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(build(name, picture))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
