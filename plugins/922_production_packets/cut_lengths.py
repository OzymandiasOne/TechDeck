"""Read a tube's cut length off its drawings.

Rule: a part that belongs to an assembly is read from the ASSEMBLY sheet only.
An individual part sheet is read only for a one-off tube with no assembly.

Three fixes over the previous pass, each from a real miss on the 2-tube set:
  1. SCALE expressions are not dimensions. "DETAIL A / SCALE 0.474013 : 1" was
     being read as a 0.47" tube.
  2. A dimension goes to its NEAREST part callout, and every callout gets one.
     The old rule refused any dimension that sat nearer another callout, so on a
     two-tube sheet one tube got the wrong number and the other got nothing.
  3. When one tube carries two dimensions (a short side and a long side), the
     LONG one is the cut. The old code took whichever was nearest.
"""
import os, re, math
import fitz

try:
    from techdeck.core import plugin_sdk as sdk
except ModuleNotFoundError:                       # standalone / CLI testing
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from techdeck.core import plugin_sdk as sdk


def _open_pdf(path):
    """fitz.open with the two Windows/OneDrive guardrails applied.

    Every PDF read in this module goes through here: a shop print under the
    Pilot Program tree can be a cloud-only placeholder (Hard Rule 6) and its
    path can be past the 260-character cap (Hard Rule 7).
    """
    sdk.ensure_local(path)
    return fitz.open(sdk.long_path(path))

GRIND_ALLOWANCE = 0.10           # per jointed END of a tube
MIN_LENGTH = 1.0                 # nothing shorter than an inch is a tube
_BRACKET_OPEN = re.compile(r'^\((\d+\.\d{2})$')
_BRACKETED = re.compile(r'^\((\d+\.\d{2})\)$')
_PLAIN = re.compile(r'^(\d+\.\d{2})$')
_ANYNUM = re.compile(r'^\(?(\d+\.\d{2})\)?$')
PARTISH = re.compile(r'^[A-Z]{1,2}\d{6,7}-[A-Z0-9]+-\d+[A-Z]?$')


def _piece_order(part):
    """Sort key for the piece suffix: -4A, -4B, -4C or -5, -6, -7."""
    tail = part.rsplit('-', 1)[-1]
    m = re.match(r'^(\d+)([A-Z]*)$', tail)
    return (int(m.group(1)), m.group(2)) if m else (9999, tail)


def grind_allowance(part, roster):
    """How much the tube is cut over its assembly dimension.

    Every jointed end is modelled 0.1" oversized for the grind, so a tube
    jointed at BOTH ends - a middle member of a 3+ tube assembly - is 0.2" over.
    The two tubes of a 2-tube assembly are both end members, so both are 0.1".
    """
    order = sorted(set(roster), key=_piece_order)
    if len(order) < 3:
        return GRIND_ALLOWANCE
    middle = order[1:-1]
    return GRIND_ALLOWANCE * 2 if part.upper() in middle else GRIND_ALLOWANCE


def ceil_tenth(v):
    return math.ceil(round(v * 10, 6)) / 10


def index_drawings(batch_dir):
    idx = {}
    for dirpath, _dn, filenames in os.walk(batch_dir):
        if 'CAD-AND-SHOP-PRINTS' not in dirpath:
            continue
        for fn in filenames:
            if fn.lower().endswith('.pdf'):
                idx.setdefault(fn[:-4].upper(), []).append(
                    os.path.join(dirpath, fn))
    return idx


def profile_of(desc):
    return {float(t) for t in re.findall(r'\d+(?:\.\d+)?', desc or '')}


def _words(page):
    W, H = page.rect.width, page.rect.height
    out = []
    for w in page.get_text('words'):
        if w[0] > W * 0.50 and w[1] > H * 0.68:
            continue                                   # title block
        if w[1] < H * 0.10 and w[0] > W * 0.55:
            continue                                   # revisions table
        out.append((w[4].strip(), (w[0] + w[2]) / 2, (w[1] + w[3]) / 2))
    return out


def _scale_tokens(words):
    """Indexes of the numbers that belong to a 'SCALE x : y' expression."""
    out = set()
    for i, (tok, x, y) in enumerate(words):
        if tok.upper() != 'SCALE':
            continue
        for j in range(i + 1, min(i + 5, len(words))):
            t, jx, jy = words[j]
            if abs(jy - y) > 6:                        # a different line
                break
            if t == ':' or _PLAIN.match(t):
                out.add(j)
            else:
                break
    return out


TIE_TOL = 0.5                    # two tubes closer than this cannot be ranked
SAW_NEAR = 60                    # how far a "SAW CUT" note sits from its value
BELOW_TOL_Y = 30                 # a parenthesised cut length sits just under
BELOW_TOL_X = 45                 # ...its dimension


