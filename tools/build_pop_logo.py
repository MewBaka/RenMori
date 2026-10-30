"""Generate the RenMori 'pop' wordmark — ProgrammingVTuberLogos / AstAro style.

Chunky bubble letters (Mochiy Pop One), fat charcoal outline + hard drop shadow,
the 'o' in Mori is a little guardian-fox face, 'れんもり' kana below in pink/purple.
All text is baked to outline paths so the SVG is self-contained (no font at runtime).

Usage:
    python tools/build_pop_logo.py assets/logo

The Mochiy Pop One font (OFL) is resolved from, in order:
    $RENMORI_POP_FONT, ~/Library/Fonts/MochiyPopOne-Regular.ttf,
    tools/.fonts/MochiyPopOne-Regular.ttf (downloaded there once if missing).
"""
import os, sys, urllib.request
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen

FONT_URL = ("https://github.com/google/fonts/raw/main/ofl/"
            "mochiypopone/MochiyPopOne-Regular.ttf")


def resolve_font():
    cands = [os.environ.get("RENMORI_POP_FONT"),
             os.path.expanduser("~/Library/Fonts/MochiyPopOne-Regular.ttf")]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".fonts")
    dst = os.path.join(cache, "MochiyPopOne-Regular.ttf")
    if not os.path.isfile(dst):
        os.makedirs(cache, exist_ok=True)
        sys.stderr.write(f"downloading Mochiy Pop One -> {dst}\n")
        urllib.request.urlretrieve(FONT_URL, dst)
    return dst


POP = TTFont(resolve_font())

INK   = "#2b2733"   # outline, near-black warm charcoal
SHADE = "#4c4656"   # hard drop shadow
WHITE = "#ffffff"
PINK  = "#ff5c98"
PURP  = "#8f6bff"
BLUSH = "#ff9ec4"

SDX, SDY = 7, 24    # drop-shadow offset


def glyphs(font, text, size, tracking=0.0):
    gs = font.getGlyphSet(); cmap = font.getBestCmap()
    upm = font["head"].unitsPerEm; s = size / upm
    out, x = [], 0.0
    for ch in text:
        name = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        gs[name].draw(TransformPen(pen, (s, 0, 0, -s, 0, 0)))
        bp = BoundsPen(gs); gs[name].draw(bp)
        adv = gs[name].width * s
        out.append((pen.getCommands(), x, adv, bp.bounds, s))
        x += adv + tracking
    return out, (x - tracking if text else 0.0)


def fox_face(cx, cy, r):
    """A round guardian-fox face sized to sit where the 'o' is (local coords)."""
    ear = (lambda sx: f'<path d="M{cx+sx*r*0.52} {cy-r*0.74} '
                      f'L{cx+sx*r*0.96} {cy-r*1.42} L{cx+sx*r*1.02} {cy-r*0.64}Z"/>')
    ears = ear(-1) + ear(1)
    inner = (lambda sx: f'<path d="M{cx+sx*r*0.63} {cy-r*0.82} '
                        f'L{cx+sx*r*0.9} {cy-r*1.22} L{cx+sx*r*0.9} {cy-r*0.78}Z" fill="{PINK}"/>')
    ex, ey, er = r*0.40, cy-r*0.08, r*0.165
    eyes = (f'<circle cx="{cx-ex}" cy="{ey}" r="{er}" fill="{INK}"/>'
            f'<circle cx="{cx+ex}" cy="{ey}" r="{er}" fill="{INK}"/>'
            f'<circle cx="{cx-ex+er*0.4}" cy="{ey-er*0.45}" r="{er*0.34}" fill="#fff"/>'
            f'<circle cx="{cx+ex+er*0.4}" cy="{ey-er*0.45}" r="{er*0.34}" fill="#fff"/>')
    blush = (f'<ellipse cx="{cx-r*0.58}" cy="{cy+r*0.26}" rx="{r*0.19}" ry="{r*0.12}" fill="{BLUSH}" opacity=".9"/>'
             f'<ellipse cx="{cx+r*0.58}" cy="{cy+r*0.26}" rx="{r*0.19}" ry="{r*0.12}" fill="{BLUSH}" opacity=".9"/>')
    my = cy+r*0.34
    mouth = (f'<path d="M{cx} {my-r*0.04} C{cx-r*0.17} {my+r*0.20} {cx-r*0.30} {my-r*0.06} {cx-r*0.30} {my-r*0.06} '
             f'M{cx} {my-r*0.04} C{cx+r*0.17} {my+r*0.20} {cx+r*0.30} {my-r*0.06} {cx+r*0.30} {my-r*0.06}" '
             f'fill="none" stroke="{INK}" stroke-width="{r*0.085}" stroke-linecap="round" stroke-linejoin="round"/>')
    nose = f'<path d="M{cx-r*0.11} {cy+r*0.17} L{cx+r*0.11} {cy+r*0.17} L{cx} {cy+r*0.30}Z" fill="{INK}"/>'
    head = f'<circle cx="{cx}" cy="{cy}" r="{r}"/>'
    ow, rim = r*0.30, r*0.11
    shadow = (f'<g transform="translate({SDX} {SDY})" fill="{SHADE}" stroke="{SHADE}" '
              f'stroke-width="{ow}" stroke-linejoin="round">{ears}{head}</g>')
    ink = f'<g fill="{INK}" stroke="{INK}" stroke-width="{ow}" stroke-linejoin="round">{ears}{head}</g>'
    white = (f'<g fill="{WHITE}" stroke="{WHITE}" stroke-width="{ow-2*rim}" stroke-linejoin="round">{ears}{head}</g>')
    inr = f'<g stroke="{INK}" stroke-width="{r*0.07}" stroke-linejoin="round">{inner(-1)}{inner(1)}</g>'
    return {"shadow": shadow, "solid": ink + white + inr + blush + nose + eyes + mouth}


