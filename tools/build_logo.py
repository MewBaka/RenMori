"""Generate the RenMori logo SVGs with all text converted to outlines.

Usage: python tools/build_logo.py assets/logo   (needs fonttools and FOT-Skip Std D installed)
"""
import math, os, sys
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

OUT = sys.argv[1]
FONTS = os.path.expanduser("~/Library/Fonts/")
SKIP = TTFont(FONTS + "FOT-Skip Std D.otf")


def glyphs(font, text, size, tracking=0.0):
    """Return [(d, x_advance)] per char, origin at baseline, y down."""
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    upm = font["head"].unitsPerEm
    s = size / upm
    out, x = [], 0.0
    for ch in text:
        name = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        gs[name].draw(TransformPen(pen, (s, 0, 0, -s, 0, 0)))
        adv = gs[name].width * s
        out.append((pen.getCommands(), x, adv))
        x += adv + tracking
    return out, x - tracking


def text_path(font, text, size, x, y, tracking=0.0, anchor="start"):
    gl, w = glyphs(font, text, size, tracking)
    if anchor == "middle":
        x -= w / 2
    elif anchor == "end":
        x -= w
    return "".join(f'<path transform="translate({x+gx:.2f} {y:.2f})" d="{d}"/>' for d, gx, _ in gl), w


def sakura(cx, cy, r, rot=0, fill="url(#petal)", stroke="#3b2257", sw=4):
    """Five-petal cherry blossom with notched petal tips."""
    petals = []
    for i in range(5):
        a = rot + i * 72
        petals.append(
            f'<path transform="rotate({a} {cx} {cy})" d="M{cx} {cy} '
            f'C{cx - r*0.62} {cy - r*0.35} {cx - r*0.55} {cy - r*0.95} {cx - r*0.16} {cy - r} '
            f'L{cx} {cy - r*0.82} L{cx + r*0.16} {cy - r} '
            f'C{cx + r*0.55} {cy - r*0.95} {cx + r*0.62} {cy - r*0.35} {cx} {cy}Z"/>'
        )
    body = "".join(petals)
    return (
        f'<g stroke="{stroke}" stroke-width="{sw}" stroke-linejoin="round" fill="{fill}">{body}</g>'
        f'<g fill="none" stroke="#ff5d97" stroke-width="{sw*0.6}" stroke-linecap="round">'
        + "".join(
            f'<line transform="rotate({rot + i*72} {cx} {cy})" x1="{cx}" y1="{cy}" x2="{cx}" y2="{cy - r*0.42}"/>'
            for i in range(5)
        )
        + f'</g><circle cx="{cx}" cy="{cy}" r="{r*0.16}" fill="#ffd45e" stroke="{stroke}" stroke-width="{sw*0.6}"/>'
    )


def sparkle(cx, cy, r, fill="#ffd45e", stroke="#3b2257", sw=3):
    k = r * 0.22
    d = (f"M{cx} {cy-r} Q{cx+k} {cy-k} {cx+r} {cy} Q{cx+k} {cy+k} {cx} {cy+r} "
         f"Q{cx-k} {cy+k} {cx-r} {cy} Q{cx-k} {cy-k} {cx} {cy-r}Z")
    return f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" stroke-linejoin="round"/>'


def petal(cx, cy, s, rot):
    return (f'<path transform="translate({cx} {cy}) rotate({rot}) scale({s})" '
            f'd="M0 -10 C7 -8 9 2 0 10 C-9 2 -7 -8 0 -10Z" fill="#ffb3cf" stroke="#3b2257" stroke-width="{2.4/s:.2f}"/>')


