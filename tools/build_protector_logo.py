"""RenMori 'protector' sticker logo — cool-blue Ren'Py-resource-protector theme.

Vector remake of the blue sticker concept: bubble 'RenMori' with a keyhole 'o',
katakana above, 'Ren'Py Resource Protector' slogan, a shield+lock with leaves,
rpa/rpym/rpyc file chips, a ****** password pill, mint swirls + sparkles, all on
a die-cut white sticker edge. Text baked to outlines -> self-contained SVG.

Usage:
    python tools/build_protector_logo.py assets/logo

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

# ---- palette (Ren'Py brand tones: auburn / khaki / cream / gold) ----
INK    = "#43281b"   # dark espresso outline
REN_T, REN_B   = "#f6cd77", "#e7a63c"   # 'Ren' gradient — warm gold
MORI_T, MORI_B = "#c65b3b", "#9b3a21"   # 'Mori' gradient — auburn red (Eileen's hair)
NAVY   = "#7a3620"   # warm text brown (katakana / slogan)
MINT   = "#fff2d8"   # cream accent (keyhole / shine)
MINT_L = "#fffaf0"   # light cream
MINT_D = "#f3c24e"   # gold accent (sparkles / swirls / asterisks)
BLUE_M = "#b58049"   # chips — kraft tan
WHITE  = "#fdf6ea"   # warm off-white sticker edge
SHADOW = "#3a2013"   # warm brown shadow

DIECUT = 36          # white sticker border radius
SDX, SDY = 6, 16     # letter drop shadow
OUT, RIM = 22, 6     # wordmark weight: ink silhouette width / dark rim (kept modest so 'e' etc. stay open)

SIL = []   # die-cut silhouette geometry (filled/stroked white as one group)


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


def text_width(text, size, tracking=0.0):
    return glyphs(POP, text, size, tracking)[1]


def text_block(text, size, x, y, fill, tracking=0.0, anchor="start", outline=0, shadow=True, sil=True):
    gl, w = glyphs(POP, text, size, tracking)
    if anchor == "middle": x -= w/2
    elif anchor == "end":  x -= w
    defs = [(f'translate({x+gx:.2f} {y:.2f})', d) for d, gx, adv, bb, s in gl]
    body = "".join(f'<path transform="{tr}" d="{d}"/>' for tr, d in defs)
    if sil:
        for tr, d in defs:
            SIL.append(f'<path transform="{tr}" d="{d}"/>')
    out = ""
    if shadow:
        sh = "".join(f'<path transform="translate({SDX} {SDY}) {tr}" d="{d}"/>' for tr, d in defs)
        out += f'<g fill="{SHADOW}" opacity=".13">{sh}</g>'
    if outline:
        out += (f'<g fill="none" stroke="{INK}" stroke-width="{outline}" '
                f'stroke-linejoin="round">{body}</g>')
    out += f'<g fill="{fill}">{body}</g>'
    return out, w


def sparkle(cx, cy, r, fill=MINT_D, sil=True):
    k = r*0.3
    d = (f"M{cx} {cy-r} Q{cx+k} {cy-k} {cx+r} {cy} Q{cx+k} {cy+k} {cx} {cy+r} "
         f"Q{cx-k} {cy+k} {cx-r} {cy} Q{cx-k} {cy-k} {cx} {cy-r}Z")
    if sil: SIL.append(f'<path d="{d}"/>')
    return f'<path d="{d}" fill="{fill}" stroke="{INK}" stroke-width="{max(2,r*0.14)}" stroke-linejoin="round"/>'


def keyhole(cx, cy, s, fill=MINT):
    """Classic keyhole: round top + narrow tapering stem."""
    r = s*0.46
    top = cy - s*0.18
    circ = f'<circle cx="{cx}" cy="{top}" r="{r}" fill="{fill}"/>'
    y1, y2 = top, cy + s*0.86
    stem = (f'<path d="M{cx-s*0.16} {y1} L{cx+s*0.16} {y1} '
            f'L{cx+s*0.30} {y2} L{cx-s*0.30} {y2} Z" fill="{fill}"/>')
    return circ + stem


def lock_o(cx, cy, R):
    """The 'o' as a round lock face with a cream keyhole (ink silhouette + inset fill)."""
    SIL.append(f'<circle cx="{cx}" cy="{cy}" r="{R}"/>')
    body = (f'<g><circle cx="{cx+SDX}" cy="{cy+SDY}" r="{R}" fill="{SHADOW}" opacity=".16"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="{INK}"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{R-RIM}" fill="url(#moriG)"/>'
            f'<path d="M{cx-R*0.70} {cy-R*0.18} A{R*0.74} {R*0.74} 0 0 1 {cx-R*0.12} {cy-R*0.72}" '
            f'fill="none" stroke="#fff" stroke-opacity=".5" stroke-width="{R*0.12}" stroke-linecap="round"/>'
            f'{keyhole(cx, cy-R*0.02, R*0.66)}</g>')
    return body


def key(cx, cy, s, rot=0):
    """A little gold key charm — pairs with the keyhole 'o' (守 = to guard)."""
    t = f'translate({cx} {cy}) rotate({rot})'
    bow   = f'<circle cx="0" cy="0" r="{0.52*s}"/>'
    shaft = f'<rect x="{-0.13*s}" y="{0.18*s}" width="{0.26*s}" height="{1.02*s}" rx="{0.1*s}"/>'
    t1    = f'<rect x="{0.08*s}" y="{0.98*s}" width="{0.34*s}" height="{0.16*s}" rx="{0.05*s}"/>'
    t2    = f'<rect x="{0.08*s}" y="{0.72*s}" width="{0.24*s}" height="{0.14*s}" rx="{0.05*s}"/>'
    shapes = bow + shaft + t1 + t2
    ow, rim = 0.22*s, 0.07*s
    SIL.append(f'<g transform="{t}">{shapes}</g>')
    return (
        f'<g transform="translate({SDX} {SDY}) {t}" fill="{SHADOW}" opacity=".16" '
        f'stroke="{SHADOW}" stroke-width="{ow}" stroke-linejoin="round">{shapes}</g>'
        f'<g transform="{t}" fill="{INK}" stroke="{INK}" stroke-width="{ow}" stroke-linejoin="round">{shapes}</g>'
        f'<g transform="{t}" fill="{MINT_D}" stroke="{MINT_D}" stroke-width="{ow-2*rim}" stroke-linejoin="round">{shapes}</g>'
        f'<g transform="{t}"><circle cx="0" cy="0" r="{0.21*s}" fill="{WHITE}"/>'
        f'<circle cx="0" cy="0" r="{0.21*s}" fill="none" stroke="{INK}" stroke-width="{rim*1.3}"/></g>')


def chip(x, y, w, h, label, rot=0, color=BLUE_M):
    r, cut = 14, 26
    d = (f"M{x} {y+r} Q{x} {y} {x+r} {y} L{x+w-cut} {y} L{x+w} {y+cut} "
         f"L{x+w} {y+h-r} Q{x+w} {y+h} {x+w-r} {y+h} L{x+r} {y+h} Q{x} {y+h} {x} {y+h-r} Z")
    fold = f'<path d="M{x+w-cut} {y} L{x+w-cut} {y+cut} L{x+w} {y+cut} Z" fill="{INK}" fill-opacity=".22"/>'
    cx = x + (w-cut)/2 + 2
    lbl, lw = glyphs(POP, label, 30)
    lx = cx - lw/2
    lbltxt = "".join(f'<path transform="translate({lx+gx:.1f} {y+h*0.66:.1f})" d="{dd}"/>' for dd, gx, a, b, s in lbl)
    g = f'<g transform="rotate({rot} {x+w/2} {y+h/2})">'
    SIL.append(f'{g}<path d="{d}"/></g>')
    art = (f'{g}<path d="{d}" transform="translate({SDX*0.6} {SDY*0.6})" fill="{SHADOW}" opacity=".12"/>'
           f'<path d="{d}" fill="{color}" stroke="{INK}" stroke-width="5"/>{fold}'
           f'<g fill="#fff">{lbltxt}</g></g>')
    return art


def asterisk(cx, cy, r, fill=MINT_D):
    lines = "".join(f'<line transform="rotate({a} {cx} {cy})" x1="{cx}" y1="{cy-r}" x2="{cx}" y2="{cy+r}"/>'
                    for a in (0, 60, 120))
    return f'<g stroke="{fill}" stroke-width="{r*0.6}" stroke-linecap="round">{lines}</g>'


def password(x, y, w, h):
    d = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h/2}"/>'
    SIL.append(d)
    sh = f'<rect x="{x+SDX*0.6}" y="{y+SDY*0.6}" width="{w}" height="{h}" rx="{h/2}" fill="{SHADOW}" opacity=".12"/>'
    stars = "".join(asterisk(x + w*0.5 + (i-2.5)*w*0.145, y+h*0.5, h*0.17) for i in range(6))
    return (f'{sh}<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h/2}" '
            f'fill="{NAVY}" stroke="{INK}" stroke-width="5"/>{stars}')


def swirl(d, w=7, color=MINT_D):
    """Mint ribbon with a white casing so it reads as part of the sticker."""
    return (f'<path d="{d}" fill="none" stroke="{WHITE}" stroke-width="{w+16}" stroke-linecap="round"/>'
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{w}" stroke-linecap="round"/>')


DEFS = (
    '<defs>'
    f'<linearGradient id="renG" x1="0" y1="0" x2="0" y2="1">'
    f'<stop offset="0" stop-color="{REN_T}"/><stop offset="1" stop-color="{REN_B}"/></linearGradient>'
    f'<linearGradient id="moriG" x1="0" y1="0" x2="0" y2="1">'
    f'<stop offset="0" stop-color="{MORI_T}"/><stop offset="1" stop-color="{MORI_B}"/></linearGradient>'
    '</defs>'
)


def wordmark(x0, base, size):
    gl, w = glyphs(POP, "RenMori", size, tracking=-4)
    bounce = [0, -6, 2, -10, 0, -3, -7]
    tilt   = [-3, 2, -1, 3, 0, 2, 5]
    fills  = ["url(#renG)"]*3 + ["url(#moriG)"]*4
    face_i = 4
    _, gx_o, adv_o, bb_o, s_o = gl[face_i]
    o_w = (bb_o[2]-bb_o[0]) * s_o
    cx, cy = x0 + gx_o + adv_o/2.0, base - size*0.285
    R = o_w*0.60
    FILL_W = OUT - 2*RIM
    shadow, outline, fill = [], [], []
    for i, (d, gx, adv, bb, s) in enumerate(gl):
        if i == face_i:
            continue
        tr = f"translate({x0+gx:.2f} {base+bounce[i]:.2f}) rotate({tilt[i]} {adv/2:.1f} {-size*0.3:.1f})"
        SIL.append(f'<path transform="{tr}" d="{d}"/>')
        shadow.append(f'<path transform="translate({SDX} {SDY}) {tr}" d="{d}"/>')
        outline.append(f'<path transform="{tr}" d="{d}"/>')
        fill.append(f'<path transform="{tr}" d="{d}" fill="{fills[i]}" stroke="{fills[i]}" '
                    f'stroke-width="{FILL_W}" stroke-linejoin="round" stroke-linecap="round"/>')
    # sticker-style weight: fat ink silhouette, then inset gradient body
    s = (f'<g fill="{SHADOW}" stroke="{SHADOW}" stroke-width="{OUT}" stroke-linejoin="round" '
         f'stroke-linecap="round" opacity=".16">{"".join(shadow)}</g>'
         f'<g fill="{INK}" stroke="{INK}" stroke-width="{OUT}" stroke-linejoin="round" '
         f'stroke-linecap="round">{"".join(outline)}</g>'
         f'<g>{"".join(fill)}</g>'
         f'{lock_o(cx, cy, R)}')
    return s, w


def build():
    SIL.clear()
    x0, base, size = 150, 470, 210
    wm, w = wordmark(x0, base, size)
    wm_right = x0 + w

    # katakana nestled just above the 'en' of Ren
    glw, _ = glyphs(POP, "RenMori", size, tracking=-4)
    en_cx = x0 + (glw[1][1] + glw[2][1] + glw[2][2]) / 2
    kana, kw = text_block("レンモリ", 68, en_cx, base - size + 25, NAVY,
                          tracking=16, anchor="middle", outline=0, shadow=False)
    # fill the seam between the katakana and the wordmark tops
    SIL.append(f'<line x1="{en_cx-kw/2+10}" y1="{base-size+42}" x2="{en_cx+kw/2-10}" y2="{base-size+42}"/>')
    # slogan below
    slog, sw = text_block("Ren'Py Resource Protector", 50, x0 + w/2 + 10, base + 108, NAVY,
                          tracking=0.5, anchor="middle", outline=0, shadow=False)

    # a little key charm where the wordmark ends — pairs with the keyhole 'o' (守)
    charm = key(wm_right + 46, base - size + 58, 52, rot=26)

    # contiguous bottom row: three file chips + password pill, centred, no gaps
    cyc = base + 150
    cw, ov = [126, 138, 146], 14
    pw_w, pw_h, gap_cp = 280, 72, 40
    row_w = cw[0] + (cw[1]-ov) + (cw[2]-ov) + gap_cp + pw_w
    rx = x0 + (w - row_w)/2
    c1 = rx; c2 = c1 + cw[0] - ov; c3 = c2 + cw[1] - ov; pwx = c3 + cw[2] + gap_cp
    chips = (chip(c1, cyc,   cw[0], 100, "rpa",  rot=-5)
             + chip(c2, cyc-6, cw[1], 100, "rpym", rot=4)
             + chip(c3, cyc+2, cw[2], 100, "rpyc", rot=-3))
    pw = password(pwx, cyc + 14, pw_w, pw_h)

    # single filler to fuse wordmark <-> slogan (the bottom row merges by proximity)
    SIL.append(f'<line x1="{x0+180}" y1="{base+42}" x2="{wm_right-180}" y2="{base+42}"/>')

    # one decorative gold swirl on the left (sits just above the die-cut so the casing merges)
    swirls = swirl(f"M{x0+10} {base-size*0.2} C{x0-40} {base-size*0.5} {x0+30} {base-size*0.95} {x0+70} {base-size-30}", 7)

    sparkles = (sparkle(x0 + 40, base - size*0.5, 18)
                + sparkle(x0 + w*0.42, base - size - 46, 15, fill=MINT_L)
                + sparkle(wm_right + 72, base - size + 34, 18)
                + sparkle(x0 + w*0.62, base - size*0.2, 12, fill=MINT_L))

    # ---- die-cut base (merged sticker silhouette) + its shadow ----
    sil = "".join(SIL)
    base_shadow = (f'<g transform="translate(0 18)" fill="{SHADOW}" stroke="{SHADOW}" opacity=".16" '
                   f'stroke-width="{DIECUT*2}" stroke-linejoin="round" stroke-linecap="round">{sil}</g>')
    diecut = (f'<g fill="{WHITE}" stroke="{WHITE}" stroke-width="{DIECUT*2}" '
              f'stroke-linejoin="round" stroke-linecap="round">{sil}</g>')

    # ---- tight viewBox around the content ----
    vx, vy = 92, 150
    vw = int(wm_right + 158 - vx)
    vh = int(base + 312 - vy)
    body = (base_shadow + diecut + swirls + kana + wm + charm + slog + chips + pw + sparkles)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx} {vy} {vw} {vh}" '
           f'width="{vw}" height="{vh}">'
           f'{DEFS}<title>RenMori</title>{body}</svg>')
    return svg


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    p = os.path.join(out, "renmori-protector.svg")
    open(p, "w").write(build())
    print("wrote", p)
