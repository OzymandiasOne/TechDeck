"""
Java Tutor - turning the tutor's markdown into HTML for the chat view.

QTextBrowser renders a subset of HTML, so this is deliberately small: the
blocks that actually show up in a coding lesson - fenced code, inline code,
headings, lists, tables, bold/italic - and nothing else.

Java code blocks get syntax colouring. The tokeniser makes ONE pass with a
single alternation so that a keyword inside a string or comment is not
coloured as a keyword; colouring keywords first and strings second is the
classic way to get `"// not a comment"` wrong.
"""

import html
import re

# --- palette ---------------------------------------------------------------
# Defaults are tuned for TechDeck's dark theme; the window passes real theme
# colours in where it has them.
DEFAULTS = {
    "text": "#e6e6e6",
    "muted": "#9aa0a6",
    "code_bg": "#1b1f24",
    "code_border": "#2d333b",
    "accent": "#7aa2f7",
    "kw": "#c678dd",        # keywords
    "str": "#98c379",       # strings and chars
    "com": "#7f848e",       # comments
    "num": "#d19a66",       # numbers
    "ann": "#e5c07b",       # annotations
    "typ": "#61afef",       # class-ish names
}

_JAVA_KEYWORDS = {
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char",
    "class", "const", "continue", "default", "do", "double", "else", "enum",
    "extends", "final", "finally", "float", "for", "goto", "if", "implements",
    "import", "instanceof", "int", "interface", "long", "native", "new",
    "package", "private", "protected", "public", "return", "short", "static",
    "strictfp", "super", "switch", "synchronized", "this", "throw", "throws",
    "transient", "try", "void", "volatile", "while", "var", "record",
    "sealed", "permits", "yield", "true", "false", "null",
}

# One alternation, ordered so the greediest context wins: comments and strings
# swallow anything that looks like code inside them.
_JAVA_TOKEN = re.compile(
    r"""
    (?P<com>  //[^\n]* | /\*.*?\*/ )
  | (?P<str>  "(?:\\.|[^"\\\n])*" | '(?:\\.|[^'\\\n])*' )
  | (?P<ann>  @[A-Za-z_]\w* )
  | (?P<num>  \b\d[\d_]*(?:\.\d+)?[fFdDlL]? \b )
  | (?P<word> \b[A-Za-z_]\w* \b )
    """,
    re.VERBOSE | re.DOTALL,
)


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def highlight_java(code: str, pal: dict) -> str:
    """Colour Java source. Returns HTML with the original spacing intact."""
    out = []
    pos = 0
    for m in _JAVA_TOKEN.finditer(code):
        out.append(_esc(code[pos:m.start()]))
        pos = m.end()
        kind = m.lastgroup
        raw = m.group()
        if kind == "word":
            if raw in _JAVA_KEYWORDS:
                colour = pal["kw"]
            elif raw[:1].isupper():
                colour = pal["typ"]
            else:
                out.append(_esc(raw))
                continue
        else:
            colour = pal[kind]
        out.append(f'<span style="color:{colour};">{_esc(raw)}</span>')
    out.append(_esc(code[pos:]))
    return "".join(out)


def _inline(text: str, pal: dict) -> str:
    """Inline markdown: `code`, **bold**, *italic*, [links]."""
    # Inline code first, and stash it, so bold/italic markers inside a code
    # span are left alone.
    stash: list[str] = []

    def keep_code(m):
        body = _esc(m.group(1))
        stash.append(
            f'<span style="background:{pal["code_bg"]};color:{pal["accent"]};'
            f'font-family:Consolas,monospace;">&nbsp;{body}&nbsp;</span>'
        )
        return f"\x00{len(stash) - 1}\x00"

    text = re.sub(r"`([^`]+)`", keep_code, text)
    text = _esc(text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)",
                  rf'<a href="\2" style="color:{pal["accent"]};">\1</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], text)
    return text


def _code_block(code: str, lang: str, index: int, pal: dict) -> str:
    """A fenced code block, with a Copy link the window handles."""
    lang = (lang or "").lower()
    body = highlight_java(code, pal) if lang in ("java", "") else _esc(code)
    label = lang or "code"
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0" '
        f'style="margin:8px 0;"><tr><td style="background:{pal["code_bg"]};'
        f'border:1px solid {pal["code_border"]};">'
        f'<table width="100%" cellspacing="0" cellpadding="6"><tr>'
        f'<td style="color:{pal["muted"]};font-size:11px;">{_esc(label)}</td>'
        f'<td align="right"><a href="copy:{index}" '
        f'style="color:{pal["muted"]};font-size:11px;'
        f'text-decoration:none;">Copy</a></td></tr></table>'
        f'<div style="padding:2px 10px 10px 10px;">'
        f'<pre style="margin:0;font-family:Consolas,monospace;'
        f'font-size:13px;color:{pal["text"]};">{body}</pre></div>'
        f"</td></tr></table>"
    )