DEFS = """
<defs>
  <linearGradient id="pouch" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#ff9cc4"/><stop offset=".55" stop-color="#d98bff"/><stop offset="1" stop-color="#8f6bff"/>
  </linearGradient>
  <linearGradient id="petal" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#ffc4da"/>
  </linearGradient>
  <linearGradient id="ear" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#ffe3ef"/>
  </linearGradient>
  <linearGradient id="kanji" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#ff4f8b"/><stop offset="1" stop-color="#7b4dff"/>
  </linearGradient>
  <linearGradient id="gold" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#fff1a8"/><stop offset="1" stop-color="#ffb938"/>
  </linearGradient>
  <linearGradient id="ren" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#ffa3c8"/><stop offset=".5" stop-color="#ff5c98"/><stop offset="1" stop-color="#f0377a"/>
  </linearGradient>
  <linearGradient id="mori" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#c9b2ff"/><stop offset=".5" stop-color="#8f6bff"/><stop offset="1" stop-color="#6440f0"/>
  </linearGradient>
  <linearGradient id="gloss" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#fff" stop-opacity=".75"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/>
  </linearGradient>
  <radialGradient id="halo" cx=".5" cy=".5" r=".5">
    <stop offset="0" stop-color="#ffd1e4" stop-opacity=".9"/><stop offset=".7" stop-color="#ffe6f0" stop-opacity=".55"/><stop offset="1" stop-color="#fff0f6" stop-opacity="0"/>
  </radialGradient>
  <clipPath id="pouchClip"><path d="M131 180 L181 132 L331 132 L381 180 L381 424 Q381 452 353 452 L159 452 Q131 452 131 424Z"/></clipPath>
</defs>
"""

INK = "#3b2257"


def emblem(mini=False):
    """The omamori charm with kitsune ears, drawn in a 512x512 box."""
    p = []
    # soft halo and orbit ring
    if not mini:
      p.append('<circle cx="256" cy="282" r="236" fill="url(#halo)"/>')
      p.append(f'<circle cx="256" cy="282" r="214" fill="none" stroke="#ff9cc4" stroke-width="3" stroke-dasharray="2 12" stroke-linecap="round"/>')
    # kitsune ears behind the pouch
    for sx in (1, -1):
        t = f'translate(256 0) scale({sx} 1) translate(-256 0)'
        p.append(f'<g transform="{t}">'
                 f'<path d="M150 190 Q122 98 128 52 Q176 70 226 140Z" fill="url(#ear)" stroke="{INK}" stroke-width="9" stroke-linejoin="round"/>'
                 f'<path d="M156 168 Q140 110 142 80 Q174 98 204 138Z" fill="#ff9cc4"/>'
                 f'</g>')
    # pouch body
    body = "M131 180 L181 132 L331 132 L381 180 L381 424 Q381 452 353 452 L159 452 Q131 452 131 424Z"
    p.append(f'<path d="{body}" fill="url(#pouch)"/>')
    # seigaiha waves on the lower half
    waves = []
    for row, y in enumerate(range(372, 470, 22)):
        off = 0 if row % 2 == 0 else 22
        for x in range(110 - off, 420, 44):
            for r in (22, 14, 6):
                waves.append(f'<circle cx="{x}" cy="{y}" r="{r}"/>')
    p.append(f'<g clip-path="url(#pouchClip)" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="3">{"".join(waves)}</g>')
    # left-side shine
    p.append('<path d="M150 192 L150 300" stroke="#fff" stroke-opacity=".7" stroke-width="9" stroke-linecap="round"/>')
    p.append('<path d="M150 322 L150 338" stroke="#fff" stroke-opacity=".7" stroke-width="9" stroke-linecap="round"/>')
    # gold stitched inner border
    inner = "M147 186 L187 148 L325 148 L365 186 L365 420 Q365 436 349 436 L163 436 Q147 436 147 420Z"
    p.append(f'<path d="{inner}" fill="none" stroke="#ffe27a" stroke-width="3.5" stroke-dasharray="9 7" stroke-linecap="round"/>')
    p.append(f'<path d="{body}" fill="none" stroke="{INK}" stroke-width="10" stroke-linejoin="round"/>')
    # name panel with 守
    p.append(f'<rect x="196" y="186" width="120" height="166" rx="22" fill="#fff" stroke="{INK}" stroke-width="7"/>')
    p.append(f'<rect x="205" y="195" width="102" height="148" rx="15" fill="none" stroke="#ffb3cf" stroke-width="3"/>')
    kanji, _ = text_path(SKIP, "守", 104, 256, 306, anchor="middle")
    p.append(f'<g fill="url(#kanji)" stroke="{INK}" stroke-width="3" stroke-linejoin="round">{kanji}</g>')
    # heart keyhole lock on the lower body
    p.append(f'<path d="M256 432 C214 406 204 384 216 370 C228 356 246 360 256 374 C266 360 284 356 296 370 C308 384 298 406 256 432Z" '
             f'fill="url(#gold)" stroke="{INK}" stroke-width="7" stroke-linejoin="round"/>')
    p.append(f'<circle cx="256" cy="386" r="7.5" fill="{INK}"/><path d="M252 388 L249 409 L263 409 L260 388Z" fill="{INK}"/>')
    # cord knot on top
    p.append(f'<path d="M256 132 C238 92 238 56 256 40 C274 56 274 92 256 132Z" fill="none" stroke="{INK}" stroke-width="15" stroke-linecap="round"/>')
    p.append(f'<path d="M256 132 C238 92 238 56 256 40 C274 56 274 92 256 132Z" fill="none" stroke="#ff4f8b" stroke-width="7" stroke-linecap="round"/>')
    for sx in (1, -1):
        t = f'translate(256 0) scale({sx} 1) translate(-256 0)'
        p.append(f'<g transform="{t}"><path d="M256 120 C226 92 196 100 200 124 C204 146 236 136 256 120Z" fill="#ff6fa3" stroke="{INK}" stroke-width="7" stroke-linejoin="round"/>'
                 f'<path d="M216 116 C224 110 234 112 240 117" fill="none" stroke="#fff" stroke-opacity=".7" stroke-width="4" stroke-linecap="round"/></g>')
    p.append(f'<circle cx="256" cy="121" r="13" fill="url(#gold)" stroke="{INK}" stroke-width="6"/>')
    # blossoms, petals, sparkles
    p.append(sakura(372, 182, 46, rot=12))
    if mini:
        return "".join(p)
    p.append(sakura(134, 420, 30, rot=-20))
    p.append(petal(426, 288, 1.7, 40) + petal(92, 300, 1.4, -30) + petal(410, 400, 1.2, 110) + petal(108, 216, 1.1, 70))
    p.append(sparkle(88, 150, 22) + sparkle(438, 104, 15, fill="#fff") + sparkle(446, 440, 18) + sparkle(70, 372, 11, fill="#fff"))
    return "".join(p)


