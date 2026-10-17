"""Embeds the Segoe UI font into a generated SVG.

GitHub shows README images inside <img>, where web fonts are blocked and the
viewer's own fonts are used. To make the text look the same for everybody, the
font files in assets/fonts/ are base64-embedded into each SVG (@font-face with a
data: URL). Only the faces that the SVG actually uses are embedded.

Used by generate_ship.py, generate_langs.py and generate_timeline.py:
    return embed_fonts(svg)
"""
import base64
import os
import re

FONT_FAMILY = "SegoeUIEmbed"
# the embedded font first; the rest is only a fallback (and covers glyphs the font lacks)
FONT_STACK = f"{FONT_FAMILY}, Segoe UI, Ubuntu, Helvetica, Arial, sans-serif"

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
_FACES = {  # (bold, italic) -> file
    (False, False): "SegoeUI-Regular.woff",
    (True, False): "SegoeUI-Bold.woff",
    (False, True): "SegoeUI-Italic.woff",
    (True, True): "SegoeUI-BoldItalic.woff",
}


def _face_css(bold, italic):
    with open(os.path.join(_DIR, _FACES[(bold, italic)]), "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    return (
        f"@font-face{{font-family:'{FONT_FAMILY}';font-weight:{700 if bold else 400};"
        f"font-style:{'italic' if italic else 'normal'};"
        f"src:url(data:font/woff;base64,{b64}) format('woff');}}"
    )


def _used_faces(svg):
    """Which (bold, italic) faces do the <text> elements of this SVG need?"""
    used = set()
    for tag in re.findall(r"<text\b[^>]*>", svg):
        m = re.search(r'font-weight="(\d+)"', tag)
        bold = bool(m) and int(m.group(1)) >= 600      # 600 and up use the Bold face
        italic = 'font-style="italic"' in tag
        used.add((bold, italic))
    return used or {(False, False)}


def embed_fonts(svg):
    """Insert the <style> with the embedded fonts at the start of <defs>."""
    css = "".join(_face_css(b, i) for b, i in sorted(_used_faces(svg)))
    style = f"<style>{css}</style>"
    if "<defs>" in svg:
        return svg.replace("<defs>", "<defs>" + style, 1)
    return re.sub(r"(<svg\b[^>]*>)", lambda m: m.group(1) + "<defs>" + style + "</defs>", svg, count=1)
