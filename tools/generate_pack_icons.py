"""
Generate editable pixel-art versions of the Icons8 social-media and character
packs, KEEPING each icon's ORIGINAL colors (no theme recoloring).

This is the companion to generate_tile_icons.py. That one recolors icons into the
active theme palette; THIS one paints each icon in its own literal colors so the
packs keep their native look while staying hand-editable pixel grids. To theme an
icon instead, move it into generate_tile_icons.py.

Drawn on a 32x32 grid (flat colors, no AA), scaled x2 (NEAREST) to 64px.
Output: assets/icons/tile icons/<set> pixel/<key>.png

Run:  python tools/generate_pack_icons.py [set ...]
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT_BASE = ROOT / "assets" / "icons" / "tile icons"
BASE = 32
SCALE = 2


# ── grid painter (one char per pixel; "." = transparent) ─────────────────────
def _draw_grid(d, grid, tones):
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch != ".":
                d.point((x, y), fill=tones[ch])


def _new():
    im = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def _save(im, out_folder, key):
    d = OUT_BASE / out_folder
    d.mkdir(parents=True, exist_ok=True)
    im.resize((BASE * SCALE, BASE * SCALE), Image.NEAREST).save(d / f"{key}.png")


# ── icons (natural colors preserved; each grid is hand-editable) ─────────────
_ADOBE_ILLUSTRATOR_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "....bbaaaaaaaaaaaaaaaaaaaabb....",
    "....bbaaaaaaaaaaaaaaaaaaaabb....",
    "....bbaaaaaaaaaaaaaaaaaaaabb....",
    "....bbaaaaaaaaaaaaaaaaaaaabb....",
    "....bbaaaaaaabbaaaaaaaaaaabb....",
    "....bbaaaaaaabbaaaaaaaaaaabb....",
    "....bbaaaaabbaabbaaaabbaaabb....",
    "....bbaaaaabbaabbaaaabbaaabb....",
    "....bbaaabbaaaaaabbaaaaaaabb....",
    "....bbaaabbaaaaaabbaaaaaaabb....",
    "....bbaaabbaaaaaabbaabbaaabb....",
    "....bbaaabbbbbbbbbbaabbaaabb....",
    "....bbaaabbbbbbbbbbaabbaaabb....",
    "....bbaaabbaaaaaabbaabbaaabb....",
    "....bbaaabbaaaaaabbaabbaaabb....",
    "....bbaaabbaaaaaabbaabbaaabb....",
    "....bbaaaaaaaaaaaaaaaaaaaabb....",
    "....bbaaaaaaaaaaaaaaaaaaaabb....",
    "....bbaaaaaaaaaaaaaaaaaaaabb....",
    "....bbaaaaaaaaaaaaaaaaaaaabb....",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "................................",
    "................................",
    "................................",
    "................................",
]
_ADOBE_ILLUSTRATOR_TONES = {"a": "#B4252C", "b": "#F18F06"}

def adobe_illustrator(d):   # icons8-adobe-illustrator-64.png
    _draw_grid(d, _ADOBE_ILLUSTRATOR_GRID, _ADOBE_ILLUSTRATOR_TONES)


_ADOBE_PHOTOSHOP_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "....bbaaaaaaaaaaaaaaaaaaaabb....",
    "....bbaaaaaaaaaaaaaaaaaaaabb....",
    "....bbaaaaaaaaaaaaaaaaaaaabb....",
    "....bbaaaaaaaaaaaaaaaaaaaabb....",
    "....bbaabbbbbbaaaaaaaaaaaabb....",
    "....bbaabbbbbbaaaaaaaaaaaabb....",
    "....bbaabbaaaabbaaaabbbbaabb....",
    "....bbaabbaaaabbaaaabbbbaabb....",
    "....bbaabbaaaabbaabbaaaaaabb....",
    "....bbaabbaaaabbaabbaaaaaabb....",
    "....bbaabbbbbbaaaaaabbaaaabb....",
    "....bbaabbbbbbaaaaaabbaaaabb....",
    "....bbaabbaaaaaaaaaaaabbaabb....",
    "....bbaabbaaaaaaaaaaaabbaabb....",
    "....bbaabbaaaaaaaabbbbaaaabb....",
    "....bbaabbaaaaaaaabbbbaaaabb....",
    "....bbaaaaaaaaaaaaaaaaaaaabb....",
    "....bbaaaaaaaaaaaaaaaaaaaabb....",
    "....bbaaaaaaaaaaaaaaaaaaaabb....",
    "....bbaaaaaaaaaaaaaaaaaaaabb....",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "......bbbbbbbbbbbbbbbbbbbb......",
    "................................",
    "................................",
    "................................",
    "................................",
]
_ADOBE_PHOTOSHOP_TONES = {"a": "#085195", "b": "#589BD4"}

def adobe_photoshop(d):     # icons8-adobe-photoshop-64.png
    _draw_grid(d, _ADOBE_PHOTOSHOP_GRID, _ADOBE_PHOTOSHOP_TONES)


_ANDROID_OS_GRID = [
    "................................",
    "................................",
    "............aa....aa............",
    "............dd....dd............",
    "..........aeccbddbccea..........",
    "..........aeeeeeeeeeea..........",
    "........aeceffecceffecea........",
    "........aeceffecceffecea........",
    "........aeeeeeeeeeeeeeea........",
    "........adaaccaaaaccaada........",
    "................................",
    "................................",
    "....db..cedbbbbbbbbbbdea..db....",
    "....da..ceeeeeeeeeeeeeea..db....",
    "..deed..aeaaaaaaaaaaaaea..beea..",
    "..deeb..ceaddddddddddaea..ceea..",
    "..deeb..ceaddddddddddaea..ceea..",
    "..deeb..ceaddddddddddaea..ceea..",
    "..deeb..ceaddddddddddaea..ceea..",
    "..aded..ceaddddddddddaea..beda..",
    "....ca..ceaddddddddddaea..dd....",
    "....da..aeadddaaaadddaea..dd....",
    "........aeadddeeeedddaea........",
    "........aeddddbddbddddea........",
    "..........aeea....ceea..........",
    "..........aeea....aeea..........",
    "..........aeea....aeea..........",
    "..........aeea....aeea..........",
    "..........aeea....aeea..........",
    "..........ceeb....ceeb..........",
    "................................",
    "................................",
]
_ANDROID_OS_TONES = {"a": "#90C04B", "b": "#91C04A", "c": "#90C14A", "d": "#91C14B", "e": "#92C14C", "f": "#E5E4E3"}

def android_os(d):          # icons8-android-os-64.png
    _draw_grid(d, _ANDROID_OS_GRID, _ANDROID_OS_TONES)


_APPLE_INC_GRID = [
    "................................",
    "................................",
    "....................ee..........",
    "....................ee..........",
    "..................fgge..........",
    "..................egge..........",
    "................eggg............",
    "................fgge............",
    "................................",
    "................................",
    "......fgeeeege....egeeeegg......",
    "......eggggggg....egggggge......",
    "....fgfeeeeeegeeeegeeegedcca....",
    "....egegggggggggggggggeedaca....",
    "....egegggggggeeeegggeddcb......",
    "....egegggggggggggggeedacb......",
    "....gggggggggggggggeddca........",
    "....efeeeeeeeeeeeeeedacb........",
    "....dcddddddddddddddbbdb........",
    "....adaaaaaaaaaaaaaabbda........",
    "....adbbbbbbbbbbbbbbbbbbdb......",
    "....bdbbbbbbbbbbbbbbbbbbcb......",
    "....acbbbbbbbbbbbbbbbbbbbada....",
    "....bdbbbbbbbbbbbbbbbbbbbada....",
    "......bcbbbbbbbbbbbbbbbbcb......",
    "......bdbbbbbbbbbbbbbbbbdb......",
    "........bcbbbbcddcbbbbcb........",
    "........bdbbbabbbbabbbdb........",
    "..........bccb....bccb..........",
    "..........acca....acca..........",
    "................................",
    "................................",
]
_APPLE_INC_TONES = {"a": "#26649F", "b": "#26659F", "c": "#2765A0", "d": "#27669F", "e": "#589AD3", "f": "#589AD4", "g": "#589BD4"}

def apple_inc(d):           # icons8-apple-inc-64.png
    _draw_grid(d, _APPLE_INC_GRID, _APPLE_INC_TONES)


_CHROME_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..........abbbbbbbbbba..........",
    "..........bdbbbbbbbbda..........",
    "........abbaaaaaaaaaaaba........",
    "........bdabbbddddbbbcda........",
    "......abbabbbbbbbbbbbbaaba......",
    "......aeabbbddffffffffffff......",
    "....ghcbabbdbfvvvvspppppppqp....",
    "....ghcccadefftxutsssqqqqqqp....",
    "....glhhcbafvtooootvsprqqpqp....",
    "....glkhcffftuommoutsssqqpqp....",
    "....gghhhlttoonmmnootvsqrpqp....",
    "....gggjgltwomnmmnmouvsqrpqp....",
    "....gggjhltwomnmmnmowvsqrpqp....",
    "....gggjglttoonmmnootvsqrpqp....",
    "....gggggjlltuommoutsssqqpqp....",
    "....gggggjglttooootvsqrqqpqp....",
    "....glggggillltwwtsssrqqqpqp....",
    "....gggggggjglttttsqrqqqpqqp....",
    "......glggggijllllpqqqqpqp......",
    "......gggggggggggkpqqqpqqp......",
    "........glggggjjjkpqqpqp........",
    "........ggggggghkkpqpqqp........",
    "..........glgljkppqqqp..........",
    "..........gggigkpqqqqp..........",
    "................................",
    "................................",
    "................................",
    "................................",
]
_CHROME_TONES = {"a": "#E31E2F", "b": "#E41E2F", "c": "#E31F2F", "d": "#E41F30", "e": "#E42031", "f": "#E42131", "g": "#00953F", "h": "#02943F", "i": "#01953F", "j": "#019540", "k": "#02963F", "l": "#029641", "m": "#589BD4", "n": "#599BD4", "o": "#5A9CD5", "p": "#FBC101", "q": "#FCC201", "r": "#FCC202", "s": "#FCC203", "t": "#E4E4E2", "u": "#E4E4E4", "v": "#E6E4E2", "w": "#E5E4E5", "x": "#E4E5E4"}

def chrome(d):              # icons8-chrome-64.png
    _draw_grid(d, _CHROME_GRID, _CHROME_TONES)


_DISCORD_NEW_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    ".........aaaa......aaaa.........",
    ".........aaaa......aaaa.........",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaabbbbaaaaaabbbbaaaaa....",
    "..aaaaaaabbbbaaaaaabbbbaaaaaaa..",
    "..aaaaaaabbbbaaaaaabbbbaaaaaaa..",
    "..aaaaaaabbbbaaaaaabbbbaaaaaaa..",
    "..aaaaaaabbbbaaaaaabbbbaaaaaaa..",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "..aaaaaaaaaaaaaaaaaaaaaaaaaaaa..",
    "....aaaaaaaa........aaaaaaaa....",
    "....aaaaaaaa........aaaaaaaa....",
    ".......aaa............aaa.......",
    ".......aaa............aaa.......",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_DISCORD_NEW_TONES = {"a": "#085295", "b": "#E6E5E5"}

def discord_new(d):         # icons8-discord-new-64.png
    _draw_grid(d, _DISCORD_NEW_GRID, _DISCORD_NEW_TONES)


_FACEBOOK_MESSENGER_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "..aaaaaaaaaaaabbaaaaaaaaaaaaaa..",
    "..aaaaaaaaaaaabbaaaaaaaaaaaaaa..",
    "..aaaaaaaaaabbbbbbaaaabbaaaaaa..",
    "..aaaaaaaaaabbbbbbaaaabbaaaaaa..",
    "..aaaaaaaabbbbbbbbbbbbaaaaaaaa..",
    "..aaaaaaaabbbbbbbbbbbbaaaaaaaa..",
    "..aaaaaabbaaaabbbbbbaaaaaaaaaa..",
    "..aaaaaabbaaaabbbbbbaaaaaaaaaa..",
    "..aaaaaaaaaaaaaabbaaaaaaaaaaaa..",
    "..aaaaaaaaaaaaaabbaaaaaaaaaaaa..",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaa........",
    "......aaaaaaaaaaaaaaaaaa........",
    "....aaaaaa......................",
    "....aaaaaa......................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_FACEBOOK_MESSENGER_TONES = {"a": "#589BD4", "b": "#E6E5E5"}

def facebook_messenger(d):  # icons8-facebook-messenger-64.png
    _draw_grid(d, _FACEBOOK_MESSENGER_GRID, _FACEBOOK_MESSENGER_TONES)


_GITHUB_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "......aaaaabbaaaaaabbaaaaa......",
    "......aaaaabbaaaaaabbaaaaa......",
    "....aaaaaaabbbbbbbbbbaaaaaaa....",
    "....aaaaaaabbbbbbbbbbaaaaaaa....",
    "....aaaaabbbbbbbbbbbbbbaaaaa....",
    "....aaaaabbbbbbbbbbbbbbaaaaa....",
    "....aaaaabbbbbbbbbbbbbbaaaaa....",
    "....aaaaabbbbbbbbbbbbbbaaaaa....",
    "....aaaaabbbbbbbbbbbbbbaaaaa....",
    "....aaaaabbbbbbbbbbbbbbaaaaa....",
    "....aaaaaaabbbbbbbbbbaaaaaaa....",
    "....aaaaaaabbbbbbbbbbaaaaaaa....",
    "....aaaabbaaabbbbbbaaaaaaaaa....",
    "....aaaabbaaabbbbbbaaaaaaaaa....",
    "......aaaabbbbbbbbbaaaaaaa......",
    "......aaaabbbbbbbbbaaaaaaa......",
    "........aaaaabbbbbbaaaaa........",
    "........aaaaabbbbbbaaaaa........",
    "..........aaabbbbbbaaa..........",
    "..........aaabbbbbbaaa..........",
    "................................",
    "................................",
    "................................",
    "................................",
]
_GITHUB_TONES = {"a": "#085295", "b": "#E6E5E5"}

def github(d):              # icons8-github-64.png
    _draw_grid(d, _GITHUB_GRID, _GITHUB_TONES)


_GMAIL_LOGO_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "....aaaaabbbbbbbbbbbbbbaaaaa....",
    "....aaaaabbbbbbbbbbbbbbaaaaa....",
    "..aaaaaaaaabbbbbbbbbbaaaaaaaaa..",
    "..aaaaaaaaabbbbbbbbbbaaaaaaaaa..",
    "..aaaabbaaaaabbbbbbaaaaabbaaaa..",
    "..aaaabbaaaaabbbbbbaaaaabbaaaa..",
    "..aaaabbbbaaaaabbaaaaabbbbaaaa..",
    "..aaaabbbbaaaaabbaaaaabbbbaaaa..",
    "..aaaabbbbbbaaaaaaaabbbbbbaaaa..",
    "..aaaabbbbbbaaaaaaaabbbbbbaaaa..",
    "..aaaabbbbbbbbaaaabbbbbbbbaaaa..",
    "..aaaabbbbbbbbaaaabbbbbbbbaaaa..",
    "..aaaabbbbbbbbbbbbbbbbbbbbaaaa..",
    "..aaaabbbbbbbbbbbbbbbbbbbbaaaa..",
    "..aaaabbbbbbbbbbbbbbbbbbbbaaaa..",
    "..aaaabbbbbbbbbbbbbbbbbbbbaaaa..",
    "..aaaabbbbbbbbbbbbbbbbbbbbaaaa..",
    "..aaaabbbbbbbbbbbbbbbbbbbbaaaa..",
    "....aabbbbbbbbbbbbbbbbbbbbaa....",
    "....aabbbbbbbbbbbbbbbbbbbbaa....",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_GMAIL_LOGO_TONES = {"a": "#E41E2F", "b": "#E6E5E5"}

def gmail_logo(d):          # icons8-gmail-logo-64.png
    _draw_grid(d, _GMAIL_LOGO_GRID, _GMAIL_LOGO_TONES)


_GOOGLE_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "...........bbbbbbbbbbb..........",
    "...........bbbbbbbbbbb..........",
    "........bbbbbbbbbbbbbbbbb.......",
    "........bbbbbbbbbbbbbbbbb.......",
    "......bbbbbbbbbbbbbbbbbbbbb.....",
    "......bbbbbbb.......bbbbbbb.....",
    "......bbbbbbb.......bbbbbbb.....",
    "....dddddbb............bb.......",
    "....dddddbb............bb.......",
    "....ddddd.......................",
    "....ddddd.......................",
    "....ddddd........aaaaaaaaaaa....",
    "....ddddd........aaaaaaaaaaa....",
    "....ddddd........aaaaaaaaaaa....",
    "....ddddd.............aaaaaa....",
    "....dddddcc...........aaaaaa....",
    "....dddddcc...........aaaaaa....",
    "......ccccc...........aaaaaa....",
    "......ccccccccc.....ccccaa......",
    "......ccccccccc.....ccccaa......",
    "........cccccccccccccccc........",
    "........cccccccccccccccc........",
    "...........ccccccccccc..........",
    "...........ccccccccccc..........",
    "................................",
    "................................",
    "................................",
    "................................",
]
_GOOGLE_TONES = {"a": "#26659F", "b": "#E41E2F", "c": "#91C14B", "d": "#FCC201"}

def google(d):              # icons8-google-64.png
    _draw_grid(d, _GOOGLE_GRID, _GOOGLE_TONES)


_GOOGLE_MAPS_GRID = [
    "................................",
    "................................",
    "..........aaaaaaacccccc.........",
    "..........aaaaaaacccccc.........",
    ".......aaaaaaaacccccccccc.......",
    ".......aaaaaaaacccccccccc.......",
    ".......bbaaaa......cccccc.......",
    ".......bbaaaa......cccccc.......",
    ".....bbbbbb..........ccdddd.....",
    ".....bbbbbb..........ccdddd.....",
    ".....bbbbee..........dddddd.....",
    ".....bbbbee..........dddddd.....",
    ".....bbbbee..........dddddd.....",
    ".....bbeeee..........dddddd.....",
    ".....bbeeeeee......dddddddd.....",
    ".......eeeeee......dddddd.......",
    ".......eeeeeeeeeedddddddd.......",
    ".......eeeeeeeeeedddddddd.......",
    ".......eeeeeeeedddddddddd.......",
    ".........eeeeeedddddddd.........",
    ".........eeeedddddddddd.........",
    ".........eeeedddddddddd.........",
    "...........dddddddddd...........",
    "...........dddddddddd...........",
    ".............dddddd.............",
    ".............dddddd.............",
    ".............dddddd.............",
    "...............dd...............",
    "...............dd...............",
    "...............dd...............",
    "................................",
    "................................",
]
_GOOGLE_MAPS_TONES = {"a": "#26659F", "b": "#E41E2F", "c": "#589BD4", "d": "#91C14B", "e": "#FCC201"}

def google_maps(d):         # icons8-google-maps-64.png
    _draw_grid(d, _GOOGLE_MAPS_GRID, _GOOGLE_MAPS_TONES)


_INSTAGRAM_OLD_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    ".......aaffeeccdddddddddd.......",
    ".......aaffeeccdddddddddd.......",
    "....dddaaffeeccddddddddddddd....",
    "....dddaaffeeccddddddddddddd....",
    "....dddaaffeeccddddddddddddd....",
    "....dddaaffeehhhhhhddddddddd....",
    "....dddaaffeehhhhhhddddddddd....",
    "....dddaaffhhbbbbbbhhddddddd....",
    "....dddaaffhhbbbbbbhhddddddd....",
    "....ggggghhbbhhbbbbbbhhggggg....",
    "....ggggghhbbhhbbbbbbhhggggg....",
    "....ggggghhbbbbbbbbbbhhggggg....",
    "....ggggghhbbbbbbbbbbhhggggg....",
    "....ggggghhbbbbbbbbbbhhggggg....",
    "....ggggghhbbbbbbbbbbhhggggg....",
    "....ggggggghhbbbbbbhhggggggg....",
    "....ggggggghhbbbbbbhhggggggg....",
    "....ggggggggghhhhhhggggggggg....",
    "....ggggggggghhhhhhggggggggg....",
    "....gggggggggggggggggggggggg....",
    "....gggggggggggggggggggggggg....",
    "....gggggggggggggggggggggggg....",
    ".......gggggggggggggggggg.......",
    ".......gggggggggggggggggg.......",
    "................................",
    "................................",
    "................................",
    "................................",
]
_INSTAGRAM_OLD_TONES = {"a": "#E41E2F", "b": "#706D67", "c": "#589BD4", "d": "#D38754", "e": "#91C14B", "f": "#FCC201", "g": "#F9C292", "h": "#E6E5E5"}

def instagram_old(d):       # icons8-instagram-old-64.png
    _draw_grid(d, _INSTAGRAM_OLD_GRID, _INSTAGRAM_OLD_TONES)


_MCDONALD_S_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    ".........aaa.........aaa........",
    ".........aaa.........aaa........",
    ".........aaa.........aaa........",
    "......aaa...aaa...aaa...aaa.....",
    "......aaa...aaa...aaa...aaa.....",
    "......aaa...aaa...aaa...aaa.....",
    "...aaa.........aaa.........aaa..",
    "...aaa.........aaa.........aaa..",
    "...aaa.........aaa.........aaa..",
    "...aaa.........aaa.........aaa..",
    "...aaa.........aaa.........aaa..",
    "...aaa.........aaa.........aaa..",
    "...aaa.........aaa.........aaa..",
    "...aaa.........aaa.........aaa..",
    "...aaa.........aaa.........aaa..",
    "...aaa.........aaa.........aaa..",
    "...aaa.........aaa.........aaa..",
    "...aaa.........aaa.........aaa..",
    "...aaa.........aaa.........aaa..",
    "...aaa.........aaa.........aaa..",
    "...aaa.........aaa.........aaa..",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_MCDONALD_S_TONES = {"a": "#FFCB03"}

def mcdonald_s(d):          # icons8-mcdonald`s-64.png
    _draw_grid(d, _MCDONALD_S_GRID, _MCDONALD_S_TONES)


_MICROSOFT_EXCEL_2019_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..........cccccccccbbbbbbbbb....",
    "..........cccccccccbbbbbbbbb....",
    "..........cccccccccbbbbbbbbb....",
    "..........aaaaaaaaabbbbbbbbb....",
    "..........aaaaaaaaabbbbbbbbb....",
    "..........aaaaaaaaabbbbbbbbb....",
    "....bbbbbbbbbbbbaaaccccccccc....",
    "....bbbbbbbbbbbbaaaccccccccc....",
    "....bbddbbbbddbbaaaccccccccc....",
    "....bbddbbbbddbbaaaccccccccc....",
    "....bbddbbbbddbbaaaccccccccc....",
    "....bbbbddddbbbbaaaccccccccc....",
    "....bbbbddddbbbbaaabbbbbbbbb....",
    "....bbddbbbbddbbaaabbbbbbbbb....",
    "....bbddbbbbddbbaaabbbbbbbbb....",
    "....bbddbbbbddbbaaabbbbbbbbb....",
    "....bbbbbbbbbbbbaaabbbbbbbbb....",
    "....bbbbbbbbbbbbaaabbbbbbbbb....",
    "..........aaaaaaaaaaaaaaaaaa....",
    "..........aaaaaaaaaaaaaaaaaa....",
    "..........aaaaaaaaaaaaaaaaaa....",
    "..........aaaaaaaaaaaaaaaaaa....",
    "..........aaaaaaaaaaaaaaaaaa....",
    "..........aaaaaaaaaaaaaaaaaa....",
    "................................",
    "................................",
    "................................",
    "................................",
]
_MICROSOFT_EXCEL_2019_TONES = {"a": "#00953F", "b": "#91C14B", "c": "#BDD94E", "d": "#E6E5E5"}

def microsoft_excel_2019(d): # icons8-microsoft-excel-2019-64.png
    _draw_grid(d, _MICROSOFT_EXCEL_2019_GRID, _MICROSOFT_EXCEL_2019_TONES)


_MICROSOFT_WORD_2019_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..........dddddddddddddddddd....",
    "..........dddddddddddddddddd....",
    "..........dddddddddddddddddd....",
    "..........dddddddddddddddddd....",
    "..........dddddddddddddddddd....",
    "..........dddddddddddddddddd....",
    "....aaaaaaaaaaaacccccccccccc....",
    "....aaaaaaaaaaaacccccccccccc....",
    "....aaaaaaaaaaaacccccccccccc....",
    "....aeeaaeeaaeeacccccccccccc....",
    "....aeeaaeeaaeeacccccccccccc....",
    "....aeeaaeeaaeeacccccccccccc....",
    "....aeebbeebbeeabbbbbbbbbbbb....",
    "....aabeebbeebaabbbbbbbbbbbb....",
    "....aaaeeaaeeaaabbbbbbbbbbbb....",
    "....aaaaaaaaaaaabbbbbbbbbbbb....",
    "....aaaaaaaaaaaabbbbbbbbbbbb....",
    "....aaaaaaaaaaaabbbbbbbbbbbb....",
    "..........aaaaaaaaaaaaaaaaaa....",
    "..........aaaaaaaaaaaaaaaaaa....",
    "..........aaaaaaaaaaaaaaaaaa....",
    "..........aaaaaaaaaaaaaaaaaa....",
    "..........aaaaaaaaaaaaaaaaaa....",
    "..........aaaaaaaaaaaaaaaaaa....",
    "................................",
    "................................",
    "................................",
    "................................",
]
_MICROSOFT_WORD_2019_TONES = {"a": "#085295", "b": "#26659F", "c": "#3F80B9", "d": "#589BD4", "e": "#E6E5E5"}

def microsoft_word_2019(d): # icons8-microsoft-word-2019-64.png
    _draw_grid(d, _MICROSOFT_WORD_2019_GRID, _MICROSOFT_WORD_2019_TONES)


_NOTIFICATION_GRID = [
    "................................",
    "................................",
    "................................",
    "..............acca..............",
    "..............cccb..............",
    "..............dffd..............",
    "..............fffd..............",
    "............dfdffdfd............",
    "............dfdffdfd............",
    "..........dffdffffdffd..........",
    "..........dfdffffffdfd..........",
    "..........dfdffffffdfd..........",
    "..........dfdffffffdfd..........",
    "..........dfdffffffdfd..........",
    "..........dfdffffffdfd..........",
    "..........dfdffffffdfd..........",
    "..........ggeggggggege..........",
    "........dfdffffffffffdfd........",
    "........gggggggggggggggg........",
    "......iihhhhhhhhhhhhhhhhii......",
    "......hihhhhhhhhhhhhhhhhih......",
    "....dfggggggggggggggggggggfd....",
    "....dfddddddffffffffddddddfd....",
    "....dfggggggffffffffggggggfd....",
    "....dffffffddddddddddffffffd....",
    "............cccccccb............",
    "............acaaaaca............",
    "..............bcca..............",
    "..............acca..............",
    "................................",
    "................................",
    "................................",
]
_NOTIFICATION_TONES = {"a": "#F08E06", "b": "#F08F06", "c": "#F18F06", "d": "#FBC101", "e": "#FBC102", "f": "#FCC201", "g": "#FCC202", "h": "#FFEB8D", "i": "#FFEC8E"}

def notification(d):        # icons8-notification-64.png
    _draw_grid(d, _NOTIFICATION_GRID, _NOTIFICATION_TONES)


_SPOTIFY_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "....aaaaabbbbbbbbbbaaaaaaaaa....",
    "....aaaaabbbbbbbbbbaaaaaaaaa....",
    "....aaaaaaaaaaaaaaabbbbaaaaa....",
    "....aaaaaaaaaaaaaaabbbbaaaaa....",
    "....aaaaaabbbbbbbaaaaaaaaaaa....",
    "....aaaaaabbbbbbbaaaaaaaaaaa....",
    "....aaaaaaaaaaaaabbbbbaaaaaa....",
    "....aaaaaaaaaaaaabbbbbaaaaaa....",
    "....aaaaaaabbbbaaaaaaaaaaaaa....",
    "....aaaaaaabbbbaaaaaaaaaaaaa....",
    "....aaaaaaaaaaabbbbaaaaaaaaa....",
    "....aaaaaaaaaaabbbbaaaaaaaaa....",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "................................",
    "................................",
    "................................",
    "................................",
]
_SPOTIFY_TONES = {"a": "#91C14B", "b": "#E6E5E5"}

def spotify(d):             # icons8-spotify-64.png
    _draw_grid(d, _SPOTIFY_GRID, _SPOTIFY_TONES)


_STEAM_CIRCLED_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "......aaaaaaaaaaaabbbbbbaa......",
    "......aaaaaaaaaaaabbbbbbaa......",
    "....aaaaaaaaaaaabbaaaaaabbaa....",
    "....aaaaaaaaaaaabbaaaaaabbaa....",
    "....aaaaaaaaaaaabbaabbaabbaa....",
    "....aaaaaaaaaaaabbaabbaabbaa....",
    "....bbaaaaaaaabbbbaaaaaabbaa....",
    "....bbaaaaaaaabbbbaaaaaabbaa....",
    "....bbbbaaaaaabbbbbbbbbbaaaa....",
    "....bbbbaaaabbbbbbbbbbbbaaaa....",
    "....aabbbbaabbbbbbbbaaaaaaaa....",
    "....aabbbbaabbbbbbbbaaaaaaaa....",
    "....aaaabbbbbbbbbaaaaaaaaaaa....",
    "....aaaabbbbbbbbbaaaaaaaaaaa....",
    "......aaaabbbbaaaaaaaaaaaa......",
    "......aaaabbbbaaaaaaaaaaaa......",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "................................",
    "................................",
    "................................",
    "................................",
]
_STEAM_CIRCLED_TONES = {"a": "#085295", "b": "#FFFFFF"}

def steam_circled(d):       # icons8-steam-circled-64.png
    _draw_grid(d, _STEAM_CIRCLED_GRID, _STEAM_CIRCLED_TONES)


_TELEGRAM_APP_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "......aaaaaaaaaaaccccaaaaa......",
    "....aaaaaaaaaaaaaccccaaaaaaa....",
    "....aaaaaaaaaccccccccaaaaaaa....",
    "....aaaaaaaaaccccccccaaaaaaa....",
    "....aaaaaaaccccbbccccaaaaaaa....",
    "....aaaaaaaccccbbccccaaaaaaa....",
    "....aaaacccccbbccccccaaaaaaa....",
    "....aaaacccccbbccccccaaaaaaa....",
    "....aaaaaaabbbbccccccaaaaaaa....",
    "....aaaaaaabbbbccccccaaaaaaa....",
    "....aaaaaaabbaaccccccaaaaaaa....",
    "....aaaaaaabbaaccccccaaaaaaa....",
    "....aaaaaaaaaaaaaaaccaaaaaaa....",
    "......aaaaaaaaaaaaaccaaaaa......",
    "......aaaaaaaaaaaaaaaaaaaa......",
    "........aaaaaaaaaaaaaaaa........",
    "........aaaaaaaaaaaaaaaa........",
    "..........aaaaaaaaaaaa..........",
    "..........aaaaaaaaaaaa..........",
    "................................",
    "................................",
    "................................",
    "................................",
]
_TELEGRAM_APP_TONES = {"a": "#589BD4", "b": "#B6B5B5", "c": "#E6E5E5"}

def telegram_app(d):        # icons8-telegram-app-64.png
    _draw_grid(d, _TELEGRAM_APP_GRID, _TELEGRAM_APP_TONES)


_TERRARIA_GRID = [
    "..............dhhd..............",
    "..............dhhh..............",
    "..........dhdddhjihd............",
    "..........dhhhdhjihd............",
    "..........dhiihdhhfdhd..........",
    "..........ehijhdddfdhh..........",
    "........dhdfhhddfgdhiihd........",
    "........dhhhddhhfgehjihd........",
    "........dhijhhijhdddhhhd........",
    "........dhiihhjjhdhhddhd........",
    "..........hhdfhhdhjihe..........",
    "..........dhdfddehiihd..........",
    "............dhfhhfhh............",
    "............dheeeefd............",
    "..............cccc..............",
    "..............bbbb..............",
    "........dhlm..abba..............",
    "........ghli..abba..............",
    "......fhddhh..abba..dfhd........",
    "......hhhgee..abba..ghhf........",
    "......fhlicc..abba..ilhdhd......",
    "......dhlkcb..abba..kihfhg......",
    "............abaaba..ccehli......",
    "............abbaba..bcehlm......",
    "..............abaaba............",
    "..............abaaba............",
    "..............abba..............",
    "..............abba..............",
    "............ababbbba............",
    "............ababbaba............",
    "..........abbbbbbbbbba..........",
    "..........ababbbbbbaba..........",
]
_TERRARIA_TONES = {"a": "#B3252C", "b": "#B4252C", "c": "#B3262C", "d": "#00943F", "e": "#01943F", "f": "#00953F", "g": "#01953F", "h": "#019640", "i": "#90C04A", "j": "#90C04B", "k": "#91C04A", "l": "#90C14B", "m": "#91C14B"}

def terraria(d):            # icons8-terraria-64.png
    _draw_grid(d, _TERRARIA_GRID, _TERRARIA_TONES)


_VISUAL_GAME_BOY_GRID = [
    "................................",
    "................................",
    "................................",
    ".........aaaaaaaaaaaaaa.........",
    ".........aaaaaaaaaaaaaa.........",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaccccccccccccccaa.......",
    ".......aaccccccccccccccaa.......",
    ".......aaccccccccccccccaa.......",
    ".......aaccccccccccccccaa.......",
    ".......aaccccccccccccccaa.......",
    ".......aaccccccccccccccaa.......",
    ".......aaccccccccccccccaa.......",
    ".......aaccccccccccccccaa.......",
    ".......aaccccccccccccccaa.......",
    ".......aaccccccccccccccaa.......",
    ".......aaccccccccccccccaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".......aaaaaaddaaaaaaaaaa.......",
    ".......aaaaaaddaaaaaaaaaa.......",
    ".......aaaaddddddaabbaaaa.......",
    ".......aaaaddddddaabbaaaa.......",
    ".......aaaaaaddaaaaaaaaaa.......",
    ".......aaaaaaddaaaaaaaaaa.......",
    ".......aaaaaaaaaaaaaaaaaa.......",
    ".........aaaaaaaaaaaaaa.........",
    ".........aaaaaaaaaaaaaa.........",
    "................................",
    "................................",
    "................................",
]
_VISUAL_GAME_BOY_TONES = {"a": "#589BD4", "b": "#FCC402", "c": "#E6E5E5", "d": "#FFED8E"}

def visual_game_boy(d):     # icons8-visual-game-boy-64.png
    _draw_grid(d, _VISUAL_GAME_BOY_GRID, _VISUAL_GAME_BOY_TONES)


_WECHAT_GRID = [
    "................................",
    "................................",
    "................................",
    "........cjeeeeeejd..............",
    "........djjjjjjjjd..............",
    "....cjedggccccccggdejd..........",
    "....cjjjgeggggggegjjjd..........",
    "....cjcgiiggggggiigcjd..........",
    "....cjcgccggggggcchejf..........",
    "..gigeicaacieeicaacdccgc........",
    "..gjceicaacieeicaajjjjjj........",
    "..ejcgggccggghcjkkkkkkkkmk......",
    "..ejcgggiigggijjkmmmmmmmmk......",
    "..gjcgggeeghcjkkmmmmmmmmmmmk....",
    "..giggggggghjjkmkkmmmmmmkkmk....",
    "....cjcgghcjkkmkbbkmmmmkbbkmmk..",
    "....cjcgghcjkmmkbbkmmmmkbbkmmk..",
    "....cjcgghcjkmmmkkmmmmmmkkmkmk..",
    "....ciggghcjkmmmmmmmmmmmmmmkmk..",
    "......cjchgjlmmmmmmmmmmmmmmkmk..",
    "......cjggcjkkmkmmmmmmmmmmmkmk..",
    "......cjjd....mmkmmmmmmmmkmk....",
    "......cgid....kmmkkkkkmmmkmk....",
    "......cd........mmmmmmmmmkmk....",
    "......dc........kmkkkkmkmkmm....",
    "......................mmmk......",
    "......................kmmk......",
    "........................mk......",
    "........................kk......",
    "................................",
    "................................",
    "................................",
]
_WECHAT_TONES = {"a": "#039741", "b": "#726F69", "c": "#90C04A", "d": "#91C04A", "e": "#90C14B", "f": "#92C04B", "g": "#91C14B", "h": "#91C14C", "i": "#92C14C", "j": "#92C24D", "k": "#E5E4E4", "l": "#E5E5E4", "m": "#E6E5E5"}

def wechat(d):              # icons8-wechat-64.png
    _draw_grid(d, _WECHAT_GRID, _WECHAT_TONES)


_WINDOWS_10_GRID = [
    "................................",
    "................................",
    "................................",
    ".......................bcaaca...",
    ".......................acccca...",
    ".........bcca..bcaaaaaacaaaca...",
    ".........acca..accccccccccaca...",
    "...bcaaaacaca..acaaaaaacccaca...",
    "...accccccaca..acaccccccccaca...",
    "...acaaaacaca..acaccccccccaca...",
    "...acaccccaca..acaccccccccaca...",
    "...acaccccaca..acaccccccccaca...",
    "...acaaaaaaca..acaaaaaaaaaaca...",
    "...acccccccca..acccccccccccca...",
    "...acaaaaaaca..acaaaaaaaaaaca...",
    "................................",
    "................................",
    "...bcaaaaaaca..bcaaaaaaaaaaca...",
    "...acccccccca..acccccccccccca...",
    "...acaaaaaaca..acaaaaaaaaaaca...",
    "...acaccccaca..acaccccccccaca...",
    "...acaccccaca..acaccccccccaca...",
    "...acaaaacaca..acaccccccccaca...",
    "...accccccaca..acaccccccccaca...",
    "...acaacacaca..acaaaaaacccaca...",
    ".........ccca..accccccccccaca...",
    ".........acca..acaaaacacaaaca...",
    ".......................ccccca...",
    ".......................acaaca...",
    "................................",
    "................................",
    "................................",
]
_WINDOWS_10_TONES = {"a": "#589AD3", "b": "#589AD4", "c": "#589BD4"}

def windows_10(d):          # icons8-windows-10-64.png
    _draw_grid(d, _WINDOWS_10_GRID, _WINDOWS_10_TONES)


_YOUTUBE_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "......ccaaaaaaaaaaaaaaaaca......",
    "......cdccccccccccccccccda......",
    "....accbbbbbbbbbbbbbbbbbbcca....",
    "....cdbcccccddcccccccccccbda....",
    "..cccbccccccaaccccccccccccbccb..",
    "..cdbccccccdeeddddcccccccccbdb..",
    "..ccbccccdaeffeaaacccccccccbcb..",
    "..ccbccccdaeffeeeeddddcccccbcb..",
    "..ccbccccdaefhffffeaaacccccbcb..",
    "..ccbccccdaefhhhhfeeeecccccbcb..",
    "..ccbccccdaefhfgggffffeadccbcb..",
    "..ccbccccdaefhfgggffffeadccbcb..",
    "..ccbccccdaefhhhhfeeeecccccbcb..",
    "..ccbccccdaefhffffeaaacccccbcb..",
    "..ccbccccdaeffeeeeddddcccccbcb..",
    "..ccbccccdaeffeaaacccccccccbcb..",
    "..cdbccccccceeddddcccccccccbdb..",
    "..bccbccccccaaccccccccccccbccc..",
    "....cdbcccccddcccccccccccbda....",
    "....accbbbbbbbbbbbbbbbbbbccb....",
    "......cdccccccccccccccccda......",
    "......acaaaaaaaaaaaaaaaacb......",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_YOUTUBE_TONES = {"a": "#E31E2E", "b": "#E31E2F", "c": "#E41E2F", "d": "#E41F30", "e": "#E42031", "f": "#E6E2E3", "g": "#E6E4E4", "h": "#E6E5E5"}

def youtube(d):             # icons8-youtube-64.png
    _draw_grid(d, _YOUTUBE_GRID, _YOUTUBE_TONES)


_ANONYMOUS_MASK_GRID = [
    "................................",
    "................................",
    "................................",
    ".........dffffffffffffe.........",
    ".........effffffffffffe.........",
    ".....dffefeddddddddddefeffe.....",
    ".....dffffffffffffffffffffe.....",
    ".....dfdeffffffffffffffedfe.....",
    ".....dfdfcccceffffeccccfdfe.....",
    ".....dffcbbbbcffffcbbbbcffe.....",
    ".....dffcbbabccffccbbabcffe.....",
    ".....dfdfeefcbbccbbcfeefdfe.....",
    ".....dfdefffcbbccbbcffffdfe.....",
    ".....dffe....ceddec....dffe.....",
    ".....dffe....ffddff....dffe.....",
    ".....dfdedffddffffddffdfdfe.....",
    ".....dfdffffffffffffffffdfe.....",
    ".....dfdfffddffffffddfffdfe.....",
    ".....dfdfcceffecceffeccfdfe.....",
    ".....dffcbbcffcbbcffcbbcffe.....",
    ".....dffcbbccccbbccccbbcffe.....",
    ".......dfccbbbbccbbbbccfe.......",
    ".......dffcbbbbccbbbbcffe.......",
    ".......dfdeccccffccccedfe.......",
    ".......dfdfffffccffffedfe.......",
    ".........dffffcbbcffffe.........",
    ".........dffefcbbcfeffe.........",
    ".............ffbbff.............",
    ".............fcbbef.............",
    "................................",
    "................................",
    "................................",
]
_ANONYMOUS_MASK_TONES = {"a": "#716E67", "b": "#716E68", "c": "#F7C090", "d": "#F8C191", "e": "#F8C192", "f": "#F9C292"}

def anonymous_mask(d):      # icons8-anonymous-mask-64.png
    _draw_grid(d, _ANONYMOUS_MASK_GRID, _ANONYMOUS_MASK_TONES)


_BATMAN_GRID = [
    "................................",
    "........aa............aa........",
    "........aa............aa........",
    "........aa............aa........",
    "........aa............aa........",
    "........abba........aaba........",
    "........abca........acba........",
    "........acaaaaaaaaaaaaca........",
    "........acaaccccccccaaca........",
    "........acaaaaaaaaaaaaca........",
    "........acaaaaaaaaaaaaca........",
    "........acaaaaaaaaaaaaca........",
    "........acaaaaaaaaaaaaca........",
    "........acaaaaaaaaaaaaca........",
    "........acccccaaaaccccca........",
    "........aciiiicaaciiiica........",
    "........aciiiicaaciiiica........",
    "........acccccaaaaccccca........",
    "........acccaaaaaaaaccca........",
    "........aceecaaaaaaceeca........",
    "........aceecccccccceeca........",
    "........aceheeeeeeeeheca........",
    "........aceehhgggghheeca........",
    "........acccegddddgeccca........",
    "........abacegddddgecaba........",
    "........acacehfggfhecaca........",
    "........abaceehhhheecaba........",
    "..........acccehheccca..........",
    "..........abaceeeecaba..........",
    "............acccccca............",
    "............abaaaaba............",
    "................................",
]
_BATMAN_TONES = {"a": "#706D67", "b": "#716E68", "c": "#726E68", "d": "#F19007", "e": "#F7C191", "f": "#F8C191", "g": "#F9C191", "h": "#F9C292", "i": "#E4E3E3"}

def batman(d):              # icons8-batman-64.png
    _draw_grid(d, _BATMAN_GRID, _BATMAN_TONES)


_CATWOMAN_GRID = [
    "................................",
    "................................",
    ".......dd..............dd.......",
    ".......dd..............dc.......",
    ".......dddd..cgddgd..cddd.......",
    ".......cfgd..dgffgd..dgfc.......",
    ".......cfdcddcddddcddcdfc.......",
    ".......cfdeffddddddffedfc.......",
    ".......cfccddddddddddccfc.......",
    ".......cffffddddddddefffc.......",
    ".......cfhhfcddddddcfhhfc.......",
    ".......cfhhffeddddeffhhfc.......",
    ".......cfhkhhfcddcfhhkhfc.......",
    ".......cfhkihffeeffhikhfc.......",
    ".......cfhhaahhffhhaahhfc.......",
    ".......cfhhaahjffjiaahhfc.......",
    ".......cfhkhhjlmmljhhkhfc.......",
    ".......cfhllllloolllllhfc.......",
    ".......cgmonnooqqoonnomgc.......",
    ".......cgmqqqmmmmmmqqqmgc.......",
    ".........mqqmbbbbbbmqqp.........",
    ".........pqqmbbbbbbmqqp.........",
    "...........qqmmmmmmqq...........",
    "...........mmqqqqqqmm...........",
    "...........ggmqqqqmgg...........",
    "...........cgmmmmmmgc...........",
    "...........cggggggggc...........",
    "...........dfccccccfd...........",
    "...........cffffffffc...........",
    "...........cfddddddfc...........",
    "................................",
    "................................",
]
_CATWOMAN_TONES = {"a": "#094679", "b": "#C21257", "c": "#6F6C66", "d": "#706D67", "e": "#716D67", "f": "#716D68", "g": "#716E67", "h": "#EB75A8", "i": "#EB75A9", "j": "#EC75A8", "k": "#ED75A9", "l": "#ED76A9", "m": "#F7C091", "n": "#F8C092", "o": "#F9C092", "p": "#F8C192", "q": "#F9C292"}

def catwoman(d):            # icons8-catwoman-64.png
    _draw_grid(d, _CATWOMAN_GRID, _CATWOMAN_TONES)


_CHEBURASHKA_GRID = [
    "................................",
    "................................",
    "................................",
    "...........bbbbbbbbbb...........",
    "...........cccccccccc...........",
    "...bbbbbbbcffffffffffcbbbbbbb...",
    "...bcbbbcccfhhhhhhhhfcccbbbcb...",
    ".bbddddbcfffhhhhhhhhfffcbddddbb.",
    ".bcddddbcfhhhffhhffhhhfcbddddcb.",
    ".bbddddbcfhhfaaffaafhhfcbddddbb.",
    ".bbddddbcfhhfaaffaafhhfcbddddbb.",
    ".bcddddbcfhhhffhhffhhhfcbddddcb.",
    ".bbddddbcfffhhhffhhhfffcbddddbb.",
    "...bcbbbcccfhhgeeghhfcccbbbcb...",
    "...bbbbbbbcffffeeffffcbbbbbbb...",
    "...........ccccbbcccc...........",
    "...........bbccccccbb...........",
    ".........bbbcffffffcbbb.........",
    ".........bcbcfhhhhfcbcb.........",
    ".......bbbcbcfhgghfcbcbbb.......",
    ".......bbbbbcfhgghfcbbbbb.......",
    "...........bcfhhhhfcb...........",
    "...........bcffffffcb...........",
    "...........bccccccccb...........",
    "...........bbbbbbbbbb...........",
    "...........bbcb..bcbb...........",
    "...........bbbb..bbbb...........",
    ".........bbbbcb..bcbbbb.........",
    ".........bbbbbb..bbbbbb.........",
    "................................",
    "................................",
    "................................",
]
_CHEBURASHKA_TONES = {"a": "#064678", "b": "#8C1539", "c": "#8C163A", "d": "#B4252C", "e": "#E41E2F", "f": "#F8C191", "g": "#F9C191", "h": "#F9C292"}

def cheburashka(d):         # icons8-cheburashka-64.png
    _draw_grid(d, _CHEBURASHKA_GRID, _CHEBURASHKA_TONES)


_COOKIE_MONSTER_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "...........ddgd..ddgd...........",
    "...........llll..llll...........",
    ".......fldlmmmmlkmmmmldle.......",
    ".......elllmppmllmnpmllle.......",
    ".......dlmmmpppmmccmpmmld.......",
    ".......glmpopmmpmccmppmld.......",
    ".......glmppmccmpmmpopmlgheie...",
    ".......dlmmpmccmmpppommldllle...",
    ".....dkejllmpmmllmppmlllkkjle...",
    ".....elejdlmmmmllmmmmldeddele...",
    "...fkfekklllllljjlllllebbbbdjli.",
    "...eleigdddddddiiddddddbabbgkli.",
    "...eljdbbbbdebbdgbbeebbabggle...",
    "...eljdbbabddbbddbbddbaabglle...",
    "...eleigdbabbaabbaabbbaabgkle...",
    "...eleildbbaaaaaaaaaaabbbgkle...",
    ".....eleiedbaaaaaaaaaabdgiele...",
    ".....eleildbbbbaaaaaabbglefle...",
    ".....eleiiigggdbaaaabdgdeli.....",
    ".....elfeiikkldbbbbbbgleflg.....",
    ".......ileiiiiiggggggdeli.......",
    ".......elfeeeeejkkkkjeflg.......",
    ".........illlllllllllli.........",
    ".........ekeeeeeeeeeeke.........",
    "................................",
    "................................",
    "................................",
    "................................",
]
_COOKIE_MONSTER_TONES = {"a": "#085295", "b": "#095395", "c": "#716E68", "d": "#579AD4", "e": "#589AD3", "f": "#589AD4", "g": "#579BD3", "h": "#599AD3", "i": "#589BD4", "j": "#599BD4", "k": "#599CD4", "l": "#5A9CD5", "m": "#E4E4E4", "n": "#E5E4E4", "o": "#E5E5E5", "p": "#E6E5E5"}

def cookie_monster(d):      # icons8-cookie-monster-64.png
    _draw_grid(d, _COOKIE_MONSTER_GRID, _COOKIE_MONSTER_TONES)


_FUTURAMA_BENDER_GRID = [
    "................................",
    ".............ceec...............",
    ".............eeec...............",
    ".............hiig...............",
    ".............giig...............",
    ".........cecceeeeccec...........",
    ".........ceeecccceeec...........",
    ".......ceccccccccccccec.........",
    ".......ceccccccccccccec.........",
    ".......ceccccccccccccec.........",
    ".......cecceeeeeeeeeeee.........",
    ".......ceceghggggggggggii.......",
    ".......ceeegiiiiiiiiiihig.......",
    ".......ceggmmmmmmmmmmmkbbgi.....",
    ".......cegimjjjlllljjljabii.....",
    ".......cegimjbbjmljbbjjabgi.....",
    ".......cegimjbbjmljbbjjabgi.....",
    ".......cegimjjjlllljjljabii.....",
    ".......ceggmmmmmmmmmmmkbbgi.....",
    ".......ceeegiiiiiiiihihig.......",
    ".......ceceghggggggggggii.......",
    ".......cecceeeeeeeeeeee.........",
    ".......cedddddddddddcdd.........",
    ".......cekkffkkffkkffkk.........",
    ".......ceklffllffllffml.........",
    ".......ceklffllffllffml.........",
    ".......cdkkffllffllffml.........",
    ".......ceddffjlffllffml.........",
    ".......cecdffkkffkkffkk.........",
    ".........eeeeeeeeeeeeed.........",
    ".........ceccccccccccec.........",
    "................................",
]
_FUTURAMA_BENDER_TONES = {"a": "#716E67", "b": "#716E68", "c": "#B6B5B5", "d": "#B7B6B5", "e": "#B7B6B6", "f": "#F9C292", "g": "#E4E3E3", "h": "#E5E4E4", "i": "#E6E5E5", "j": "#FEEB8D", "k": "#FEEB8E", "l": "#FFEC8E", "m": "#FFEC8F"}

def futurama_bender(d):     # icons8-futurama-bender-64.png
    _draw_grid(d, _FUTURAMA_BENDER_GRID, _FUTURAMA_BENDER_TONES)


_GREY_GRID = [
    "................................",
    "................................",
    "................................",
    ".........bbbbbbbbbbbbbb.........",
    ".........bbbbbbbbbbbbbb.........",
    ".......bbccccccccccccccbb.......",
    ".......bbccccccccccccccbb.......",
    ".....bbccccccccccccccccccbb.....",
    ".....bbccccccccccccccccccbb.....",
    ".....bbccaaaaccccccaaaaccbb.....",
    ".....bbccaaaaccccccaaaaccbb.....",
    ".....bbccaaaaaaccaaaaaaccbb.....",
    ".....bbccaaaaaaccaaaaaaccbb.....",
    ".....bbccaaaaaaccaaaaaaccbb.....",
    ".....bbccaaaaaaccaaaaaaccbb.....",
    ".....bbccccaaaaccaaaaccccbb.....",
    ".....bbccccaaaaccaaaaccccbb.....",
    ".....bbccccccaaccaaccccccbb.....",
    ".....bbccccccaaccaaccccccbb.....",
    ".......bbccccccccccccccbb.......",
    ".......bbccccccccccccccbb.......",
    ".........bbccccccccccbb.........",
    ".........bbccccccccccbb.........",
    "...........bbccccccbb...........",
    "...........bbccccccbb...........",
    ".............bbbbbb.............",
    ".............bbbbbb.............",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
]
_GREY_TONES = {"a": "#064678", "b": "#009540", "c": "#A8C82B"}

def grey(d):                # icons8-grey-64.png
    _draw_grid(d, _GREY_GRID, _GREY_TONES)


_GRINCH_GRID = [
    "................................",
    "...............cedeedec.........",
    "...............ceeeeeec.........",
    ".............eeedddeeeeec.......",
    ".............cedeedeeceec.......",
    ".............cedded....deec.....",
    ".............dedded....ceec.....",
    "...........ceccccccec......cc...",
    "...........dedeeeedee......ee...",
    ".......ossonnnnnnnnnnosso..nnsq.",
    ".......nsssssssssssssssso..ssss.",
    ".......osooqqqqqqqqqqooso..ssso.",
    ".......osnrrrssssssrrrnso..ssss.",
    ".......nsssssssssssssssso.......",
    ".......osnnnnnnnnnnnnnnso.......",
    ".........ggggmmmmmmgggg.........",
    ".........gggghhhhhhgggg.........",
    ".....jmhmnnnnggiiggnnnnmhmh.....",
    ".....jmlmnsnngfiifgnnsnmlmh.....",
    "...jmlmhmpnbbihllhibbnpmhmlmh...",
    "...jmiihmnnbaimihmiabnnmhihmh...",
    "...lkgghmmmiilhgghliimmmiggkm...",
    "...lkgghhhhlllhgghlllhhhhggkm...",
    "...jmhhggimlmmmhhmmmlmigghhmh...",
    "...jmmhgghhhhhhllhhhhhhgghmmh...",
    ".....jmkhgfggfgiigfggfgikmh.....",
    ".....jmmhgffffgihgffffghmmh.....",
    ".........hkikhhgghhkikh.........",
    ".........mmmlmhgghmlmml.........",
    ".............jmkkmk.............",
    ".............lmllmj.............",
    "................................",
]
_GRINCH_TONES = {"a": "#074778", "b": "#084779", "c": "#E31E2E", "d": "#E31E2F", "e": "#E41E2F", "f": "#01953F", "g": "#019640", "h": "#90C04A", "i": "#90C04B", "j": "#91C04A", "k": "#90C14B", "l": "#91C14B", "m": "#92C14C", "n": "#E4E4E3", "o": "#E5E4E4", "p": "#E4E5E3", "q": "#E6E4E4", "r": "#E5E5E4", "s": "#E6E5E5"}

def grinch(d):              # icons8-grinch-64.png
    _draw_grid(d, _GRINCH_GRID, _GRINCH_TONES)


_JOKER_DC_GRID = [
    "................................",
    "...........cdccccccdd...........",
    "...........cfdffffdfd...........",
    ".........cdcdccccccdcdd.........",
    ".........dfeeddddddeefd.........",
    ".......cdcdccddddddccdcdd.......",
    ".......dfceffeddddeffeefd.......",
    ".....cdcecfoofceecfoofcecdd.....",
    ".....cfceffooffffffooffecfd.....",
    ".....cfcfooooooffoooooofcfd.....",
    ".....cfcfotsstoffotsstofcfd.....",
    ".......cfotsttsoosttstofc.......",
    ".......cfotossttttssotofc.......",
    ".......cfottttttttttttofc.......",
    ".......ffoooooottooooooff.......",
    ".......jjffffffooffffffjj.......",
    ".......nlfccecfoofceccfln.......",
    ".......njhgaagiooigaaghkl.......",
    ".......mkiibbiiooiibbiikm.......",
    ".......knooppoonnooppoonk.......",
    ".......knpptttqnnttttppnj.......",
    ".........bbpttonnottpbb.........",
    ".........bbppronnorppbb.........",
    ".........ppbbptsstpbbpp.........",
    ".........tpbbppppppbbpt.........",
    "...........ppbbbbbbpp...........",
    "...........tpbbbbbbpt...........",
    "...........qtppppppto...........",
    "...........qttttttttq...........",
    ".............rttttp.............",
    ".............rtttto.............",
    "................................",
]
_JOKER_DC_TONES = {"a": "#E32030", "b": "#E42031", "c": "#00943F", "d": "#00953F", "e": "#019540", "f": "#029641", "g": "#716C66", "h": "#706D67", "i": "#716E68", "j": "#B4B4B3", "k": "#B5B4B4", "l": "#B4B5B4", "m": "#B6B5B5", "n": "#B7B6B6", "o": "#E4E4E3", "p": "#E6E3E3", "q": "#E5E4E4", "r": "#E6E4E4", "s": "#E5E5E4", "t": "#E6E5E5"}

def joker_dc(d):            # icons8-joker-dc-64.png
    _draw_grid(d, _JOKER_DC_GRID, _JOKER_DC_TONES)


_KYLE_BROFLOVSKI_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    ".......kmhjjjjjjjjjjjjhmj.......",
    ".......immmmmmmmmmmmmmmmj.......",
    ".....kmlmmmmmmmmmmmmmmmmlmj.....",
    ".....imiiiiiiiiiiiiiiiiiimj.....",
    ".....mieeeeeeeeeeeeeeeeeeim.....",
    ".....iieaaaaaaaaaaaaaaaaeii.....",
    ".....eeccccccccccccccccccee.....",
    ".....eeccccddddccddddccccee.....",
    "...kmiieaaabbbbaabbbbaaaeiimj...",
    "...immieeeeeeeeeeeeeeeeeeimmj...",
    "...hmimnnnnttttnnttttnnnnmimj...",
    "...hmmmpsssuvttssttvussspmmmj...",
    ".lmkmppnsutvtggttggtvtusnppmhmj.",
    ".kmhmprnsuuvtggttggtvuusnrpmhmh.",
    ".kmlmprqqssuvttssttvussqqrpmlmh.",
    ".lmhmprqqnsuuuursuuuusnqqrnmhmj.",
    ".kj..nsnqqqssssqqssssrqqnsn..lj.",
    ".lj..nsnqqqqnnnqqnnnqqqqnsn..hj.",
    ".....nsnqqqqqssssssqqqqqnso.....",
    ".....nsponnqqnnnnnnqqnnopso.....",
    ".......nssssnggggggnsssso.......",
    ".......nsqosngfggfgnsoqso.......",
    "...........osnoooonso...........",
    "...........nsqssssqso...........",
    "................................",
    "................................",
    "................................",
    "................................",
]
_KYLE_BROFLOVSKI_TONES = {"a": "#00943F", "b": "#01943E", "c": "#01953F", "d": "#019540", "e": "#02953F", "f": "#716E67", "g": "#716E68", "h": "#A7C72B", "i": "#A6C82B", "j": "#A8C72B", "k": "#A7C82B", "l": "#A8C82B", "m": "#A9C82C", "n": "#F8C191", "o": "#F8C192", "p": "#F8C291", "q": "#F9C292", "r": "#F9C293", "s": "#F9C393", "t": "#E5E4E4", "u": "#E6E4E4", "v": "#E6E5E5"}

def kyle_broflovski(d):     # icons8-kyle-broflovski-64.png
    _draw_grid(d, _KYLE_BROFLOVSKI_GRID, _KYLE_BROFLOVSKI_TONES)


_NEO_GRID = [
    "................................",
    ".............aeaaaaaaea.........",
    ".............affffffffa.........",
    ".......aeaaaaaaaaaaaaaaea.......",
    ".......afffffbaaaabbaaafa.......",
    ".......afaaaaaaaaaaaaaafa.......",
    ".......afadffffbdffffdafa.......",
    ".....aeabafhhhhffhhhhfabaea.....",
    ".....afafffhllhffhllhfffafa.....",
    ".....aeafhhillihhillihhfaea.....",
    ".....afffhllllllllllllhfffa.....",
    ".....afhhillllllllllllihhfa.....",
    ".....afhllllllllllllllllhfa.....",
    ".....afhllllllllllllllllhfa.....",
    ".....afhhhhhhhhhhhhhhhhhhfa.....",
    ".....acffffffffffffffffffca.....",
    ".....ffffaaaaaaffaaaaaaffff.....",
    ".....hihhfaaaafhhfaaaafhhih.....",
    ".....lllhffffffhhffffffhlll.....",
    ".....hlhihhhhhhlihhhhhhihli.....",
    ".....hlillllllllllllllllili.....",
    ".......hlhllllllllllllhli.......",
    ".......hlhlllkkkkkklllhli.......",
    ".......hlhllllllllllllhli.......",
    ".......hlhllljjjjjjlllhli.......",
    ".......hlhkljggggggjlkhli.......",
    ".......hlhhljggggggjlhhli.......",
    ".........hlhljjjjjjlhli.........",
    ".........hlhillllllihli.........",
    "...........hlllllllli...........",
    "...........llhhhhhhli...........",
    "................................",
]
_NEO_TONES = {"a": "#706D67", "b": "#716D67", "c": "#706E68", "d": "#716E67", "e": "#716E68", "f": "#726E68", "g": "#F19007", "h": "#F8C191", "i": "#F8C192", "j": "#F9C191", "k": "#F9C291", "l": "#F9C292"}

def neo(d):                 # icons8-neo-64.png
    _draw_grid(d, _NEO_GRID, _NEO_TONES)


_NINJA_TURTLE_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "...........prqqqqqqrn....cd.....",
    "...........prrrrrrrrp....dc.....",
    ".........qrqqqqqqqqqqrq..cc.....",
    ".........ooooprppppoooo..cc.....",
    ".........hhfhoqqqqohfhh..dgec...",
    ".........iiiiooooooiiii..feec...",
    ".......cistttifhhfitttsic.......",
    ".......cisvushchhchsuvsic.......",
    ".......citubbkjjjjkbbutic.......",
    ".......citsbakmmmmkabstic.......",
    ".....qoheihkknnnnnnkkhiehoq.....",
    ".....rohhhhjmnrrrrnmjhhhhoq.....",
    "...prqpoooonnqrqqrqnnoooopqrn...",
    "...prqrqqqqrrrqqqqrrrqqqqrqrn...",
    "...prqrppppqrrrrrrrrrrrpprqrn...",
    "...prqprrrrrrnnnnnnnnnnrrpqrn...",
    ".....prqrrqrnmlmmmmmmlmnrrn.....",
    ".....prqpqqrnmlmmmmmmlmnrrn.....",
    ".......prrrrrnnnnnnnnqqrp.......",
    ".......prqpprrrrrrrrrprrn.......",
    "...........prqqqqqqrn...........",
    "...........prqpqqpqrn...........",
    ".............prrrrn.............",
    ".............prqqrn.............",
    "................................",
    "................................",
    "................................",
    "................................",
]
_NINJA_TURTLE_TONES = {"a": "#064778", "b": "#084779", "c": "#E31E2E", "d": "#E31E2F", "e": "#E41E2F", "f": "#E31F2F", "g": "#E41F30", "h": "#E32030", "i": "#E42031", "j": "#01943F", "k": "#019440", "l": "#01953F", "m": "#019640", "n": "#90C04A", "o": "#92BF4A", "p": "#91C04A", "q": "#90C14B", "r": "#91C14B", "s": "#E5E3E3", "t": "#E6E3E3", "u": "#E4E4E4", "v": "#E6E5E5"}

def ninja_turtle(d):        # icons8-ninja-turtle-64.png
    _draw_grid(d, _NINJA_TURTLE_GRID, _NINJA_TURTLE_TONES)


_R2_D2_GRID = [
    "................................",
    "................................",
    ".............aaaaab.............",
    ".............dddddd.............",
    "...........hieeeeeeie...........",
    "...........giiieeiiie...........",
    ".........iiiiieddeiiiih.........",
    ".........egeeieddeieege.........",
    ".........ddcdeeddeedcdd.........",
    ".........ddddffddffdddd.........",
    ".....kmkjjjjjkkjjkkjjjjjkmk.....",
    ".....mmmmmmmmjjjjjjmmmmmmmk.....",
    ".....mmkkllmjddddddjmllkkmm.....",
    ".....mmkkmlmjddddddjmlmkkmm.....",
    ".....mmmmmmmljjjjjjlmmmmmmm.....",
    ".....jmkkkmmmmmjjmmmmmkkkmj.....",
    ".....ii..kmklmjddjmlkmk..ii.....",
    ".....ee..kmklmjddjmlkmk..ee.....",
    ".....he..kmklmjddjmlkmk..hh.....",
    ".....he..kmklmjddjmlkmk..hh.....",
    ".....ee..kmkmmmjjmmmkmk..ee.....",
    ".....ii..kmkmmljjmmmkmk..ii.....",
    ".....jj..jmmmmjddjmmmmk..jj.....",
    ".....mm..kmjjkjddjkjjmk..mm.....",
    ".....mm....iiiiffiiii....km.....",
    ".....jj....eieeiieeie....jj.....",
    ".....iiie..............eiii.....",
    ".....eiie..............eiie.....",
    ".....eiie..............eiih.....",
    ".....eiih..............eiih.....",
    "................................",
    "................................",
]
_R2_D2_TONES = {"a": "#085195", "b": "#085294", "c": "#095395", "d": "#0A5396", "e": "#B5B4B4", "f": "#B5B4B5", "g": "#B5B5B5", "h": "#B6B5B5", "i": "#B7B6B6", "j": "#E4E4E4", "k": "#E5E4E4", "l": "#E5E4E5", "m": "#E6E5E5"}

def r2_d2(d):               # icons8-r2-d2-64.png
    _draw_grid(d, _R2_D2_GRID, _R2_D2_TONES)


_SCROOGE_MCDUCK_GRID = [
    "................................",
    ".............fiffie.............",
    ".............fiiiif.............",
    ".........fgffffffffffgf.........",
    ".........fiiiffffffiiif.........",
    ".........fiffffffffffif.........",
    ".........fiffffffffffie.........",
    ".........fiffffffffffie.........",
    ".........fiffffffffffie.........",
    ".........figgggggggggie.........",
    ".........fieeeeeeeeeeif.........",
    ".....fgffgeddddddddddegffgf.....",
    ".....fiiigeddddddddddegiiif.....",
    "...fiffffffeeeeeeeeeeffffffie...",
    "...fifffffgiiiiggiiiigfffffif...",
    ".....fiffeirrrriirrrrieffif.....",
    ".....fgffiisvvriirvvsiiffgf.....",
    ".......eirszACzqqACAzsrie.......",
    ".......eiqvACzzvvzzCAvqie.......",
    ".........qvBzccqqcczBvq.........",
    ".........qvBzcbqqaczBvq.........",
    ".....qs..qvBzccqqcczBvq..qv.....",
    ".....qs..qvBzccqqcczBvs..qs.....",
    "...qvqqssqvCzcbqqbczCvqssqqvs...",
    "...qvssvvrvzzccqqcczzvrvvssvs...",
    ".....qvqqtqmljjggjjlmqtqqvq.....",
    ".....qvuuurmjlmhhmljmruuuvs.....",
    ".....quxxxxmkkmxxmkkmxxxxut.....",
    ".....quxwyxmmmmxxmmmmxywxut.....",
    ".........opooooppoooopp.........",
    ".........nppppppppppppn.........",
    "................................",
]
_SCROOGE_MCDUCK_TONES = {"a": "#074678", "b": "#084779", "c": "#08487A", "d": "#E31F30", "e": "#716C66", "f": "#706D67", "g": "#706D68", "h": "#716E66", "i": "#716E67", "j": "#589AD3", "k": "#589BD4", "l": "#599BD4", "m": "#599CD2", "n": "#F08E06", "o": "#F08F06", "p": "#F18F06", "q": "#B5B5B5", "r": "#B6B5B4", "s": "#B6B5B5", "t": "#B6B5B6", "u": "#B7B6B4", "v": "#B7B6B6", "w": "#FBC101", "x": "#FBC103", "y": "#FCC201", "z": "#E3E4E4", "A": "#E4E4E4", "B": "#E5E4E4", "C": "#E6E5E5"}

def scrooge_mcduck(d):      # icons8-scrooge-mcduck-64.png
    _draw_grid(d, _SCROOGE_MCDUCK_GRID, _SCROOGE_MCDUCK_TONES)


_SHREK_GRID = [
    "................................",
    "................................",
    "............jokjjkoj............",
    "............jqqqqqql............",
    "..jj......nonlkkkklnoj......ko..",
    "..jm......jqkloooolkql......jo..",
    "..jqoj..monoooooooooonom..joqm..",
    "..jqqm..jqjjjjoooojjjjqj..jqqm..",
    "....jqnjccccccloolccccccjnqm....",
    "....joqlcbccbcloolcbccbclqqj....",
    "......qnhddddhjqqjhddddhko......",
    "......qnhihhghjqqjhghhehno......",
    "......qnfhttaakookaatthdno......",
    "......qnhhttaakqqkaatthhno......",
    "......kqjkqqkkrrrrkkqqkjqj......",
    "......jqoqjmqqrssrqqmjqoqj......",
    "....nolonnpqrrssssrrqponoooj....",
    "....jqkooonorrrrrrrronoookqj....",
    "....kqkoooqqqqqqqqqqqqoookqk....",
    "....kqkoookjknkkkknkkjoookqk....",
    "....jqknqjhhjqoqqoqkhhjqnkqj....",
    "....jqnkqjhhjjjjjjjjhhjqknqj....",
    "......jqknjjhhhhhhhhjjnkqj......",
    "......jqnnqjhhhhhhhhjqnnqj......",
    "........jqknjjjjjjjjnkqj........",
    "........jqnoqqqqqqqqonqj........",
    "..........jqkorrrrokqj..........",
    "..........jqnorrrronqj..........",
    "............jqqqqqqj............",
    "............jqjjjjqk............",
    "................................",
    "................................",
]
_SHREK_TONES = {"a": "#074779", "b": "#8C1639", "c": "#8C173A", "d": "#01943F", "e": "#00953F", "f": "#01953F", "g": "#019540", "h": "#029540", "i": "#019640", "j": "#90C04A", "k": "#90C04B", "l": "#91C04B", "m": "#90C14A", "n": "#90C14B", "o": "#91C14B", "p": "#91C14C", "q": "#92C14C", "r": "#BDD84E", "s": "#BDD94E", "t": "#E4E4E3"}

def shrek(d):               # icons8-shrek-64.png
    _draw_grid(d, _SHREK_GRID, _SHREK_TONES)


_SONIC_THE_HEDGEHOG_GRID = [
    "................................",
    "................................",
    "................................",
    ".....cheeeeeeddddefhf...........",
    ".....chffjjfjjjjjjfjf...........",
    ".......djfgciooooicgehf.........",
    ".......fhfgdiorooidgejf.........",
    ".........cjdiooiiiffffdfcbabb...",
    ".........fjdiooidggggffjfbbba...",
    ".........fjegiihfccccffeeccba...",
    ".........cjefddfgjjjjhgfffcbb...",
    ".......fhffffgicjttttjcgffefc...",
    ".......fjeffffgcjtvvtjjgfggjd...",
    ".....fheffffffgcjtvvvttjcccjd...",
    ".....fjeffffffijjtvttvtjcjjjd...",
    "...fheffffffgcjttvtnnttjjttjc...",
    "...djfeeefffgcjtvvtnnttjjttjj...",
    ".cjffjjjjfffgcjtvvtnnttjcnntt...",
    ".cjeeeffdfffgcjtvvtnnttjinnuv...",
    ".........cjegdiosuvttvvttttvv...",
    ".........fjeiiiootuvvuuvvtttt...",
    ".......cffgdioonnossssssonnnn...",
    ".......cjegdioonnooooppromklk...",
    ".......eheffijjoonnnnorsq.......",
    ".......cjeefddiopnnmnorsq.......",
    ".....fhffjhjf....osoosq.........",
    ".....djfdffhf....rsrrsq.........",
    "...chffjf.......................",
    "...cheehf.......................",
    "................................",
    "................................",
    "................................",
]
_SONIC_THE_HEDGEHOG_TONES = {"a": "#064577", "b": "#064678", "c": "#26649E", "d": "#26649F", "e": "#26659E", "f": "#26659F", "g": "#27659F", "h": "#27669F", "i": "#28669F", "j": "#2866A0", "k": "#6F6C66", "l": "#706D67", "m": "#716E67", "n": "#716E68", "o": "#F6C192", "p": "#F8C191", "q": "#F8C192", "r": "#F9C292", "s": "#F9C293", "t": "#E4E3E4", "u": "#E5E4E4", "v": "#E6E5E5"}

def sonic_the_hedgehog(d):  # icons8-sonic-the-hedgehog-64.png
    _draw_grid(d, _SONIC_THE_HEDGEHOG_GRID, _SONIC_THE_HEDGEHOG_TONES)


_SUPER_MARIO_GRID = [
    "................................",
    "................................",
    "................................",
    "............egggggge............",
    "............gjkkkkie............",
    "........eggfgkCCCCkefgge........",
    "........ghijgkCHHCkgjihe........",
    "......ehgeeegkCHHCkgeeeghg......",
    "......eheikkkkCCCCkkkkiehe......",
    "......eiekqqqqttttqqqqkeie......",
    "......ejkkqrrrqqqqrrrqkkje......",
    "....egekpqrrrrrrrrrrrrqpkege....",
    "....kkkkqrppppttttpppprqkkkk....",
    "....pqqqrponmnwwwwnmnoprqqqp....",
    "....trpptsoooouzzuoooostpprs....",
    "......dduBCDDCBzzBCDDCBudd......",
    "......cduBFHDEBzzBEDHFBudc......",
    "....zudduBGDabuzzubaDGBuddwz....",
    "....zwdduBCEbbwBBwbbECBuddwz....",
    "....vzuuxBBBIIJJJJIIBBBxuuzv....",
    "....uzzzzAuwJKKKKKKJwuAzzzzy....",
    "......vzzwnoIKJJJJKIonwzzu......",
    "......vzzwnoIIIKKIIIonwzzy......",
    "........zBnlooIKKIoolnBx........",
    "........zwnnnoIIIIonnnwz........",
    "..........uBwwoooowwBu..........",
    "..........zzzunnnnuzzz..........",
    "............vAwwwwAu............",
    "............vzzzzzzy............",
    "................................",
    "................................",
    "................................",
]
_SUPER_MARIO_TONES = {"a": "#074779", "b": "#084777", "c": "#8B1539", "d": "#8D1739", "e": "#E31E2F", "f": "#E31E30", "g": "#E41E2F", "h": "#E41E30", "i": "#E41F30", "j": "#E42031", "k": "#E42132", "l": "#706D67", "m": "#716D68", "n": "#726E66", "o": "#726F67", "p": "#EC75A8", "q": "#ED75A8", "r": "#ED75A9", "s": "#EC76A8", "t": "#ED76A8", "u": "#FAC001", "v": "#FBC101", "w": "#FBC103", "x": "#FCC101", "y": "#FBC201", "z": "#FCC201", "A": "#FCC202", "B": "#FCC203", "C": "#E6E3E3", "D": "#E4E4E4", "E": "#E5E4E3", "F": "#E6E4E3", "G": "#E6E5E3", "H": "#E6E5E5", "I": "#FEEB8E", "J": "#FFEC8D", "K": "#FFEC8E"}

def super_mario(d):         # icons8-super-mario-64.png
    _draw_grid(d, _SUPER_MARIO_GRID, _SUPER_MARIO_TONES)


_WALL_E_GRID = [
    "................................",
    "................................",
    "...........wvhf..wvif...........",
    "...........vvhf..vvif...........",
    ".........uthhfgnngifhtu.........",
    ".........uthgignngfghtu.........",
    ".........sttttunnuttttq.........",
    ".........stuutunnutuutq.........",
    "...............jl...............",
    "...............mm...............",
    "...............kk...............",
    "...............nn...............",
    ".....koknutqqqquuqqqqtrnkoj.....",
    ".....nnknututtttttttutunknn.....",
    "...ssuu..tttttttttttttt..uuss...",
    "...sttt..uuruuuuuuuuruu..ttts...",
    ".........nnnnnnnnnnnnnn.........",
    ".........kokkkkkkkkkkok.........",
    ".........ppmpooooppolpm.........",
    ".........jojonnnnoojjoj.........",
    "...becbbdnoonddddnkaakndbbceb...",
    "...ceeeeenoonddddnkaakndceeec...",
    "...cecccdjokknnnnookkondbccec...",
    "...becccdnnnnooookonnnndbcceb...",
    "...beccberuuu......ruurebcceb...",
    "...beccbeqttt......tttqebcceb...",
    "...beccec..............cecceb...",
    "...cecceb..............beccec...",
    "...ceeeec..............ceeeec...",
    "...ceccec..............ceccec...",
    "................................",
    "................................",
]
_WALL_E_TONES = {"a": "#E41F2F", "b": "#6F6C66", "c": "#706D67", "d": "#716D66", "e": "#716E67", "f": "#589BD4", "g": "#599BD2", "h": "#5A9BD4", "i": "#599CD4", "j": "#F08E06", "k": "#F18E06", "l": "#F08F06", "m": "#F08F07", "n": "#F08F08", "o": "#F18F06", "p": "#F18F07", "q": "#B5B4B4", "r": "#B6B4B4", "s": "#B6B5B5", "t": "#B6B5B6", "u": "#B7B5B4", "v": "#E5E4E4", "w": "#E6E5E5"}

def wall_e(d):              # icons8-wall-e-64.png
    _draw_grid(d, _WALL_E_GRID, _WALL_E_TONES)


_WOODY_WOODPECKER_GRID = [
    "................................",
    "............dd..................",
    "............ee..................",
    "..........de..eeeeed............",
    "..........ee..eeeeed............",
    "....ed..dedddddddddded..........",
    "....ed..eedeeeeeeeeded..........",
    "......deddeeddeeeded............",
    "......dedeeeeeeeeded............",
    "........dedeeeeeeeeeed..........",
    "........deddffeeggdded..........",
    "........deefccfeed....ed........",
    "........deffccfgii....dd........",
    "........edccfdeirr..............",
    "........edcciiiirr..............",
    "......dedgdirrrriiru........pn..",
    "......eedgeiruuriirs........nn..",
    "....deedegeiruurifbasu..oppp....",
    "....dedeegeirusrifbbrt..pppn....",
    "....dedeegeirsbbrrolqqonpn......",
    "....deedeihirrbbstqppnpppn......",
    "......eidhllqqoqrrqnqppn........",
    "......dehhlpllmqrrqloppn........",
    "........lmplhhhhqqpn............",
    "........ppplhhehllpn............",
    "..........npmmhfkkop............",
    "..........npplhijkop............",
    "..............mokkqp............",
    "..............pqkkop............",
    "................oqpn............",
    "................pppn............",
    "................................",
]
_WOODY_WOODPECKER_TONES = {"a": "#074779", "b": "#084778", "c": "#8D1539", "d": "#E31E2F", "e": "#E41E2F", "f": "#E21F30", "g": "#E31F30", "h": "#E4202F", "i": "#E42031", "j": "#706D67", "k": "#716E66", "l": "#FBC001", "m": "#FCC001", "n": "#FBC101", "o": "#FBC102", "p": "#FCC201", "q": "#FCC203", "r": "#E6E3E3", "s": "#E4E4E4", "t": "#E6E5E3", "u": "#E6E5E5"}

def woody_woodpecker(d):    # icons8-woody-woodpecker-64.png
    _draw_grid(d, _WOODY_WOODPECKER_GRID, _WOODY_WOODPECKER_TONES)

_BLUEPRINT_GRID = [
    "................................",
    "................................",
    "................................",
    "................................",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaeeeeeeeeeeeeeeeeeeeeaa....",
    "....aaebbbbbbbbbbbbddddddeaa....",
    "....aaebbeebbbbbbbbbbbbbbeaa....",
    "....aaebbebebbbbbbbbeebbbeaa....",
    "....aaebbebebbbbbbbebbebbeaa....",
    "....aaebbebbebbbbbbebbebbeaa....",
    "....aaebbebbebbbbbbbeebbbeaa....",
    "....aaebbebbbebbbbbbbbbbbeaa....",
    "....aaebbebbbebbbbbbeebbbeaa....",
    "....aaebbebbbbebbbbebbebbeaa....",
    "....aaebbebbbbebbbbebbebbeaa....",
    "....aaebbebbbbbebbbebbebbeaa....",
    "....aaebbebbbbbebbbebbebbeaa....",
    "....aaebbebbbbbbebbebebbbeaa....",
    "....aaebbeeeeeeeebbeebbbbeaa....",
    "....aaebbbbbbbbbbbbbbbbbbeaa....",
    "....aaebbbbbbbbbdddddddddeaa....",
    "....aaebbbbbbbbbdddddddddeaa....",
    "....aaebbbbbbbbbdddddddddeaa....",
    "....aaeeeeeeeeeeeeeeeeeeeeaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "....aaaaaaaaaaaaaaaaaaaaaaaa....",
    "................................",
    "................................",
    "................................",
    "................................",
]
# Blueprint sheet for Customer DXF Quoting: dark-blue border, blueprint-blue
# paper, and the L-shaped flat pattern drawn as white LINEWORK (outline, two
# drilled holes, dashed bend line at the leg/foot junction) like a real
# blueprint, with a yellow dimension line + end ticks underneath. Fixed
# palette — this icon is NOT theme-recolored (pack set, not the pixel-32 set).
_BLUEPRINT_TONES = {"a": "#085295", "b": "#26659F", "d": "#FCC201", "e": "#E6E5E5"}

def blueprint(d):           # customer dxf quoting
    _draw_grid(d, _BLUEPRINT_GRID, _BLUEPRINT_TONES)


# Output set -> {key: (grid, tones)}. Each grid is painted in its own colors.
_MR_BEANS_GRID = [
    "...........kggkkkkkkkkkkk.......",
    "...........kggkkkkkkkkkkk.......",
    "...........kggkkkkkkkkkkk.......",
    "...........kggkkkkkkkkkkk.......",
    "...........kggkkkkkkkkkkk.......",
    "...........kggkkkkkkkkkkk.......",
    "...........kggkkkkkkkkkkk.......",
    "...........rrrrrrrrrrrrrr.......",
    "...........rrrrrrrrrrrrrr.......",
    "........kkkkkkkkkkkkkkkkkkkk....",
    "........kkkkkkkkkkkkkkkkkkkk....",
    ".........oddbbbbbbbbbbbbbo......",
    ".........obbbbbbbbbbbbbbbbo.....",
    ".....k.k.kobdbbbbbbbbbbbbbo.....",
    "....kwkwkwkbbdddbbbbbdddbbo.....",
    "....kwkwkwkohhhbbbbbbbbbdbbo....",
    "....kwwwwwkhwkkhbbbbbwkkbbbo....",
    "....kwwwwwkhkkkhbbbbbkkkbbbo....",
    "....kwwwwwkhkkkhbbbbbkkkbbbbo...",
    ".....kwwwkbhkkkhbbbbbkkkbbbbo...",
    "......kkkobbhhhbbbbbbbbbbbbbbo..",
    "........obbbbbbbbbbbbbbbbbbbbo..",
    "........obbbbbbbbbbbbbbbbbbbbo..",
    "........obbbbbobbbbbbbobbbbbbo..",
    "........obbbbbbooooooobbbbbbdo..",
    "........obbbbbbbbbbbbbbbbbbdo...",
    "........obbbbbbbbbbbbbbbbbddo...",
    ".........obbbbbbbbbbbbbbbddo....",
    "..........obbbbbbbbbbbbbddo.....",
    "...........obbbbbbbbbbdddo......",
    "............oodddddddddoo.......",
    "..............ooooooooo.........",
]
_MR_BEANS_TONES = {"b": "#D2622A", "d": "#A8431C", "g": "#3C3C48", "h": "#EE9257", "k": "#16161C", "o": "#5C2410", "r": "#C03434", "w": "#FFF4E6"}
SETS = {
    "TechDeck pack pixel": {
        "mr_beans": (_MR_BEANS_GRID, _MR_BEANS_TONES),
        "blueprint": (_BLUEPRINT_GRID, _BLUEPRINT_TONES),
    },
    "Icons socialmedia pixel": {
        "adobe_illustrator": (_ADOBE_ILLUSTRATOR_GRID, _ADOBE_ILLUSTRATOR_TONES),
        "adobe_photoshop": (_ADOBE_PHOTOSHOP_GRID, _ADOBE_PHOTOSHOP_TONES),
        "android_os": (_ANDROID_OS_GRID, _ANDROID_OS_TONES),
        "apple_inc": (_APPLE_INC_GRID, _APPLE_INC_TONES),
        "chrome": (_CHROME_GRID, _CHROME_TONES),
        "discord_new": (_DISCORD_NEW_GRID, _DISCORD_NEW_TONES),
        "facebook_messenger": (_FACEBOOK_MESSENGER_GRID, _FACEBOOK_MESSENGER_TONES),
        "github": (_GITHUB_GRID, _GITHUB_TONES),
        "gmail_logo": (_GMAIL_LOGO_GRID, _GMAIL_LOGO_TONES),
        "google": (_GOOGLE_GRID, _GOOGLE_TONES),
        "google_maps": (_GOOGLE_MAPS_GRID, _GOOGLE_MAPS_TONES),
        "instagram_old": (_INSTAGRAM_OLD_GRID, _INSTAGRAM_OLD_TONES),
        "mcdonald_s": (_MCDONALD_S_GRID, _MCDONALD_S_TONES),
        "microsoft_excel_2019": (_MICROSOFT_EXCEL_2019_GRID, _MICROSOFT_EXCEL_2019_TONES),
        "microsoft_word_2019": (_MICROSOFT_WORD_2019_GRID, _MICROSOFT_WORD_2019_TONES),
        "notification": (_NOTIFICATION_GRID, _NOTIFICATION_TONES),
        "spotify": (_SPOTIFY_GRID, _SPOTIFY_TONES),
        "steam_circled": (_STEAM_CIRCLED_GRID, _STEAM_CIRCLED_TONES),
        "telegram_app": (_TELEGRAM_APP_GRID, _TELEGRAM_APP_TONES),
        "terraria": (_TERRARIA_GRID, _TERRARIA_TONES),
        "visual_game_boy": (_VISUAL_GAME_BOY_GRID, _VISUAL_GAME_BOY_TONES),
        "wechat": (_WECHAT_GRID, _WECHAT_TONES),
        "windows_10": (_WINDOWS_10_GRID, _WINDOWS_10_TONES),
        "youtube": (_YOUTUBE_GRID, _YOUTUBE_TONES),
    },
    "Icons8 characters pixel": {
        "anonymous_mask": (_ANONYMOUS_MASK_GRID, _ANONYMOUS_MASK_TONES),
        "batman": (_BATMAN_GRID, _BATMAN_TONES),
        "catwoman": (_CATWOMAN_GRID, _CATWOMAN_TONES),
        "cheburashka": (_CHEBURASHKA_GRID, _CHEBURASHKA_TONES),
        "cookie_monster": (_COOKIE_MONSTER_GRID, _COOKIE_MONSTER_TONES),
        "futurama_bender": (_FUTURAMA_BENDER_GRID, _FUTURAMA_BENDER_TONES),
        "grey": (_GREY_GRID, _GREY_TONES),
        "grinch": (_GRINCH_GRID, _GRINCH_TONES),
        "joker_dc": (_JOKER_DC_GRID, _JOKER_DC_TONES),
        "kyle_broflovski": (_KYLE_BROFLOVSKI_GRID, _KYLE_BROFLOVSKI_TONES),
        "neo": (_NEO_GRID, _NEO_TONES),
        "ninja_turtle": (_NINJA_TURTLE_GRID, _NINJA_TURTLE_TONES),
        "r2_d2": (_R2_D2_GRID, _R2_D2_TONES),
        "scrooge_mcduck": (_SCROOGE_MCDUCK_GRID, _SCROOGE_MCDUCK_TONES),
        "shrek": (_SHREK_GRID, _SHREK_TONES),
        "sonic_the_hedgehog": (_SONIC_THE_HEDGEHOG_GRID, _SONIC_THE_HEDGEHOG_TONES),
        "super_mario": (_SUPER_MARIO_GRID, _SUPER_MARIO_TONES),
        "wall_e": (_WALL_E_GRID, _WALL_E_TONES),
        "woody_woodpecker": (_WOODY_WOODPECKER_GRID, _WOODY_WOODPECKER_TONES),
    },
}


def main():
    want = sys.argv[1:]
    sets = {k: v for k, v in SETS.items() if not want or k in want}
    total = 0
    for out_folder, icons in sets.items():
        for key, (grid, tones) in icons.items():
            im, d = _new()
            _draw_grid(d, grid, tones)
            _save(im, out_folder, key)
            total += 1
    print(f"Generated {total} icons across {len(sets)} set(s): {', '.join(sets)}")


if __name__ == "__main__":
    main()