def cut_candidates(page, profile):
    """Every dimension on a sheet as (value, x, y, add_grind).

    A dimension with a number in parentheses immediately BELOW it is a finished
    length over its saw-cut length - the parenthesised one is what gets cut, and
    it is used as printed (rounded up to the tenth), with no grind allowance on
    top. "( N SAW CUT )" is the same thing with the words spelled out.
    """
    saw, plain, ref = _dims(page, profile)
    out = [(v, x, y, False) for v, x, y in saw]
    claimed = set()
    # a plain dimension sitting directly above a "( N SAW CUT )" note is that
    # same tube's FINISHED length - the note is its cut. Leaving both in gave
    # H6454666-H1 three candidates for two tubes, and the shorter tube was
    # ranked onto 19.80 instead of 13.90.
    plain = [(v, x, y) for v, x, y in plain
             if not any(0 < sy - y <= BELOW_TOL_Y and abs(sx - x) <= BELOW_TOL_X
                        for _sv, sx, sy in saw)]
    for v, x, y in plain:
        under = [(rv, rx, ry) for rv, rx, ry in ref
                 if 0 < ry - y <= BELOW_TOL_Y and abs(rx - x) <= BELOW_TOL_X]
        if under:
            rv, rx, ry = min(under, key=lambda t: t[2] - y)
            out.append((rv, x, y, False))
            claimed.add((rv, rx, ry))
        else:
            out.append((v, x, y, True))
    for rv, rx, ry in ref:
        if (rv, rx, ry) not in claimed:
            out.append((rv, rx, ry, False))
    return out


def _dims(page, profile):
    """(saw, plain, reference) dimension values with positions."""
    words = _words(page)
    skip = _scale_tokens(words)
    saw, plain, ref = [], [], []
    for i, (tok, x, y) in enumerate(words):
        if tok.upper().lstrip('(') != 'SAW':
            continue
        # the longest number printed beside the words. Anchoring to the token
        # directly above instead cost 6 parts - the value sits above on some
        # sheets and to the left on others, and it is always the longer of the
        # finished/cut pair.
        near = []
        for j, (t, jx, jy) in enumerate(words):
            if j in skip:
                continue
            m = _ANYNUM.match(t)
            if m and math.hypot(jx - x, jy - y) <= SAW_NEAR:
                near.append((float(m.group(1)), j, jx, jy))
        if near:
            v, j, jx, jy = max(near)
            saw.append((v, jx, jy))
            skip.add(j)
    for i, (tok, x, y) in enumerate(words):
        if i in skip:
            continue
        m = _BRACKETED.match(tok)
        if m:
            v = float(m.group(1))
            if v not in profile and v >= MIN_LENGTH:
                ref.append((v, x, y))
            continue
        m = _PLAIN.match(tok)
        if m:
            v = float(m.group(1))
            if v not in profile and v >= MIN_LENGTH:
                plain.append((v, x, y))
    return saw, plain, ref


def _labels(page):
    out = []
    for tok, x, y in _words(page):
        t = tok.strip().rstrip(',').upper()
        if PARTISH.match(t):
            out.append((t, x, y))
    return out


VALUE_TOL = 0.3                  # a short side and a long side of one tube
POS_TOL = 150                    # ...drawn in the same part of the sheet


def collapse(dims):
    """A tube dimensioned twice - its short side and its long side - is one
    measurement. Keep the long one.

    H7923062-H27 carries 3.12 and 3.2 for one tube, 5.76 and 5.9 for the other;
    the cut lengths were 3.3 and 6.0, i.e. the LONG one of each pair + 0.10.
    """
    out = []
    for d in sorted(dims, key=lambda t: -t[0]):
        v, x, y = d[0], d[1], d[2]
        # two tubes of the SAME length are two dimensions, not one tube
        # dimensioned twice - R7921865-H13 carries 11.00, 11.00 and 21.90
        if any(0 < abs(v - o[0]) <= VALUE_TOL
               and math.hypot(x - o[1], y - o[2]) <= POS_TOL for o in out):
            continue
        out.append(d)
    return out


def assign(dims, labels):
    """{part: its dimension}, paired by READING ORDER down the sheet.

    Pairing each callout to its nearest dimension was a coin flip (12 of 28 on
    the 2-tube drawings) because a callout's leader points away from the tube it
    names. Taking both lists top-to-bottom instead gets 24 of 28. The leaders
    themselves are drawn as hundreds of 1pt fragments, so they cannot be
    followed from the text layer.
    """
    if not labels or not dims:
        return {}
    dims = collapse(dims)
    if len(dims) < len(labels):
        return {}
    ls = sorted(labels, key=lambda t: (t[2], t[1]))
    ds = sorted(dims, key=lambda t: (t[2], t[1]))[-len(ls):]
    return {t: d for (t, _lx, _ly), d in zip(ls, ds)}