def _table(rows: list[str], pal: dict) -> str:
    """A pipe table. The |---| separator row is dropped."""
    parsed = []
    for row in rows:
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells if c != ""):
            continue
        parsed.append(cells)
    if not parsed:
        return ""

    head, *body = parsed
    out = [
        f'<table cellspacing="0" cellpadding="6" '
        f'style="border:1px solid {pal["code_border"]};margin:8px 0;">'
    ]
    out.append("<tr>" + "".join(
        f'<td style="border-bottom:1px solid {pal["code_border"]};">'
        f"<b>{_inline(c, pal)}</b></td>" for c in head) + "</tr>")
    for row in body:
        out.append("<tr>" + "".join(
            f"<td>{_inline(c, pal)}</td>" for c in row) + "</tr>")
    out.append("</table>")
    return "".join(out)


def to_html(markdown: str, pal: dict | None = None) -> tuple[str, list[str]]:
    """Render markdown to HTML.

    Returns (html, code_blocks) - the second item is the raw text of each
    fenced block, in order, so the window's Copy links can find them.
    """
    pal = {**DEFAULTS, **(pal or {})}
    lines = markdown.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    codes: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # fenced code
        fence = re.match(r"^\s*```+\s*(\w+)?\s*$", line)
        if fence:
            lang = fence.group(1) or ""
            i += 1
            buf = []
            while i < len(lines) and not re.match(r"^\s*```+\s*$", lines[i]):
                buf.append(lines[i])
                i += 1
            i += 1  # closing fence (or end of text - an unclosed block still renders)
            code = "\n".join(buf)
            out.append(_code_block(code, lang, len(codes), pal))
            codes.append(code)
            continue

        # table
        if line.strip().startswith("|") and line.strip().endswith("|"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                buf.append(lines[i])
                i += 1
            out.append(_table(buf, pal))
            continue

        # heading
        head = re.match(r"^(#{1,4})\s+(.*)$", line)
        if head:
            size = {1: 18, 2: 16, 3: 15, 4: 14}[len(head.group(1))]
            out.append(
                f'<div style="font-size:{size}px;margin:16px 0 6px 0;">'
                f"<b>{_inline(head.group(2), pal)}</b></div>")
            i += 1
            continue

        # horizontal rule
        if re.match(r"^\s*([-*_])\s*(\1\s*){2,}$", line):
            out.append(f'<div style="border-top:1px solid {pal["code_border"]};'
                       f'margin:10px 0;"></div>')
            i += 1
            continue

        # lists - gathered so consecutive items form one block
        if re.match(r"^\s*([-*+]|\d+[.)])\s+", line):
            ordered = bool(re.match(r"^\s*\d+[.)]\s+", line))
            items = []
            while i < len(lines) and re.match(r"^\s*([-*+]|\d+[.)])\s+", lines[i]):
                items.append(re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", lines[i]))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>"
                       + "".join(f'<li style="margin:3px 0;">{_inline(t, pal)}</li>'
                                 for t in items)
                       + f"</{tag}>")
            continue

        # blank line - just a separator; paragraph margins do the spacing
        if not line.strip():
            i += 1
            continue

        # plain paragraph: gather the run of non-blank lines that is not the
        # start of some other block, and join them with soft breaks
        buf = []
        while i < len(lines):
            nxt = lines[i]
            if not nxt.strip():
                break
            if (re.match(r"^\s*```", nxt)
                    or re.match(r"^(#{1,4})\s+", nxt)
                    or re.match(r"^\s*([-*+]|\d+[.)])\s+", nxt)
                    or nxt.strip().startswith("|")
                    or re.match(r"^\s*([-*_])\s*(\s*){2,}$", nxt)):
                break
            buf.append(nxt.strip())
            i += 1
        if buf:
            out.append(f'<div style="margin:9px 0;">'
                       + "<br>".join(_inline(b, pal) for b in buf)
                       + "</div>")

    return "".join(out), codes
