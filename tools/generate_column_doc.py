"""Generate a Word .docx documenting where every 911 Runtime Estimator output
column is pulled from. Self-contained (writes the OpenXML zip directly, no
python-docx dependency). Re-run after column changes to refresh the doc:

    python tools/generate_column_doc.py
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parents[1] / "docs" / \
    "911 Runtime Estimator - Column Sources.docx"

# ── Content ────────────────────────────────────────────────────────────────

INTRO = [
    "This document lists every column in the workbook produced by the 911 "
    "Runtime Estimator plugin (id 911_runtime_estimator) and where each value "
    "comes from. The output file is named "
    "“911 RUNTIME ESTIMATOR - {root} - {date}.xlsx” and contains two "
    "identically-structured sheets, Plates and Non-Plates.",
    "Columns fall into two groups: (1) every column from the order’s "
    "BATCH LIST workbook, reproduced verbatim in its native order, and (2) the "
    "columns the plugin generates itself (from the nest packet PDFs or by "
    "calculation), appended after the batch-list block. “Order” is "
    "placed first as a row label.",
    "Batch-list values are read by HEADER NAME (the header row is auto-detected "
    "by scanning for ‘Nest Pkg Nbr’ / ‘PPN Quantity’), so "
    "they survive column shifts between files. The exact set and order of "
    "batch-list columns is whatever that order’s workbook contains; the "
    "list below is the standard layout.",
]

# Batch-list columns: (output header, note)
BATCH_COLS = [
    ("Work Order", ""),
    ("DYPN", ""),
    ("Assembly", ""),
    ("PPN Quantity", "Drives the estimate (pieces) and the pivot quantity sum."),
    ("Source Material", "Batch list’s own ‘Material’ column (an EB "
                        "stock code, e.g. EB211029001) — renamed to "
                        "‘Source Material’ to keep it distinct from the "
                        "generated Material column."),
    ("Description", "Also a thickness fallback (‘… THK …’) and "
                    "the plate vs non-plate split."),
    ("Material Amount (Total)", ""),
    ("DYPN QTY", ""),
    ("Nest Pkg Nbr", "Key that joins a batch row to its packet PDF and the top "
                     "level of the pivot."),
    ("Nuclear", ""),
    ("Hull Integrity Y/N", ""),
    ("Level", ""),
    ("Subsafe Y/N", ""),
    ("Fly by Wire Y/N", ""),
    ("DSS-SOC Y/N", ""),
    ("NOFORN Y/N", ""),
    ("Planner Code", ""),
    ("WO Status", ""),
    ("WO Start Date", ""),
    ("WO Due Date", ""),
    ("WO Target Hours", ""),
    ("Activity Start", ""),
    ("Activity Close", ""),
    ("WAFF", ""),
    ("Document No", ""),
    ("Rem Used", ""),
    ("Rem Created", ""),
    ("Requirement Status", ""),
    ("Doc Location", ""),
    ("Trade Instruction", ""),
    ("SCOPE OF WORK", "Triggers the +180 min/pc bevel surcharge when it contains "
                      "‘BEVEL’."),
]

# Generated columns: (output header, origin, how it's derived)
GEN_COLS = [
    ("Order", "Folder name",
     "The order subfolder’s name under the ROOT directory you pick at "
     "runtime (e.g. V090). Identifies which order each row came from."),
    ("Process", "Batch list, else PDF",
     "The batch list’s ‘Process’ column if present; otherwise the "
     "cut method detected on page 1 of the nest packet PDF "
     "(PLASMA / LASER / WATERJET / TELESIS / OXY…)."),
    ("Thickness (in)", "Nest packet PDF",
     "Page-1 ‘Orders / Pieces / Thickness / Length / Width’ data row. "
     "Fallbacks: the REMNANT ‘THICK:’ field, then the batch-list "
     "Description ‘… THK …’ (row flagged ‘thk from "
     "desc’). If none is found the row is left blank, flagged ‘no "
     "thickness’, and highlighted yellow."),
    ("Stock L", "Nest packet PDF",
     "Part-sketch ‘SIZE:’ field — prefers the stock form "
     "‘#L x W’, else ‘thk x L x W’. Normalized so L is the "
     "larger dimension."),
    ("Stock W", "Nest packet PDF",
     "Same ‘SIZE:’ field as Stock L; W is the smaller dimension."),
    ("Mil Spec", "Nest packet PDF",
     "The ‘MIL SPEC:’ label value; fallback is a regex match for "
     "‘MIL-S-…’ anywhere in the packet text."),
    ("Material", "Nest packet PDF (MOVE TICKET)",
     "The ‘MATERIAL:’ value on the MOVE TICKET pages — the one "
     "that follows ‘MIL SPEC:’ (e.g. HSS). Only MOVE TICKET pages are "
     "scanned so a stray MATERIAL elsewhere can’t win. This is the part "
     "material designation, distinct from ‘Source Material’."),
    ("Source", "Nest packet PDF",
     "The ‘SOURCE:’ (remnant) or ‘SRCE:’ (part-sketch) label "
     "value — where the stock came from."),
    ("Est Cut Hours", "Computed",
     "The plate-cutting time estimate (see the Calculation section). Inputs: "
     "Thickness (PDF/Description), PPN Quantity, and SCOPE OF WORK. This column "
     "is PER ROW; per-nest totals appear in the pivot below the table."),
    ("Flags", "Computed",
     "Notes about how the row was estimated: ‘no thickness’, ‘thk "
     "from desc’, ‘bevel +180/pc’."),
]

CALC = [
    "Est Cut Hours is computed per batch-list row:",
    "• band(t) = minutes per piece by thickness: 6 if t < 0.5″, 9 if "
    "0.5″ ≤ t < 1.0″, 12 if 1.0″ ≤ t < 2.0″, 18 if "
    "t ≥ 2.0″.",
    "• Factor = thickness × band(t)  (minutes per piece).",
    "• Row minutes = Factor × PPN Quantity, plus 180 × PPN "
    "Quantity when SCOPE OF WORK contains ‘BEVEL’ (case-insensitive "
    "substring — compound scopes like ‘CUT/BEVEL’ count).",
    "• Est Cut Hours = Row minutes ÷ 60.",
    "If thickness cannot be determined, no estimate is produced and the row is "
    "highlighted yellow.",
]

SUMMARY = [
    "Sheets: rows are split into Plates and Non-Plates — a row is a plate "
    "if its Description says PLATE or an estimate was computed (a plate "
    "thickness was found); shapes, bars and tubes go to Non-Plates.",
    "Pivot: below each data table is a summary grouped Nest Pkg Nbr → PPN "
    "Quantity → Description → Process, summing Est Cut Hours and PPN "
    "Quantity. The nest-level row is the per-nest total; the Grand Total is the "
    "sum across all nests on that sheet. Orders are not a subtotal level.",
    "Highlighting: any row missing the data needed to estimate (no thickness) "
    "is filled yellow so it can be found and filled in by hand.",
]

# ── OOXML builders ───────────────────────────────────────────────────────────

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"')


def esc(s: str) -> str:
    return escape(str(s))


def para(text: str, *, style: str | None = None, bold: bool = False) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return (f"<w:p>{ppr}<w:r>{rpr}"
            f'<w:t xml:space="preserve">{esc(text)}</w:t></w:r></w:p>')


def cell(text: str, *, bold: bool = False, width: int | None = None,
         shade: str | None = None) -> str:
    tcpr = "<w:tcPr>"
    if width:
        tcpr += f'<w:tcW w:w="{width}" w:type="dxa"/>'
    if shade:
        tcpr += f'<w:shd w:val="clear" w:color="auto" w:fill="{shade}"/>'
    tcpr += "</w:tcPr>"
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    body = "".join(
        f'<w:p><w:r>{rpr}<w:t xml:space="preserve">{esc(line)}</w:t></w:r></w:p>'
        for line in (text.split("\n") if text else [""]))
    if not body:
        body = "<w:p/>"
    return f"<w:tc>{tcpr}{body}</w:tc>"


def row(cells: list[str]) -> str:
    return f"<w:tr>{''.join(cells)}</w:tr>"


def table(grid: list[int], rows: list[str]) -> str:
    cols = "".join(f'<w:gridCol w:w="{w}"/>' for w in grid)
    pr = ('<w:tblPr><w:tblStyle w:val="TableGrid"/>'
          '<w:tblW w:w="0" w:type="auto"/>'
          '<w:tblBorders>'
          + "".join(f'<w:{e} w:val="single" w:sz="4" w:space="0" '
                    f'w:color="999999"/>'
                    for e in ("top", "left", "bottom", "right",
                              "insideH", "insideV"))
          + "</w:tblBorders></w:tblPr>")
    return f"<w:tbl>{pr}<w:tblGrid>{cols}</w:tblGrid>{''.join(rows)}</w:tbl>"


def build_body() -> str:
    parts: list[str] = []
    parts.append(para("911 Runtime Estimator — Column Source Reference",
                      style="Title"))
    parts.append(para("Where every output column comes from · "
                      "plugin id 911_runtime_estimator", style="Subtitle"))
    for p in INTRO:
        parts.append(para(p))

    # Section 1: batch-list columns
    parts.append(para("1. Batch List columns (reproduced verbatim, native order)",
                      style="Heading1"))
    rows = [row([cell("#", bold=True, shade="D9E1F2", width=600),
                 cell("Output column", bold=True, shade="D9E1F2", width=3200),
                 cell("Source / notes", bold=True, shade="D9E1F2", width=5800)])]
    for i, (name, note) in enumerate(BATCH_COLS, start=1):
        src = ("Read directly from the *BATCH LIST.xlsx by header name. " + note).strip()
        rows.append(row([cell(str(i), width=600),
                         cell(name, width=3200),
                         cell(src, width=5800)]))
    parts.append(table([600, 3200, 5800], rows))

    # Section 2: generated columns
    parts.append(para("2. Generated columns (from the nest PDFs or computed)",
                      style="Heading1"))
    rows = [row([cell("Output column", bold=True, shade="D9E1F2", width=2200),
                 cell("Origin", bold=True, shade="D9E1F2", width=2200),
                 cell("How it is derived", bold=True, shade="D9E1F2", width=5200)])]
    for name, origin, how in GEN_COLS:
        rows.append(row([cell(name, width=2200),
                         cell(origin, width=2200),
                         cell(how, width=5200)]))
    parts.append(table([2200, 2200, 5200], rows))

    # Section 3: calculation
    parts.append(para("3. Est Cut Hours calculation", style="Heading1"))
    for p in CALC:
        parts.append(para(p))

    # Section 4: workbook layout
    parts.append(para("4. Sheets, pivot and highlighting", style="Heading1"))
    for p in SUMMARY:
        parts.append(para(p))

    sect = ('<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
            '<w:pgMar w:top="1080" w:right="1080" w:bottom="1080" '
            'w:left="1080" w:header="720" w:footer="720" w:gutter="0"/>'
            "</w:sectPr>")
    return f'<w:body>{"".join(parts)}{sect}</w:body>'


DOCUMENT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document {NS}>{build_body()}</w:document>')

STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          f'<w:styles {NS}>'
          '<w:docDefaults><w:rPrDefault><w:rPr>'
          '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/>'
          '<w:sz w:val="20"/></w:rPr></w:rPrDefault></w:docDefaults>'
          '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
          '<w:name w:val="Normal"/><w:pPr><w:spacing w:after="120"/></w:pPr></w:style>'
          '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/>'
          '<w:pPr><w:spacing w:after="120"/></w:pPr>'
          '<w:rPr><w:b/><w:sz w:val="44"/><w:color w:val="1F4E78"/></w:rPr></w:style>'
          '<w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/>'
          '<w:pPr><w:spacing w:after="240"/></w:pPr>'
          '<w:rPr><w:i/><w:sz w:val="22"/><w:color w:val="595959"/></w:rPr></w:style>'
          '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
          '<w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr>'
          '<w:rPr><w:b/><w:sz w:val="28"/><w:color w:val="1F4E78"/></w:rPr></w:style>'
          '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/>'
          '<w:tblPr><w:tblBorders>'
          '<w:top w:val="single" w:sz="4" w:space="0" w:color="999999"/>'
          '<w:left w:val="single" w:sz="4" w:space="0" w:color="999999"/>'
          '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="999999"/>'
          '<w:right w:val="single" w:sz="4" w:space="0" w:color="999999"/>'
          '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="999999"/>'
          '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="999999"/>'
          '</w:tblBorders></w:tblPr></w:style>'
          '</w:styles>')

CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                 '<Default Extension="xml" ContentType="application/xml"/>'
                 '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                 '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                 '</Types>')

RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>')

DOC_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>')


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", DOCUMENT)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