def wordmark(x0, base):
    """'RenMori' set as a galgame title: ink outline, white rim, gradient fill, gloss, bouncing letters."""
    size = 168
    gl, w = glyphs(SKIP, "RenMori", size, tracking=-4)
    bounce = [0, -10, 4, -2, -12, 2, -8]
    tilt = [-5, 4, -3, -2, 5, -4, 3]
    letters = []
    for i, (d, gx, adv) in enumerate(gl):
        cx = x0 + gx + adv / 2
        tr = f"translate({x0 + gx:.2f} {base + bounce[i]:.2f}) rotate({tilt[i]} {adv/2:.1f} {-size*0.35:.1f})"
        letters.append((tr, d, "ren" if i < 3 else "mori"))
    shadow = "".join(f'<path transform="translate(7 10) {tr}" d="{d}"/>' for tr, d, _ in letters)
    outer = "".join(f'<path transform="{tr}" d="{d}"/>' for tr, d, _ in letters)
    fills = "".join(f'<path transform="{tr}" d="{d}" fill="url(#{g})"/>' for tr, d, g in letters)
    gloss = "".join(f'<path transform="{tr}" d="{d}"/>' for tr, d, _ in letters)
    return (
        f'<g fill="{INK}" stroke="{INK}" stroke-width="30" stroke-linejoin="round" opacity=".28">{shadow}</g>'
        f'<g fill="{INK}" stroke="{INK}" stroke-width="30" stroke-linejoin="round">{outer}</g>'
        f'<g fill="#fff" stroke="#fff" stroke-width="16" stroke-linejoin="round">{outer}</g>'
        f'<g>{fills}</g>'
        f'<clipPath id="glossClip"><rect x="{x0-20}" y="{base-size}" width="{w+40}" height="{size*0.42}"/></clipPath>'
        f'<g fill="url(#gloss)" clip-path="url(#glossClip)">{gloss}</g>'
    ), w


