"""Build the TechDeck User Guide PDF from docs/user_guide/*.md.

Usage:
    python tools/build_user_guide.py [-o OUTPUT.pdf] [--lax]

Chapters are docs/user_guide/NN_*.md, ordered by filename. The leading number
groups them into parts (0x shell, 1x 902, 2x-3x 911, 4x 922, 5x General, 6x QA,
7x Games). Files starting with "_" are never part of the book.

Output defaults to C:\\Dev\\Samples\\TechDeck User Guide.pdf so it can be reviewed.

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
DEFAULT_OUT = REPO.parent / "Samples" / "TechDeck User Guide.pdf"

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
"""

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
    for todo in re.findall(r"<!--\s*TODO[^>]*-->", text):
        print(f"  [todo] {path.name}: {todo.strip()[:100]}")
    return problems


def md_to_html(text: str) -> str:
    return markdown.markdown(text, extensions=["tables", "sane_lists"])


def render_flow(writer: fitz.DocumentWriter, html: str, page_no: list[int],
                headings: list, rect: fitz.Rect = BODY_RECT) -> None:
    """Render one HTML flow (a chapter or a part page); records h1/h2 positions."""
    story = fitz.Story(html=html, user_css=CSS)
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

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    final.save(str(out), garbage=3, deflate=True)
    print(f"Wrote {out} ({final.page_count} pages)")


def _build(chapters, scratch):
    body_path = scratch / "_guide_body.pdf"
    writer = fitz.DocumentWriter(str(body_path))
    page_no = [0]
    entries: list = []
    seen_parts: set = set()
    for part_title, chap in chapters:
        if part_title not in seen_parts:
            seen_parts.add(part_title)
            entries.append((1, part_title, page_no[0] + 1))
            n = len(seen_parts)
            html = (
                f'<div style="margin-top: 260pt; text-align: center;">'
                f'<p style="font-size: 12pt; color: #888888;">Part {n}</p>'
                f'<h1 style="font-size: 26pt;">{part_title}</h1></div>'
            )
            render_flow(writer, html, page_no, [])
        text = chap.read_text(encoding="utf-8")
        title = text.lstrip().splitlines()[0].lstrip("# ").strip()
        entries.append((2, title, page_no[0] + 1))
        headings: list = []
        render_flow(writer, md_to_html(text), page_no, headings)
        entries.extend((3, t, pg + 1) for lvl, t, pg in headings if lvl == 2)
    writer.close()
    return body_path, entries


if __name__ == "__main__":
    main()
