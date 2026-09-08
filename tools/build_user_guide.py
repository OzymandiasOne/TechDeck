"""Build the TechDeck User Guide PDF from docs/user_guide/*.md.

Usage:
    python tools/build_user_guide.py [-o OUTPUT.pdf] [--lax]

Chapters are docs/user_guide/NN_*.md, ordered by filename. The leading number
groups them into parts (0x shell, 1x 902, 2x-3x 911, 4x 922, 5x General, 6x QA,
7x Games). Files starting with "_" are never part of the book.

Output defaults to assets/docs/TechDeck User Guide.pdf (the copy that ships
inside the app); a review copy is also placed in C:\\Dev\\Samples.

Voice gates: a chapter containing "plugin" or "sdk." fails the build (the guide
is for colleagues; those words are dev vocabulary). --lax downgrades to warnings.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import io
import re
import sys
from pathlib import Path

import fitz
import markdown

REPO = Path(__file__).resolve().parents[1]
GUIDE_DIR = REPO / "docs" / "user_guide"
# The shipped location: bundled via TechDeck.spec's assets datas, opened by
# /guide and Settings > Help & Feedback. A review copy also lands in Samples.
DEFAULT_OUT = REPO / "assets" / "docs" / "TechDeck User Guide.pdf"
REVIEW_COPY = REPO.parent / "Samples" / "TechDeck User Guide.pdf"

PAGE = fitz.paper_rect("letter")
MARGIN = 54.0
BODY_RECT = fitz.Rect(PAGE.x0 + MARGIN, PAGE.y0 + MARGIN, PAGE.x1 - MARGIN, PAGE.y1 - MARGIN - 18)

NAVY = (0.07, 0.22, 0.37)
GREY = (0.45, 0.45, 0.45)

# (prefixes, part title) — order defines book order
PART_MAP = [
    (("0",), "Getting Around TechDeck"),
    (("1",), "902 Apps"),
    (("2", "3"), "911 Apps"),
    (("4",), "922 Apps"),
    (("5",), "General Apps"),
    (("6",), "QA Apps"),
    (("7",), "Games"),
]

CSS = """
body { font-family: sans-serif; font-size: 10pt; line-height: 1.35; color: #1a1a1a; }
h1 { font-size: 21pt; color: #12385e; margin-bottom: 4pt; }
h2 { font-size: 13.5pt; color: #12385e; margin-top: 12pt; }
h3 { font-size: 11pt; color: #333333; margin-top: 8pt; }
p { margin: 4pt 0; }
li { margin: 2pt 0; }
table { margin: 6pt 0; }
th { background-color: #e8eef4; font-size: 9.5pt; }
th, td { border: 0.7pt solid #99aabb; padding: 3pt 6pt; font-size: 9.5pt; text-align: left; }
code { font-family: monospace; font-size: 9pt; background-color: #f0f0f0; }
pre { font-family: monospace; font-size: 9pt; background-color: #f0f0f0; margin: 5pt 0; }
blockquote { color: #444444; margin: 5pt 12pt; }
img { margin: 6pt 0 2pt 0; }
p.caption { color: #667788; font-size: 8.5pt; margin: 0 0 8pt 0; }
"""

IMG_MD_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
IMG_TAG_RE = re.compile(r'<img alt="([^"]*)" src="([^"]+)"\s*/?>')
MAX_IMG_PT = 470  # body width is ~504pt


def size_images(html: str) -> str:
    """Give every <img> an explicit width (half its pixel size, capped to the
    page) and turn its alt text into a small caption paragraph below it."""

    def _sub(m: re.Match) -> str:
        alt, src = m.group(1), m.group(2)
        path = GUIDE_DIR / src
        pix = fitz.Pixmap(str(path))
        w = min(round(pix.width * 0.5), MAX_IMG_PT)
        cap = f'<p class="caption">{alt}</p>' if alt else ""
        return f'<img src="{src}" width="{w}"/>{cap}'

    return IMG_TAG_RE.sub(_sub, html)

BANNED = [
    (re.compile(r"\bplugins?\b", re.IGNORECASE), 'the word "plugin" (say "app")'),
    (re.compile(r"\bsdk\.", re.IGNORECASE), '"sdk." (dev vocabulary)'),
    (re.compile(r"[–—]"), "an em/en dash (rewrite with plain punctuation)"),
]


def app_version() -> str:
    text = (REPO / "techdeck" / "core" / "constants.py").read_text(encoding="utf-8")
    m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else "?"


def discover_chapters() -> list[tuple[str, Path]]:
    """Returns [(part_title, chapter_path)] in book order."""
    files = sorted(p for p in GUIDE_DIR.glob("[0-9][0-9]_*.md"))
    if not files:
        sys.exit(f"No chapters found in {GUIDE_DIR}")
    out = []
    for prefixes, title in PART_MAP:
        for f in files:
            if f.name[0] in prefixes:
                out.append((title, f))
    leftovers = [f.name for f in files if not any(f.name[0] in p for p, _ in PART_MAP)]
    if leftovers:
        sys.exit(f"Chapters with no part mapping: {leftovers}")
    return out


def lint_chapter(path: Path, text: str) -> list[str]:
    problems = []
    if not text.lstrip().startswith("# "):
        problems.append(f"{path.name}: first line must be the '# ' chapter title")
    body = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)  # TODO comments are exempt
    for rx, why in BANNED:
        hits = rx.findall(body)
        if hits:
            problems.append(f"{path.name}: contains {why} x{len(hits)}")
    for src in IMG_MD_RE.findall(body):
        if not (GUIDE_DIR / src).is_file():
            problems.append(f"{path.name}: missing image {src}")
    # A split numbered list restarts at 1 in the PDF (the renderer ignores
    # <ol start>). Cause: content under a list item indented <4 spaces.
    html = markdown.markdown(body, extensions=["tables", "sane_lists"])
    splits = html.count("<ol start=")
    if splits:
        problems.append(f"{path.name}: a numbered list is split x{splits} "
                        "(indent content under list items by 4 spaces)")
    for todo in re.findall(r"<!--\s*TODO[^>]*-->", text):
        print(f"  [todo] {path.name}: {todo.strip()[:100]}")
    return problems


def md_to_html(text: str) -> str:
    return size_images(markdown.markdown(text, extensions=["tables", "sane_lists"]))


def render_flow(writer: fitz.DocumentWriter, html: str, page_no: list[int],
                headings: list, rect: fitz.Rect = BODY_RECT) -> None:
    """Render one HTML flow (a chapter or a part page); records h1/h2 positions."""
    story = fitz.Story(html=html, user_css=CSS, archive=fitz.Archive(str(GUIDE_DIR)))
    more = 1
    while more:
        dev = writer.begin_page(PAGE)
        more, _ = story.place(rect)
        current_page = page_no[0]

        def _record(el):
            if el.open_close == 1 and el.heading in (1, 2):
                headings.append((el.heading, el.text, current_page))

        story.element_positions(_record)
        story.draw(dev)
        writer.end_page()
        page_no[0] += 1


TABLE_RE = re.compile(r"<table>.*?</table>", re.DOTALL)
ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.DOTALL)
CELL_RE = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.DOTALL)
SEG_GAP = 8.0          # vertical gap between segments
MIN_TAIL = 60.0        # don't start a segment in a sliver shorter than this
HEAD_KEEP = 110.0      # a heading keeps this much room under it, or moves on
H_OPEN_RE = re.compile(r"<h[23]>")


def _li_depth_at(html: str, pos: int) -> int:
    """How many <li> elements are open at `pos`."""
    return html.count("<li>", 0, pos) - html.count("</li>", 0, pos)


def _flow_height(seg_html: str) -> float:
    probe = fitz.Story(html=seg_html, user_css=CSS, archive=fitz.Archive(str(GUIDE_DIR)))
    _, filled = probe.place(fitz.Rect(0, 0, BODY_RECT.width, 100000))
    return filled[3]


def number_headings(html: str, chap_no: int) -> str:
    """Official-manual numbering, applied at build time so the sources never
    go stale: the chapter number on the h1, N.M on each h2, N.M.P on h3."""
    html = re.sub(r"<h1>(.*?)</h1>",
                  lambda m: f"<h1>{chap_no}&#160;&#160;{m.group(1)}</h1>", html, count=1)
    state = {"sec": 0, "sub": 0}

    def hr(m: re.Match) -> str:
        tag, txt = m.group(1), m.group(2)
        if tag == "h2":
            state["sec"] += 1
            state["sub"] = 0
            num = f"{chap_no}.{state['sec']}"
        else:
            state["sub"] += 1
            num = f"{chap_no}.{state['sec']}.{state['sub']}"
        return f"<{tag}>{num}&#160;&#160;{txt}</{tag}>"

    return re.sub(r"<(h[23])>(.*?)</\1>", hr, html, flags=re.DOTALL)


def flatten_unsafe_tables(html: str) -> str:
    """Rewrite tables the renderer cannot handle as bold-label paragraphs,
    which flow across pages like any text. Two kinds are unsafe: a <table>
    inside a list item (splitting the list around it restarts numbering, and
    straddling a page drops rows), and any table taller than one page (it
    drops rows wherever it is placed)."""

    def rewrite(m: re.Match) -> str:
        rows = ROW_RE.findall(m.group(0))
        out = []
        for i, row in enumerate(rows):
            cells = [c.strip() for c in CELL_RE.findall(row)]
            if not cells:
                continue
            if i == 0 and len(rows) > 1 and "<th" in row:
                out.append("<p><i>" + ". ".join(c for c in cells if c) + ".</i></p>")
                continue
            first, rest = cells[0], ". ".join(c for c in cells[1:] if c)
            out.append(f"<p><b>{first}.</b> {rest}</p>")
        return "".join(out)

    result = []
    last = 0
    for m in TABLE_RE.finditer(html):
        result.append(html[last:m.start()])
        unsafe = (_li_depth_at(html, m.start()) > 0
                  or _flow_height(m.group(0)) > BODY_RECT.height)
        result.append(rewrite(m) if unsafe else m.group(0))
        last = m.end()
    result.append(html[last:])
    return "".join(result)


def split_segments(html: str) -> list[str]:
    """Cut the chapter at top-level tables (atomic, measured, moved whole)
    and at every h2/h3 (so a heading can be kept with its content)."""
    cuts = [(m.start(), m.end(), True) for m in TABLE_RE.finditer(html)
            if _li_depth_at(html, m.start()) == 0]
    cuts += [(m.start(), m.start(), False) for m in H_OPEN_RE.finditer(html)]
    segs, pos = [], 0
    for start, end, is_table in sorted(cuts):
        if start < pos:  # a heading inside an already-consumed table span
            continue
        if html[pos:start].strip():
            segs.append(html[pos:start])
        if is_table:
            segs.append(html[start:end])
            pos = end
        else:
            pos = start  # the heading opens the next segment
    if html[pos:].strip():
        segs.append(html[pos:])
    return segs


def render_chapter(writer: fitz.DocumentWriter, html: str, page_no: list[int],
                   headings: list) -> None:
    """Table-safe chapter renderer.

    fitz.Story SILENTLY DROPS table rows (and everything after them in the
    flow) when a <table> straddles a page boundary. So a chapter is rendered
    as segments split at tables, sharing a page cursor; each table is measured
    first and moved to a fresh page when it will not fit in the space left.
    A table taller than a full page still cannot render whole — the integrity
    gate catches that; keep tables short.
    """
    archive = fitz.Archive(str(GUIDE_DIR))
    segments = split_segments(flatten_unsafe_tables(html))

    dev = writer.begin_page(PAGE)
    y = BODY_RECT.y0

    def new_page():
        nonlocal dev, y
        writer.end_page()
        page_no[0] += 1
        dev = writer.begin_page(PAGE)
        y = BODY_RECT.y0

    for i, seg in enumerate(segments):
        story = fitz.Story(html=seg, user_css=CSS, archive=archive)
        lead = seg.lstrip()
        remaining = BODY_RECT.y1 - y
        if lead.startswith("<table"):
            need = _flow_height(seg)
            if need > remaining and need <= BODY_RECT.height:
                new_page()
        elif lead.startswith(("<h2", "<h3")):
            h = _flow_height(seg)
            need = min(h, HEAD_KEEP)
            # A bare heading whose content is the NEXT segment (a table):
            # keep them together, or the heading strands at the page bottom.
            if h < 70 and i + 1 < len(segments) and segments[i + 1].lstrip().startswith("<table"):
                need = h + SEG_GAP + min(_flow_height(segments[i + 1]), 200.0)
            if need > remaining:
                new_page()
        elif remaining < MIN_TAIL:
            new_page()
        while True:
            more, filled = story.place(fitz.Rect(BODY_RECT.x0, y, BODY_RECT.x1, BODY_RECT.y1))
            current_page = page_no[0]

            def _record(el):
                if el.open_close == 1 and el.heading in (1, 2):
                    headings.append((el.heading, el.text, current_page))

            story.element_positions(_record)
            story.draw(dev)
            if more:
                new_page()
            else:
                y = filled[3] + SEG_GAP
                break
    writer.end_page()
    page_no[0] += 1


def normalize_probe(text: str) -> str:
    # NFKC folds the renderer's ligatures (fi, fl, ff) back to plain letters,
    # or the integrity check would flag every word the font ligates.
    import unicodedata
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKC", text).lower())


def chapter_probes(md_text: str) -> list[str]:
    """Strings that MUST appear in the rendered chapter: every plain table
    cell, and the chapter's closing words."""
    body = re.sub(r"<!--.*?-->", "", md_text, flags=re.DOTALL)
    body = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", body)
    probes = []
    for line in body.splitlines():
        if line.lstrip().startswith("|") and not set(line.strip()) <= {"|", "-", " ", ":"}:
            for cell in line.strip().strip("|").split("|"):
                p = normalize_probe(re.sub(r"[`*_]", "", cell))
                if len(p) >= 6:
                    probes.append(p)
    plain = normalize_probe(re.sub(r"[#`*_|>\[\]()!-]", "", body))
    if len(plain) > 60:
        probes.append(plain[-60:])
    return probes


def check_integrity(final: fitz.Document, entries, chapters, offset: int,
                    body_pages: int) -> list[str]:
    """Verify no chapter content was silently dropped by the renderer."""
    chap_pages = [(title, pg) for lvl, title, pg in entries if lvl == 2]
    bounds = []
    for i, (title, pg) in enumerate(chap_pages):
        end = chap_pages[i + 1][1] - 1 if i + 1 < len(chap_pages) else body_pages
        bounds.append((title, pg, max(pg, end)))
    problems = []
    clip = fitz.Rect(PAGE.x0, PAGE.y0, PAGE.x1, BODY_RECT.y1 + 2)  # body only:
    # footer text would otherwise splice into probes that span a page break
    for (title, first, last), (_, chap) in zip(bounds, chapters):
        text = "".join(final[offset + p - 1].get_text(clip=clip)
                       for p in range(first, last + 1))
        rendered = normalize_probe(text)
        for probe in chapter_probes(chap.read_text(encoding="utf-8")):
            if probe not in rendered:
                problems.append(f"{chap.name}: rendered PDF is missing text: ...{probe[-40:]}")
    return problems


def find_orphan_headings(final: fitz.Document, offset: int, body_pages: int) -> list[str]:
    """Flag any page whose LAST content is a heading (h1/h2 render at >=13pt):
    an official manual never strands a header at the bottom of a page."""
    problems = []
    clip = fitz.Rect(PAGE.x0, PAGE.y0, PAGE.x1, BODY_RECT.y1 + 2)
    for p in range(body_pages):
        page = final[offset + p]
        d = page.get_text("dict", clip=clip)
        text_blocks = []
        img_bottom = 0.0
        for b in d["blocks"]:
            if b.get("type") == 1:
                img_bottom = max(img_bottom, b["bbox"][3])
            elif any(s["text"].strip() for l in b.get("lines", []) for s in l.get("spans", [])):
                text_blocks.append(b)
        if not text_blocks:
            continue
        page_text = "".join(s["text"] for b in text_blocks for l in b["lines"] for s in l["spans"])
        if page_text.strip().startswith("Part ") and len(text_blocks) <= 2:
            continue  # part divider pages are a lone big title on purpose
        last = text_blocks[-1]
        if img_bottom > last["bbox"][3]:
            continue  # an image sits below the last text, so no heading strands
        size = max(s["size"] for l in last["lines"] for s in l["spans"])
        if size >= 13:
            text = "".join(s["text"] for l in last["lines"] for s in l["spans"]).strip()
            problems.append(f"page {offset + p + 1}: heading stranded at the page bottom: {text[:60]!r}")
    return problems


def stamp_footers(doc: fitz.Document, version: str) -> None:
    y = PAGE.y1 - MARGIN + 4
    for i, page in enumerate(doc):
        page.draw_line((MARGIN, y), (PAGE.x1 - MARGIN, y), color=GREY, width=0.5)
        page.insert_text((MARGIN, y + 12), f"TechDeck User Guide  \u00b7  v{version}",
                         fontsize=8, fontname="helv", color=GREY)
        tail = f"{i + 1}"
        w = fitz.get_text_length(tail, fontname="helv", fontsize=8)
        page.insert_text((PAGE.x1 - MARGIN - w, y + 12), tail,
                         fontsize=8, fontname="helv", color=GREY)


def make_cover(version: str) -> fitz.Document:
    doc = fitz.open()
    page = doc.new_page(width=PAGE.width, height=PAGE.height)
    page.draw_rect(fitz.Rect(0, 0, PAGE.width, 8), color=None, fill=NAVY)
    icon = REPO / "assets" / "TechDeck.ico"
    try:
        from PIL import Image
        img = Image.open(icon)
        img.size  # touch to load
        buf = io.BytesIO()
        img.convert("RGBA").save(buf, format="PNG")
        side = 110
        cx = PAGE.width / 2
        page.insert_image(fitz.Rect(cx - side / 2, 190, cx + side / 2, 190 + side),
                          stream=buf.getvalue())
    except Exception as exc:  # cover works without the icon
        print(f"  [warn] cover icon skipped: {exc}")
    def centered(text: str, y: float, size: float, font: str, color) -> None:
        w = fitz.get_text_length(text, fontname=font, fontsize=size)
        page.insert_text(((PAGE.width - w) / 2, y), text, fontsize=size, fontname=font, color=color)

    centered("TechDeck", 375, 44, "hebo", NAVY)
    centered("User Guide", 412, 20, "helv", (0.2, 0.2, 0.2))
    page.draw_line((PAGE.width / 2 - 90, 440), (PAGE.width / 2 + 90, 440), color=NAVY, width=1)
    when = _dt.date.today().strftime("%B %Y")
    centered(f"Version {version}  \u00b7  {when}", 470, 11, "helv", GREY)
    centered("Every app, explained.", 486, 11, "helv", GREY)
    return doc


def make_toc_pages(entries):
    """Draws the printed Contents. Returns (doc, [(toc_page_idx, rect, body_page_1based)])."""
    doc = fitz.open()
    links = []
    page = doc.new_page(width=PAGE.width, height=PAGE.height)
    page.insert_text((MARGIN, MARGIN + 20), "Contents", fontsize=22, fontname="hebo", color=NAVY)
    y = MARGIN + 56
    for level, title, body_page in entries:
        if level == 3:
            continue  # printed TOC keeps to parts + chapters; sections live in bookmarks
        if y > PAGE.height - MARGIN - 20:
            page = doc.new_page(width=PAGE.width, height=PAGE.height)
            y = MARGIN + 20
        if level == 1:
            y += 10
            font, size, color, indent = "hebo", 11.5, NAVY, 0
        else:
            font, size, color, indent = "helv", 10, (0.1, 0.1, 0.1), 16
        page.insert_text((MARGIN + indent, y), title, fontsize=size, fontname=font, color=color)
        tail = str(body_page)
        w = fitz.get_text_length(tail, fontname="helv", fontsize=size)
        page.insert_text((PAGE.x1 - MARGIN - w, y), tail, fontsize=size, fontname="helv", color=color)
        links.append((doc.page_count - 1,
                      fitz.Rect(MARGIN, y - size, PAGE.x1 - MARGIN, y + 3), body_page))
        y += size + 7
    return doc, links


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output", default=str(DEFAULT_OUT))
    ap.add_argument("--lax", action="store_true", help="voice-gate violations warn instead of fail")
    args = ap.parse_args()

    version = app_version()
    chapters = discover_chapters()
    print(f"Building guide v{version}: {len(chapters)} chapters")

    problems = []
    for _, chap in chapters:
        problems += lint_chapter(chap, chap.read_text(encoding="utf-8"))
    if problems:
        for p in problems:
            print(f"  [voice] {p}")
        if not args.lax:
            sys.exit("Voice gate failed (use --lax to build anyway).")

    scratch = GUIDE_DIR / ".build"
    scratch.mkdir(exist_ok=True)
    body_path, entries = _build(chapters, scratch)

    body = fitz.open(str(body_path))
    stamp_footers(body, version)

    cover = make_cover(version)
    toc_doc, toc_links = make_toc_pages(entries)
    offset = cover.page_count + toc_doc.page_count  # body page 1 lands at index `offset`

    final = fitz.open()
    final.insert_pdf(cover)
    final.insert_pdf(toc_doc)
    final.insert_pdf(body)

    for toc_pg, rect, body_page in toc_links:
        final[cover.page_count + toc_pg].insert_link(
            {"kind": fitz.LINK_GOTO, "from": rect, "page": offset + body_page - 1, "to": fitz.Point(0, 0)})

    outline = [[1, "Contents", cover.page_count + 1]]
    outline += [[lvl, title, offset + pg] for lvl, title, pg in entries]
    final.set_toc(outline)
    final.set_metadata({"title": f"TechDeck User Guide v{version}", "author": "TechDeck",
                        "subject": "User guide for TechDeck and all of its apps"})

    integrity = check_integrity(final, entries, chapters, offset, body.page_count)
    integrity += find_orphan_headings(final, offset, body.page_count)
    if integrity:
        for p in integrity:
            print(f"  [integrity] {p}")
        if not args.lax:
            sys.exit("Integrity gate failed: dropped content or a stranded heading.")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    final.save(str(out), garbage=3, deflate=True)
    print(f"Wrote {out} ({final.page_count} pages)")
    if out == DEFAULT_OUT and REVIEW_COPY.parent.is_dir():
        import shutil
        shutil.copy2(out, REVIEW_COPY)
        print(f"Review copy: {REVIEW_COPY}")


def _build(chapters, scratch):
    body_path = scratch / "_guide_body.pdf"
    writer = fitz.DocumentWriter(str(body_path))
    page_no = [0]
    entries: list = []
    seen_parts: set = set()
    for chap_no, (part_title, chap) in enumerate(chapters, start=1):
        if part_title not in seen_parts:
            seen_parts.add(part_title)
            n = len(seen_parts)
            entries.append((1, f"Part {n}: {part_title}", page_no[0] + 1))
            html = (
                f'<div style="margin-top: 260pt; text-align: center;">'
                f'<p style="font-size: 12pt; color: #888888;">Part {n}</p>'
                f'<h1 style="font-size: 26pt;">{part_title}</h1></div>'
            )
            render_flow(writer, html, page_no, [])
        text = chap.read_text(encoding="utf-8")
        title = text.lstrip().splitlines()[0].lstrip("# ").strip()
        entries.append((2, f"{chap_no}  {title}", page_no[0] + 1))
        headings: list = []
        html = number_headings(md_to_html(text), chap_no)
        render_chapter(writer, html, page_no, headings)
        # Story reports the numbered heading text with the &#160; as \xa0;
        # bookmarks want a plain space.
        entries.extend((3, t.replace("\xa0", " "), pg + 1)
                       for lvl, t, pg in headings if lvl == 2)
    writer.close()
    return body_path, entries


if __name__ == "__main__":
    main()