_OWN_DIM_CACHE: dict = {}


def own_dimension(part, idx, profile):
    """The length dimensioned on the part's OWN sheet.

    Used ONLY to rank the tubes of an assembly by length - never as the cut
    length, which always comes off the assembly sheet. It is the one signal that
    settles which assembly dimension belongs to which tube: a callout's leader
    points away from the tube it names, so nearest-callout, reading order and
    lowest-total-distance all deal the numbers out wrong on 3-tube sheets.
    """
    up = part.upper()
    if up in _OWN_DIM_CACHE:
        return _OWN_DIM_CACHE[up]
    val = None
    for path in idx.get(up, []) + idx.get(up + '-STEP', []):
        doc = _open_pdf(path)
        try:
            _saw, plain, ref = _dims(doc[0], profile)
            cands = [v for v, _x, _y in plain] + [v for v, _x, _y in ref]
            if cands:
                val = max(cands)
        finally:
            doc.close()
        if val is not None:
            break
    _OWN_DIM_CACHE[up] = val
    return val


def rank_by_length(dims, siblings, idx, profile):
    """{part: its dimension}, shortest tube to shortest dimension.

    `siblings` is every tube on the assembly, taken from the batch PO - NOT from
    the callouts printed on the sheet. H7921466-H19 names only -4A and -4B on its
    assembly sheet although the batch carries a -4C, so a roster built from the
    callouts came up a tube short and the extra dimension was discarded.
    """
    owns = {t: own_dimension(t, idx, profile) for t in siblings}
    known = {t: v for t, v in owns.items() if v is not None}
    if not known:
        return {}, False
    merged = collapse(dims)
    # merging near-equal dimensions is for ONE tube dimensioned twice; never
    # merge away a dimension a real tube still needs
    if len(merged) < len(known) <= len(dims):
        merged = sorted(dims, key=lambda d: -d[0])[:len(known)]
    if len(merged) < len(known):
        return {}, False
    order = sorted(known, key=lambda t: known[t])
    ds = sorted(merged, key=lambda d: d[0])[-len(order):]
    paired = {t: d for t, d in zip(order, ds)}
    # two tubes within TIE_TOL of each other cannot be told apart by length, so
    # the pairing is a guess and the row gets flagged
    lens = sorted(known.values())
    uncertain = any(abs(a - b) < TIE_TOL for a, b in zip(lens, lens[1:]))
    return paired, uncertain


def _assembly_pages(doc):
    return [i for i in range(doc.page_count) if len(_labels(doc[i])) >= 2]


def find_assembly(part, idx):
    up = part.upper()
    for stem, paths in idx.items():
        if '-ASM' not in stem:
            continue
        for p in paths:
            doc = _open_pdf(p)
            try:
                if up not in ''.join(doc[i].get_text()
                                     for i in range(doc.page_count)).upper():
                    continue
                pages = _assembly_pages(doc)
                return p, (pages[0] if pages else 0)
            finally:
                doc.close()
    return None, None


def read(part, idx, desc, siblings=None):
    """-> (cut_length, how_we_know, assembly_path, uncertain)"""
    profile = profile_of(desc)
    up = part.upper()

    asm, page_i = find_assembly(part, idx)
    if asm:
        doc = _open_pdf(asm)
        try:
            page = doc[page_i]
            labels = _labels(page)
            roster = sorted({*(siblings or []), *(t for t, _x, _y in labels)})
            cands = cut_candidates(page, profile)
            paired, uncertain = rank_by_length(cands, roster, idx, profile)
            hit = paired.get(up)
            if hit is None:
                hit, uncertain = assign(cands, labels).get(up), True
            if hit is not None:
                v, _x, _y, add_grind = hit
                if add_grind:
                    return (ceil_tenth(v + grind_allowance(up, roster)),
                            'assembly + grind', asm, uncertain)
                return ceil_tenth(v), 'assembly cut length', asm, uncertain
            return None, 'assembly found, dimension not matched', asm, True
        finally:
            doc.close()

    for p in idx.get(up, []) + idx.get(up + '-STEP', []):
        doc = _open_pdf(p)
        try:
            saw, plain, ref = _dims(doc[0], profile)
            if saw:
                return (ceil_tenth(max(v for v, _x, _y in saw)),
                        'single tube SAW CUT', None, False)
            if ref:
                return (ceil_tenth(max(v for v, _x, _y in ref)),
                        'single tube parenthesis', None, False)
            base = max((v for v, _x, _y in plain), default=None)
            if base is not None:
                return ceil_tenth(base), 'single tube, straight cut', None, False
        finally:
            doc.close()
    return None, 'no drawing', None, True