def lockup():
    x0, base = 560, 318
    wm, w = wordmark(x0, base)
    W, H = int(x0 + w + 70), 520
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">', DEFS]
    parts.append(f'<title>RenMori</title>')
    parts.append(f'<g transform="translate(14 4)">{emblem()}</g>')
    parts.append(f'<g transform="rotate(-4 {x0 + w/2} {base})">')
    # katakana reading above
    kana, kw = text_path(SKIP, "レンモリ", 40, x0 + 6, base - 168, tracking=14)
    parts.append(f'<g fill="#fff" stroke="{INK}" stroke-width="10" stroke-linejoin="round" paint-order="stroke">{kana}</g>')
    parts.append(f'<g fill="#ff4f8b">{kana}</g>')
    parts.append(sparkle(x0 + kw + 30, base - 182, 16) + sparkle(x0 + kw + 62, base - 160, 9, fill="#fff"))
    parts.append(wm)
    # VN dialogue box tagline
    bx, by, bw, bh = x0 - 4, base + 44, w + 12, 74
    parts.append(f'<rect x="{bx+6}" y="{by+8}" width="{bw}" height="{bh}" rx="20" fill="{INK}" opacity=".28"/>')
    parts.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="20" fill="{INK}" stroke="#fff" stroke-width="5"/>')
    parts.append(f'<rect x="{bx+9}" y="{by+9}" width="{bw-18}" height="{bh-18}" rx="13" fill="none" stroke="#ff9cc4" stroke-width="2.5" stroke-dasharray="1 7" stroke-linecap="round"/>')
    # speaker name tag
    tag, tw = text_path(SKIP, "守り", 26, bx + 36, by - 4, anchor="start")
    parts.append(f'<rect x="{bx+22}" y="{by-30}" width="{tw+28}" height="40" rx="12" fill="#ff5c98" stroke="#fff" stroke-width="5"/>')
    parts.append(f'<g fill="#fff">{tag}</g>')
    tl, tlw = text_path(SKIP, "Full-data protection for Ren'Py", 30, bx + 34, by + 49, tracking=1.5)
    parts.append(f'<g fill="#fff">{tl}</g>')
    tri_x = bx + bw - 34
    parts.append(f'<path d="M{tri_x-11} {by+bh-30} L{tri_x+11} {by+bh-30} L{tri_x} {by+bh-16}Z" fill="#ffd45e" stroke="#ffd45e" stroke-width="4" stroke-linejoin="round"/>')
    parts.append('</g>')
    parts.append(petal(W - 40, 70, 1.6, 30) + petal(W - 90, 480, 1.3, -40) + sparkle(W - 26, 470, 13))
    parts.append('</svg>')
    return "".join(parts)


def icon():
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">{DEFS}'
            f'<title>RenMori</title><g transform="translate(0 -14)">{emblem()}</g></svg>')


def icon_mini():
    """Small-size variant: no halo, sparkles or stray petals, framed tighter."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="96 30 320 440" width="320" height="440">{DEFS}'
            f'<title>RenMori</title>{emblem(mini=True)}</svg>')


os.makedirs(OUT, exist_ok=True)
open(os.path.join(OUT, "renmori-logo.svg"), "w").write(lockup())
open(os.path.join(OUT, "renmori-icon.svg"), "w").write(icon())
open(os.path.join(OUT, "renmori-icon-mini.svg"), "w").write(icon_mini())
print("ok")