def wordmark(x0, base):
    size, tracking = 240, -6
    gl, w = glyphs(POP, "RenMori", size, tracking)
    bounce = [0, -8, 3, -12, 0, -4, -9]
    tilt   = [-4, 3, -2, 4, 0, 2, 6]
    fills  = ["url(#renFill)"]*3 + ["url(#moriFill)"]*4
    face_i = 4  # the 'o'

    _, gx_o, adv_o, bb_o, s_o = gl[face_i]
    o_w = (bb_o[2]-bb_o[0]) * s_o
    cx, cy = gx_o + adv_o/2.0, -size*0.285
    r = o_w*0.60
    tr_o = f"translate({x0:.2f} {base+bounce[face_i]:.2f}) rotate({tilt[face_i]} {cx:.1f} {cy:.1f})"

    paths = []
    for i, (d, gx, adv, bb, s) in enumerate(gl):
        if i == face_i:
            continue
        tr = f"translate({x0+gx:.2f} {base+bounce[i]:.2f}) rotate({tilt[i]} {adv/2:.1f} {-size*0.3:.1f})"
        paths.append((tr, d, fills[i]))

    out_w, rim = 34, 11
    sh = "".join(f'<path transform="translate({SDX} {SDY}) {tr}" d="{d}"/>' for tr, d, _ in paths)
    outer = "".join(f'<path transform="{tr}" d="{d}"/>' for tr, d, _ in paths)
    fillg = "".join(f'<path transform="{tr}" d="{d}" fill="{f}" stroke="{f}" '
                    f'stroke-width="{out_w-2*rim}" stroke-linejoin="round" stroke-linecap="round"/>'
                    for tr, d, f in paths)
    face = fox_face(cx, cy, r)
    s = [
        f'<g fill="{SHADE}" stroke="{SHADE}" stroke-width="{out_w}" stroke-linejoin="round" stroke-linecap="round">{sh}</g>',
        f'<g transform="{tr_o}">{face["shadow"]}</g>',
        f'<g fill="{INK}" stroke="{INK}" stroke-width="{out_w}" stroke-linejoin="round" stroke-linecap="round">{outer}</g>',
        f'<g>{fillg}</g>',
        f'<g transform="{tr_o}">{face["solid"]}</g>',
    ]
    return "".join(s), w


def sparkle(cx, cy, r, fill="#ffd45e"):
    k = r*0.26
    d = (f"M{cx} {cy-r} Q{cx+k} {cy-k} {cx+r} {cy} Q{cx+k} {cy+k} {cx} {cy+r} "
         f"Q{cx-k} {cy+k} {cx-r} {cy} Q{cx-k} {cy-k} {cx} {cy-r}Z")
    return f'<path d="{d}" fill="{fill}" stroke="{INK}" stroke-width="{max(3,r*0.22)}" stroke-linejoin="round"/>'


DEFS = (
    '<defs>'
    '<linearGradient id="renFill" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0" stop-color="#ff8cbb"/><stop offset=".5" stop-color="#ff5c98"/>'
    '<stop offset="1" stop-color="#f23f84"/></linearGradient>'
    '<linearGradient id="moriFill" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0" stop-color="#ab8dff"/><stop offset=".5" stop-color="#8f6bff"/>'
    '<stop offset="1" stop-color="#7452f0"/></linearGradient>'
    '</defs>'
)


def lockup():
    x0, base = 70, 300
    wm, w = wordmark(x0, base)
    kgl, kw = glyphs(POP, "れんもり", 96, 26)
    kcolors = [PINK, PINK, PURP, PURP]
    ky = base + 150
    kx = x0 + (w - kw)/2.0 + 8
    kpaths = [(f"translate({kx+gx:.2f} {ky:.2f})", d, kcolors[i])
              for i, (d, gx, adv, bb, s) in enumerate(kgl)]
    kow, krim = 20, 7
    ksh = "".join(f'<path transform="translate({SDX*0.7:.1f} {SDY*0.7:.1f}) {tr}" d="{d}"/>' for tr, d, _ in kpaths)
    kouter = "".join(f'<path transform="{tr}" d="{d}"/>' for tr, d, _ in kpaths)
    kfill = "".join(f'<path transform="{tr}" d="{d}" fill="{f}" stroke="{f}" stroke-width="{kow-2*krim}" '
                    f'stroke-linejoin="round"/>' for tr, d, f in kpaths)
    kana = (f'<g fill="{SHADE}" stroke="{SHADE}" stroke-width="{kow}" stroke-linejoin="round">{ksh}</g>'
            f'<g fill="{INK}" stroke="{INK}" stroke-width="{kow}" stroke-linejoin="round">{kouter}</g>'
            f'<g>{kfill}</g>')

    W, H = int(x0 + w + 70), int(ky + 40)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
             DEFS, '<title>RenMori</title>',
             sparkle(x0 + w - 24, base - 250, 20),
             wm, kana,
             sparkle(x0 + 6, base - 150, 16, fill="#fff"),
             sparkle(W - 48, ky - 40, 15),
             '</svg>']
    return "".join(parts)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "renmori-pop.svg")
    open(path, "w").write(lockup())
    print("wrote", path)
