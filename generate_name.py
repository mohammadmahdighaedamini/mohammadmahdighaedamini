#!/usr/bin/env python3
"""
"Name" banner card, same look as the other cards (Nightmare background).

A fixed round picture (your logo.jpg / logo.png / ... from the repo root) on the left,
and your GitHub username on the right. The username is typed letter by letter
(like readme-typing-svg), waits a moment, is erased and typed again, forever.
No GitHub API call is needed: the name comes from GITHUB_USER (set by the workflow).

Usage:
  GITHUB_USER=yourname python generate_name.py     # real name
  python generate_name.py --demo                   # sample name
Output: assets/name-typing.svg
"""
import base64
import html
import os
import sys

OUT = "assets/name-typing.svg"

W = 782                 # same width as the other cards
H = 170
PIC_R = 44              # radius of the round picture
PIC_CX = 104            # center x of the picture
TEXT_X = 182            # where the name starts
MAX_FONT = 40           # biggest font size (long names are made smaller so they always fit)
MIN_FONT = 14
CHAR_W = 0.6            # width of one letter / font size (monospace fonts are ~0.6)

# ---- typing timing (seconds) ----
TYPE_STEP = 0.09        # time per typed letter
HOLD = 2.5              # the finished name stays this long
ERASE_STEP = 0.04       # time per erased letter
GAP = 0.6               # empty pause before typing again
CURSOR_BLINK = 0.9      # cursor blink period

FONT = "'Fira Code', 'JetBrains Mono', Consolas, 'SF Mono', Menlo, 'DejaVu Sans Mono', monospace"

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


def load_logo():
    """First logo.* in the repo root -> (mime, base64) or None."""
    for name in LOGO_FILES:
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


def discrete(attr, pairs, T, extra=""):
    """pairs = [(time, value), ...] -> a step-by-step (no smoothing) animation."""
    kt = ";".join(f"{min(1.0, t / T):.5f}" for t, _ in pairs)
    vals = ";".join(fmt(v) for _, v in pairs)
    return (f'<animate attributeName="{attr}" values="{vals}" keyTimes="{kt}" '
            f'dur="{T:.3f}s" calcMode="discrete" repeatCount="indefinite"{extra}/>')


def build(name, logo):
    n = max(1, len(name))
    fs = max(MIN_FONT, min(MAX_FONT, (W - 28 - 24 - TEXT_X) / (n * CHAR_W)))
    cw = fs * CHAR_W
    full = n * cw
    cy = H / 2
    base_y = cy + fs * 0.35
    box_y, box_h = cy - fs * 0.62, fs * 1.24

    # typing timeline: width of the visible part of the name
    T = n * TYPE_STEP + HOLD + n * ERASE_STEP + GAP
    pairs = [(0.0, 0.0)]
    for i in range(1, n + 1):                         # type
        pairs.append((i * TYPE_STEP, i * cw))
    t0 = n * TYPE_STEP + HOLD
    for j in range(1, n + 1):                         # erase
        pairs.append((t0 + j * ERASE_STEP, (n - j) * cw))

    out = []
    a = out.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
      f'role="img" aria-label="{html.escape(name)}">')
    a(f"""<defs>
<clipPath id="card"><rect x="6" y="6" width="{W - 12}" height="{H - 12}" rx="22"/></clipPath>
<clipPath id="pic"><circle cx="{PIC_CX}" cy="{fmt(cy)}" r="{PIC_R}"/></clipPath>
<clipPath id="typed"><rect x="{TEXT_X}" y="{fmt(box_y)}" width="0" height="{fmt(box_h)}">{discrete("width", pairs, T)}</rect></clipPath>
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

    # the fixed round picture
    a(f'<circle cx="{PIC_CX}" cy="{fmt(cy)}" r="{PIC_R}" fill="#0b0716"/>')
    if logo:
        mime, b64 = logo
        a(f'<image href="data:{mime};base64,{b64}" x="{PIC_CX - PIC_R}" y="{fmt(cy - PIC_R)}" '
          f'width="{2 * PIC_R}" height="{2 * PIC_R}" preserveAspectRatio="xMidYMid slice" '
          f'clip-path="url(#pic)"/>')
    else:                                             # no logo file: show the first letter instead
        a(f'<text x="{PIC_CX}" y="{fmt(cy + 14)}" text-anchor="middle" font-family="{FONT}" '
          f'font-size="40" font-weight="700" fill="#ffffff">{html.escape(name[:1].upper())}</text>')
    a(f'<circle cx="{PIC_CX}" cy="{fmt(cy)}" r="{PIC_R + 7}" fill="none" stroke="url(#frame)" stroke-width="2"/>')

    # the typed name
    a('<g clip-path="url(#typed)">')
    a(f'<text x="{TEXT_X}" y="{fmt(base_y)}" font-family="{FONT}" font-size="{fmt(fs)}" '
      f'font-weight="700" fill="#ffffff" textLength="{fmt(full)}" lengthAdjust="spacing" '
      f'xml:space="preserve">{html.escape(name)}</text>')
    a("</g>")

    # blinking cursor that follows the end of the typed part
    a(f'<rect x="{TEXT_X}" y="{fmt(box_y)}" width="3" height="{fmt(box_h)}" rx="1.5" fill="#ff4fb8">')
    a(discrete("x", [(t, TEXT_X + v) for t, v in pairs], T))
    a(f'<animate attributeName="opacity" values="1;0" keyTimes="0;.5" dur="{CURSOR_BLINK}s" '
      f'calcMode="discrete" repeatCount="indefinite"/>')
    a("</rect>")

    a("</svg>")
    return "\n".join(out)


def main():
    if "--demo" in sys.argv:
        name = "mohammadmahdighaedamini"
    else:
        name = os.environ.get("GITHUB_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER")
        if not name:
            sys.exit("Set GITHUB_USER (your GitHub username), or run with --demo")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(build(name, load_logo()))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
