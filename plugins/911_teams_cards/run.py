"""
911 Teams Cards - post one Teams modeling card per nest waiting to be set up.

Split out of 911 Setup as its OWN app on 2026-08-10 (C.D. 2026-08-06: "maybe
the Teams card generation and schedule update can be separate from the 911
Setup, cause I don't want to make Teams cards every time I run the setup").
It was always the odd stage out -- the only one that is not about the batch
you are setting up, and the only one that needed no batch number -- so it now
runs on its own.

This module is the SINGLE HOME of everything that touches the EB 922 Schedule:
the card work list, the card payload, the posted-card ledger, and the STATUS
write-back. 911 Setup imports it (the same sibling-import pattern it already
uses for 911_remove_ticket's cover-stamp helpers) both for its own optional
"Generate Teams Cards" stage and to advance a nest's STATUS to NEED MODEL once
the batch is actually set up. Never fork this logic back into 911 Setup.

Entry point: run(params, progress_callback, cancel_event).
"""

import datetime as _dt
import json
import re
import threading
from pathlib import Path

from techdeck.core import plugin_sdk as sdk


# ---------------------------------------------------------------------------
# Sibling helpers -- 911_remove_ticket owns the schedule's colour reading
# (_schedule_path / _theme_rgbs / _fill_rgb / _match_fill), shared with the
# packet difficulty stamp. One home, imported, never copied.
# ---------------------------------------------------------------------------
_omit_stamps = None


def _load_omit_stamp_helpers(log):
    """The sibling 911_remove_ticket module, or None with one logged warning."""
    global _omit_stamps
    if _omit_stamps is not None:
        return _omit_stamps or None
    try:
        _omit_stamps = sdk.load_sibling("911_remove_ticket", __file__)
    except Exception as e:
        log(f"  WARNING: 911 Remove Ticket helpers unavailable ({e}) - the "
            f"schedule's difficulty colours cannot be read.")
        _omit_stamps = False
    return _omit_stamps or None


def _base_qtdr(override: str = "") -> Path:
    """911 QTDR root. Override wins; otherwise auto-discover across every
    OneDrive path variant (the base name differs per machine)."""
    root = sdk.resolve_911_qtdr_root(override)
    if root is not None:
        return root
    return sdk.pilot_program_roots()[0] / "911 QTDR"


def _find_batch_list(batch_folder: Path, batch_number: str) -> Path:
    """
    Locate the BATCH LIST excel inside the batch folder.
    Expected name: "<batch_number> BATCH LIST.xlsx" (case-insensitive).
    Falls back to any .xlsx containing 'BATCH LIST' if exact name not found.

    Kept in step with 911 Setup's copy of the same lookup -- both read the same
    files, and the card title's stock code comes out of this workbook.
    """
    exact = batch_folder / f"{batch_number} BATCH LIST.xlsx"
    if sdk.exists(exact):
        return exact

    for f in batch_folder.iterdir():
        if (sdk.is_file(f)
                and f.suffix.lower() == ".xlsx"
                and "BATCH LIST" in f.name.upper()
                and not f.name.startswith("~")):
            return f

    raise FileNotFoundError(
        f"No BATCH LIST file found in {batch_folder}. "
        f"Expected '{batch_number} BATCH LIST.xlsx'."
    )


# ===========================================================================
# Generate Teams Cards (v1.8.0)
# ===========================================================================
# One card per nest that is WAITING to be set up, posted to the MODELING
# bucket of the SOPO D911 PIPELINE plan (D922 channel) through a Power
# Automate webhook -- the same "TechDeck never touches Planner directly"
# pattern 922 Setup uses (flow recipe: docs/TEAMS_CARDS.md, flow #3).
#
# The work list is NOT the batch folder: it is the EB 922 Schedule's
# "CURRENT PIPELINE" sheet, every row where DEPT. is 911 and STATUS is
# "NEED TEAMS/SETUP". That makes the stage batch-independent -- it cards the
# whole 911 queue, whichever batch each nest belongs to -- so it runs before
# (and without) the batch prompt.
#
# Per row:
#   col B "BATCH / NEST"  "V092 503836" -> batch V092, nest 503836
#   col C "DATE"          -> the card's due date
#   col D "NOTES"         -> source-material text -> SAW CUT / TUBE LASER
#                            label, and whether the "Program" checklist item
#                            applies (tube stock only)
#   col E "RATING"        -> SIMPLE / MEDIUM / DIFFICULT, read from the CELL
#                            COLOUR (the cell holds no text) via the sibling
#                            911 Remove Ticket helpers -- the single home of
#                            that logic, shared with the packet stamp
#
# The "(#)" in the card title is the nest's EB source-material stock code
# (e.g. 211076345), which lives in the batch's own BATCH LIST 'Material'
# column -- not on the schedule. Each referenced batch's BATCH LIST is read
# once and cached.
# ---------------------------------------------------------------------------

# The 'TechDeck 911 Setup - Create Modeling Cards' Power Automate flow
# (built + turned on 2026-08-03; recipe in docs/TEAMS_CARDS.md, flow #3).
# Baked in so a fresh install posts out of the box — the same reason 922 Setup
# carries its URL as a constant, after v0.8.6.8 shipped with a blank default
# and silently dry-ran on every machine but the author's. The Settings field
# is an OVERRIDE (e.g. pointing at a rebuilt/test flow without an app update);
# the card_dry_run toggle is how you preview without posting. If the flow is
# ever recreated, update this constant AND ship an app update.
DEFAULT_CARD_WEBHOOK_URL = (
    "https://REDACTED-ENVIRONMENT.api"
    ".powerplatform.com:443/powerautomate/automations/direct/cu/15/workflows/"
    "REDACTED-WORKFLOW-ID/triggers/manual/paths/invoke"
    "?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0"
    "&sig=REDACTED"
)

_CARD_PREVIEW_FILENAME = "last_911_setup_payload.json"

# Schedule sheet + the headers we read, all looked up BY NAME (Hard Rules 1-2)
# -- the live sheet ships them with trailing spaces ('DEPT. ', 'STATUS ').
_SCHED_SHEET = "CURRENT PIPELINE"
_SCHED_DEPT = "DEPT."
_SCHED_KEY = "BATCH / NEST"
_SCHED_DATE = "DATE"
_SCHED_NOTES = "NOTES"
_SCHED_RATING = "RATING"
_SCHED_STATUS = "STATUS"

# The two stops after 'NEED TEAMS/SETUP' on the status belt (card_template.json
# overrides both). Fallbacks only -- see the write-back section below.
_STATUS_AFTER_CARDS_DEFAULT = "NEED SETUP"
_STATUS_AFTER_SETUP_DEFAULT = "NEED MODEL"


def _load_card_template() -> dict:
    """Load card_template.json sitting next to this file."""
    with open(Path(__file__).with_name("card_template.json"),
              "r", encoding="utf-8") as fh:
        return json.load(fh)


def _norm_text(value) -> str:
    """Uppercase, whitespace-collapsed form used for every schedule match."""
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip().upper()


def _norm_status(value) -> str:
    """_norm_text plus tightened slashes, so a hand-typed 'NEED TEAMS / SETUP'
    still matches the canonical 'NEED TEAMS/SETUP'."""
    return re.sub(r"\s*/\s*", "/", _norm_text(value))


def _split_batch_nest(value):
    """'V092 503836' -> ('V092', '503836'); 'V085 S20085' -> ('V085','S20085').

    Batch first, nest LAST -- never a digits-only match, because nests are not
    always numeric (Hard Rule 3's alphanumeric-nest class). Returns
    (None, None) when the cell does not carry both halves.
    """
    tokens = _norm_text(value).split()
    if len(tokens) < 2:
        return None, None
    return tokens[0], tokens[-1]


def _due_date_iso(value) -> str:
    """Schedule DATE cell -> an ISO-8601 instant Planner accepts, or "".

    Non-dates are expected and fine: the column also carries 'HOLD' and 'N/A'
    for nests with no scheduled date, which simply means no due date.
    """
    if isinstance(value, _dt.datetime):
        return value.strftime("%Y-%m-%dT00:00:00Z")
    if isinstance(value, _dt.date):
        return value.strftime("%Y-%m-%dT00:00:00Z")
    return ""


def _resolve_machine(material_text: str, template: dict):
    """'SAW CUT' / 'TUBE LASER' / None for a source-material description.

    The rule, in order (C.D. 2026-08-03):
      1. the material says TUBE -> it IS a tube -> TUBE LASER
      2. otherwise a '(TL)' note means it is going on the tube laser anyway
      3. everything else -> SAW CUT

    Shape does NOT imply the tube laser -- an angle is an angle, and the
    '(TL)' marker is exactly how the schedule flags the exceptions. Only a
    completely EMPTY material text returns None, so that card is created
    unlabelled and reported rather than guessed at.
    """
    text = _norm_text(material_text)
    if not text:
        return None
    if _is_tube(text, template):
        return "TUBE LASER"
    for marker in (template.get("machine_tube_markers") or ["TL"]):
        if re.search(r"\(\s*" + re.escape(_norm_text(marker)) + r"\s*\)", text):
            return "TUBE LASER"
    return template.get("machine_default", "SAW CUT")


def _is_tube(material_text: str, template: dict) -> bool:
    """True when the source material is tube stock (drives the 'Program'
    checklist item -- a tube-laser program is meaningless on saw stock)."""
    text = _norm_text(material_text)
    return any(_norm_text(k) in text
               for k in (template.get("tube_keywords") or ["TUBE"]))


def _read_schedule_rows(params, template, log, cancel_event):
    """Every CURRENT PIPELINE row that needs a card -> (rows, problem_text).

    ``problem_text`` is non-empty when the whole lookup was unavailable (the
    schedule is missing, open in Excel, or has no such sheet); the caller
    reports it and skips the stage rather than posting a half-built payload.

    Each row dict: batch, nest, date, notes, difficulty, excel_row.
    """
    stamps = _load_omit_stamp_helpers(log)
    if stamps is None:
        return [], ("The 911 Remove Ticket helpers could not be loaded, so the "
                    "EB 922 Schedule's difficulty colours cannot be read and "
                    "no Teams cards were created.")

    path = stamps._schedule_path(params)
    if path is None:
        return [], ("The EB 922 Schedule workbook could not be found, so no "
                    "Teams cards were created. Check that the '922 QTDR "
                    "Production Packages' folder is synced, or set the "
                    "'EB 922 Schedule' path in this plugin's Settings.")
    log(f"Schedule      : {path}")
    try:
        wb = sdk.load_workbook_resilient(path, log=log, data_only=True)
    except Exception as exc:
        return [], (f"The Teams-card work list could not be read from "
                    f"{path.name}:\n\n{exc}\n\nNo Teams cards were created.")

    try:
        if _SCHED_SHEET not in wb.sheetnames:
            return [], (f"{path.name} has no '{_SCHED_SHEET}' sheet, so no "
                        f"Teams cards were created.")
        ws = wb[_SCHED_SHEET]
        # prefix_ok + header_col: these headers are hand-maintained and
        # have drifted before ('RATING' -> 'RATING/PC COUNT').
        hdr_row, hdr = sdk.find_header_row(
            ws, [_SCHED_KEY, _SCHED_STATUS], prefix_ok=True)
        if not hdr_row:
            return [], (f"{path.name} has no row containing both "
                        f"'{_SCHED_KEY}' and '{_SCHED_STATUS}' on the "
                        f"'{_SCHED_SHEET}' sheet, so no Teams cards were "
                        f"created.")
        c_key = sdk.header_col(hdr, _SCHED_KEY)
        c_status = sdk.header_col(hdr, _SCHED_STATUS)
        c_dept = sdk.header_col(hdr, _SCHED_DEPT)
        c_date = sdk.header_col(hdr, _SCHED_DATE)
        c_notes = sdk.header_col(hdr, _SCHED_NOTES)
        c_rating = sdk.header_col(hdr, _SCHED_RATING)
        theme_rgbs = stamps._theme_rgbs(wb)

        want_dept = _norm_text(template.get("schedule_dept", "911"))
        want_status = _norm_status(template.get("schedule_status",
                                                "NEED TEAMS/SETUP"))

        rows = []
        for r in range(hdr_row + 1, ws.max_row + 1):
            if r % 64 == 0:
                sdk.raise_if_cancelled(cancel_event)
            if c_dept and _norm_text(ws.cell(r, c_dept).value) != want_dept:
                continue
            if _norm_status(ws.cell(r, c_status).value) != want_status:
                continue
            batch, nest = _split_batch_nest(ws.cell(r, c_key).value)
            difficulty = None
            if c_rating:
                difficulty = stamps._match_fill(
                    stamps._fill_rgb(ws.cell(r, c_rating), theme_rgbs))
            rows.append({
                "excel_row": r,
                "raw_key": str(ws.cell(r, c_key).value or "").strip(),
                "batch": batch,
                "nest": nest,
                "date": ws.cell(r, c_date).value if c_date else None,
                "notes": ws.cell(r, c_notes).value if c_notes else None,
                "difficulty": difficulty,
            })
        return rows, ""
    finally:
        try:
            wb.close()
        except Exception:
            pass


def _read_batch_list_materials(qtdr_root: Path, batch: str, log):
    """{NEST: {'code': EB stock code, 'desc': description}} for one batch.

    The card title's "(#)" is this stock code -- the schedule does not carry
    it, the batch's own BATCH LIST does ('Material' column, keyed by
    'Nest Pkg Nbr'). The description doubles as the source-material fallback
    for schedule rows whose NOTES cell is blank.

    Returns (mapping, warning_text); an unreadable/absent BATCH LIST yields
    ({}, why) and the batch's cards are simply created without a code.
    """
    batch_folder = qtdr_root / batch
    if not sdk.is_dir(batch_folder):
        return {}, (f"No batch folder '{batch}' under {qtdr_root} - its cards "
                    f"have no source-material code.")
    try:
        path = _find_batch_list(batch_folder, batch)
    except FileNotFoundError as exc:
        return {}, f"{exc} Cards for batch {batch} have no source-material code."

    try:
        wb = sdk.load_workbook_resilient(path, log=log, data_only=True,
                                         read_only=True)
    except Exception as exc:
        return {}, (f"Could not read {path.name}: {exc} - cards for batch "
                    f"{batch} have no source-material code.")
    try:
        ws = wb["BATCH"] if "BATCH" in wb.sheetnames else wb[wb.sheetnames[0]]
        hdr_row, hdr = sdk.find_header_row(ws, ["NEST PKG NBR", "MATERIAL"])
        if not hdr_row:
            return {}, (f"{path.name} has no 'Nest Pkg Nbr' + 'Material' header "
                        f"row - cards for batch {batch} have no source-material "
                        f"code.")
        c_nest = hdr["NEST PKG NBR"]
        c_mat = hdr["MATERIAL"]
        c_desc = hdr.get("DESCRIPTION")
        out: dict = {}
        for row in ws.iter_rows(min_row=hdr_row + 1, values_only=True):
            nest = row[c_nest - 1] if c_nest - 1 < len(row) else None
            key = _norm_text(nest)
            if not key or key in out:
                continue
            code = row[c_mat - 1] if c_mat - 1 < len(row) else None
            desc = row[c_desc - 1] if c_desc and c_desc - 1 < len(row) else None
            if code is None and desc is None:
                continue
            out[key] = {"code": str(code).strip() if code is not None else "",
                        "desc": str(desc).strip() if desc is not None else ""}
        return out, ""
    finally:
        try:
            wb.close()
        except Exception:
            pass


def _build_card(row: dict, material: dict, template: dict, label_map: dict,
                warnings: list, unlabelled: list):
    """One schedule row -> one Teams card dict (plus its label NAMES for the log)."""
    batch, nest = row["batch"], row["nest"]
    code = (material or {}).get("code", "")
    # NOTES is the authority (it carries the (TL)/(SAW) overrides); the BATCH
    # LIST description is the fallback for the rows planning has not annotated
    # yet, so a blank NOTES cell still resolves a machine instead of nothing.
    material_text = str(row.get("notes") or "").strip() or (material or {}).get("desc", "")

    if code:
        title = template.get("title_format",
                             "BATCH: {batch} - NEST: {nest} ({material})").format(
            batch=batch, nest=nest, material=code)
    else:
        title = template.get("title_format_no_material",
                             "BATCH: {batch} - NEST: {nest}").format(
            batch=batch, nest=nest)

    # Checklist: the tube-only items (Program) drop out on saw stock.
    checklist = list(template.get("checklist", []))
    if not _is_tube(material_text, template):
        tube_only = {_norm_text(t) for t in (template.get("tube_only_checklist") or [])}
        checklist = [t for t in checklist if _norm_text(t) not in tube_only]

    names = []
    if row.get("difficulty"):
        names.append(row["difficulty"])
    machine = _resolve_machine(material_text, template)
    if machine:
        names.append(machine)
    else:
        unlabelled.append(f"{batch} {nest}"
                          + (f" ({material_text})" if material_text else " (no material listed)"))

    slots = []
    for name in names:
        slot = label_map.get(_norm_text(name))
        if slot:
            slots.append(slot)
        else:
            warnings.append(f"No Teams label mapped for '{name}' - skipped on "
                            f"{batch} {nest} (add it to card_template.json's "
                            f"label_map AND to the plan's labels).")

    card = {
        "title": title,
        "bucket": template.get("bucket", "MODELING"),
        "priority": template.get("priority", "Medium"),
        "status": template.get("status", "Not started"),
        "checklist": checklist,
        "labels": slots,
    }
    # dueDate is OMITTED, not blanked, when the nest has no scheduled date
    # (the DATE column also carries HOLD / N/A). The flow feeds this straight
    # into Planner's Due Date Time; an absent key reads as null and creates
    # the card with no due date, where an empty STRING fails the action.
    due = _due_date_iso(row.get("date"))
    if due:
        card["dueDate"] = due
    return card, names


# ── Posted-card ledger ──────────────────────────────────────────────────────
# SECOND line of duplicate defence. The flow itself already drops any card
# whose exact title is already in the plan (docs/TEAMS_CARDS.md, flow #3 step
# 7), and that is the authoritative check because it reads the real plan. The
# ledger is the local half: it stops the plugin from even OFFERING a card it
# has already posted from this machine, so a re-run's log says "23 already
# carded" instead of listing 31 cards it silently expects the flow to throw
# away.
#
# Deliberately advisory: delete the file (path is logged on every suppression)
# to re-offer everything — which is what you want after deleting cards in
# Planner on purpose. Never written on a dry run or a failed post.
# DELIBERATELY still named for 911_setup: this ledger predates the split and
# lives in %LOCALAPPDATA%\TechDeck, so every existing user already has one.
# Renaming it would read as an empty ledger and re-offer every nest that has
# already been carded. The filename is a migration constraint, not a label.
_LEDGER_FILENAME = "911_setup_posted_cards.json"


def _ledger_path() -> Path:
    import os
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "TechDeck" / _LEDGER_FILENAME


def _load_posted_titles(log) -> set:
    """Titles this machine has already posted. Unreadable ledger -> empty set
    (degrade to the flow's own dedupe rather than blocking the run)."""
    path = _ledger_path()
    if not sdk.is_file(path):
        return set()
    try:
        # utf-8-SIG on the read: the ledger is documented as user-editable
        # (delete it to re-offer everything), and anything on Windows that
        # rewrites it — Notepad, PowerShell's Out-File -Encoding utf8 — adds a
        # BOM that plain utf-8 rejects. Writes stay BOM-less utf-8.
        with open(path, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return {str(t) for t in (data.get("titles") or [])}
    except (OSError, json.JSONDecodeError, AttributeError) as exc:
        log(f"  (Could not read the posted-card ledger: {exc} - relying on the "
            f"flow's own duplicate check.)")
        return set()


def _record_posted_titles(titles, log) -> None:
    """Append successfully-posted titles to the ledger. Failures only log —
    a ledger write must never fail a run whose cards were created."""
    path = _ledger_path()
    merged = sorted(_load_posted_titles(log) | set(titles))
    try:
        sdk.ensure_dir(path.parent)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"plan": "EB SOPO D911", "titles": merged}, fh, indent=2)
    except OSError as exc:
        log(f"  (Could not update the posted-card ledger: {exc})")


# ===========================================================================
# Schedule status write-back (v1.9.0)
# ===========================================================================
# The EB 922 Schedule's STATUS column is a conveyor belt, and as of
# 2026-08-10 TechDeck is what advances it (C.D.; until now the schedule was
# read-only and every status was moved by hand):
#
#   NEED TEAMS/SETUP --(card posted)--> NEED SETUP --(setup ran)--> NEED MODEL
#
# Only rows that genuinely reached the next stage move. A nest whose card was
# SKIPPED (blank NOTES, no stock code) or whose post failed keeps
# NEED TEAMS/SETUP so it is re-offered next run -- the same rule the
# posted-card ledger already follows -- and a nest still sitting at
# NEED TEAMS/SETUP is never jumped straight to NEED MODEL by a setup-only
# run, because that would erase the fact that it still needs a card.
#
# Written through Excel COM, never openpyxl: the RATING column carries each
# nest's difficulty as a CELL FILL COLOUR, and the sheet has conditional
# formatting openpyxl already warns about on load and would drop on save.
# COM touches only the cells we name.
#
# Unlike _build_inspection_sheets_via_excel this opens the real file IN PLACE
# and calls Save(). That builder's temp-copy + os.replace dance exists because
# Excel SaveAs fails onto a OneDrive path; a plain in-place Save is what Excel
# does for a human all day. Replacing this file wholesale would also clobber
# whatever planning edited while we were running.
#
# The schedule is shared, so it is often open on someone else's machine. That
# must NEVER cost a card: the cards post first, and any row we could not write
# is listed for the user to change by hand (C.D. 2026-08-10).
# ---------------------------------------------------------------------------

def _schedule_status_rows(params, template, log, cancel_event=None):
    """(path, status_col, rows, problem) for every DEPT. 911 pipeline row.

    ``rows`` are {"excel_row", "batch", "nest", "status"} with ``status``
    already through _norm_status. Read-only -- _write_schedule_statuses is
    the only thing that changes a cell. ``problem`` is non-empty when the
    lookup could not happen at all.
    """
    stamps = _load_omit_stamp_helpers(log)
    if stamps is None:
        return None, None, [], ("the 911 Remove Ticket helpers could not be "
                                "loaded, so the schedule could not be read")
    path = stamps._schedule_path(params)
    if path is None:
        return None, None, [], "the EB 922 Schedule workbook could not be found"
    try:
        wb = sdk.load_workbook_resilient(path, log=log, data_only=True)
    except Exception as exc:
        return path, None, [], f"{path.name} could not be read: {exc}"
    try:
        if _SCHED_SHEET not in wb.sheetnames:
            return path, None, [], f"{path.name} has no '{_SCHED_SHEET}' sheet"
        ws = wb[_SCHED_SHEET]
        # Header row scanned, never assumed (Hard Rule 2); columns by NAME
        # (Hard Rule 1) -- the live sheet ships them with trailing spaces.
        hdr_row, hdr = sdk.find_header_row(ws, [_SCHED_KEY, _SCHED_STATUS])
        if not hdr_row:
            return path, None, [], (f"{path.name} has no row containing both "
                                    f"'{_SCHED_KEY}' and '{_SCHED_STATUS}'")
        c_key = sdk.header_col(hdr, _SCHED_KEY)
        c_status = sdk.header_col(hdr, _SCHED_STATUS)
        c_dept = sdk.header_col(hdr, _SCHED_DEPT)
        want_dept = _norm_text(template.get("schedule_dept", "911"))
        rows = []
        for r in range(hdr_row + 1, ws.max_row + 1):
            if cancel_event is not None and r % 64 == 0:
                sdk.raise_if_cancelled(cancel_event)
            if c_dept and _norm_text(ws.cell(r, c_dept).value) != want_dept:
                continue
            batch, nest = _split_batch_nest(ws.cell(r, c_key).value)
            rows.append({"excel_row": r, "batch": batch, "nest": nest,
                         "status": _norm_status(ws.cell(r, c_status).value)})
        return path, c_status, rows, ""
    finally:
        try:
            wb.close()
        except Exception:
            pass


def _write_schedule_statuses(path: Path, status_col: int, updates: list):
    """Stamp STATUS on the named schedule rows via Excel COM, in place.

    ``updates`` is [(excel_row, new_status, label)] -- ``label`` is only for
    the caller's hand-fix list. Returns (written, failure_text); a non-empty
    ``failure_text`` means NOTHING was written.
    """
    if not updates:
        return 0, ""
    try:
        import win32com.client
        import pythoncom
    except ImportError:
        return 0, ("the Excel COM bindings (pywin32) are not available on "
                   "this machine")

    xlCalculationManual = -4135
    pythoncom.CoInitialize()
    excel = None
    wb = None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        excel.ScreenUpdating = False
        excel.EnableEvents = False
        excel.AskToUpdateLinks = False
        try:
            excel.Calculation = xlCalculationManual
        except Exception:
            pass

        wb = excel.Workbooks.Open(
            Filename=str(path),
            UpdateLinks=0,
            ReadOnly=False,
            IgnoreReadOnlyRecommended=True,
            Notify=False,
            AddToMru=False,
        )
        # A workbook already open elsewhere opens READ-ONLY instead of
        # raising (the "file in use" prompt is suppressed by DisplayAlerts),
        # and Save() on it silently does nothing. Check before writing --
        # this is the shared-file case the whole hand-fix path exists for.
        if wb.ReadOnly:
            return 0, (f"{path.name} opened read-only, which means it is "
                       f"open on another machine")

        ws = wb.Sheets(_SCHED_SHEET)
        for excel_row, new_status, _label in updates:
            ws.Cells(excel_row, status_col).Value = new_status
        wb.Save()
        return len(updates), ""
    except Exception as exc:
        return 0, f"Excel refused the write ({exc})"
    finally:
        try:
            if wb is not None:
                # Already saved above; never let Close re-prompt or re-write.
                wb.Close(SaveChanges=False)
        except Exception:
            pass
        try:
            if excel is not None:
                excel.Quit()
        except Exception:
            pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def _advance_schedule_status(params, template, log, pairs, from_statuses,
                             new_status, cancel_event=None) -> list:
    """Move every DEPT. 911 row for ``pairs`` off ``from_statuses`` onto
    ``new_status``. ``pairs`` is an iterable of (batch, nest).

    Returns the labels of rows that still need changing BY HAND (empty on a
    clean write). Never raises and never blocks its caller: a locked schedule
    costs the user some typing, never a card (C.D. 2026-08-10).
    """
    if not bool(template.get("write_schedule_status", True)):
        return []
    wanted = {(_norm_text(b), _norm_text(n)) for b, n in pairs if b and n}
    if not wanted:
        return []

    try:
        path, status_col, rows, problem = _schedule_status_rows(
            params, template, log, cancel_event)
    except sdk.PluginCancelled:
        raise
    except Exception as exc:  # a status write must never sink the run
        problem, path, status_col, rows = str(exc), None, None, []

    if problem or not status_col:
        log(f"\n  ! EB 922 Schedule STATUS not updated - "
            f"{problem or 'no STATUS column found'}.")
        log(f"    Please set these to '{new_status}' by hand: "
            + ", ".join(sorted(f"{b} {n}" for b, n in wanted)))
        return sorted(f"{b} {n}" for b, n in wanted)

    from_set = {_norm_status(s) for s in from_statuses}
    updates = [(r["excel_row"], new_status, f"{r['batch']} {r['nest']}")
               for r in rows
               if (r["batch"], r["nest"]) in wanted and r["status"] in from_set]
    if not updates:
        return []

    written, failure = _write_schedule_statuses(path, status_col, updates)
    if failure:
        log(f"\n  {'!' * 46}")
        log(f"  ! Could not update the EB 922 Schedule - {failure}.")
        log(f"    Everything else finished normally. Please set these rows'")
        log(f"    STATUS to '{new_status}' by hand:")
        for excel_row, _st, label in updates:
            log(f"      row {excel_row}   {label}")
        log(f"  {'!' * 46}")
        return [label for _r, _s, label in updates]

    log(f"  EB 922 Schedule: {written} row(s) advanced to '{new_status}'.")
    return []


def _card_pick_label(card: dict, names: list, row: dict) -> str:
    """One row of the nest picker: what you need to decide yes/no.

    Batch + nest first (that is how the schedule reads and how people talk
    about a nest), then the labels the card will carry and its due date. The
    stock code stays out — it is in the card TITLE but it is not a thing
    anyone chooses by.
    """
    bits = [f"{row['batch']} {row['nest']}"]
    if names:
        bits.append(" / ".join(names))
    due = (card.get("dueDate") or "")[:10]
    bits.append(f"due {due}" if due else "no due date")
    return "  -  ".join(bits)


def _choose_cards(params, cards, card_labels, card_rows, log):
    """Let the user tick which queued nests to card.

    Returns the filtered ``(cards, card_labels, card_rows)``, or None if the
    user cancelled (the SDK has already flagged the run cancelled).

    Labels are made unique before display: SelectionDialog returns the chosen
    STRINGS, so two identical rows would be indistinguishable coming back. A
    duplicate can only happen if the schedule lists the same batch+nest twice,
    which is a data error rather than something to crash on -- so they are
    numbered instead, and both survive the round trip.
    """
    labels, seen = [], {}
    for card, names, row in zip(cards, card_labels, card_rows):
        label = _card_pick_label(card, names, row)
        if label in seen:
            seen[label] += 1
            label = f"{label}  (#{seen[label]})"
        else:
            seen[label] = 1
        labels.append(label)

    picked = sdk.request_selection(
        params, labels, None,
        window_title="911 Teams Cards",
        header="Select Nests to Card",
        root_label="All queued nests",
        noun="nest",
        prompt_note=("Every nest waiting on the EB 922 Schedule is ticked. "
                     "Untick any you do not want a card for yet - they stay "
                     "queued and are offered again next run."),
        run_button_text="Create Cards",
    )
    if picked is None:
        return None

    keep = set(picked)
    trio = [(c, n, r) for c, n, r, label in
            zip(cards, card_labels, card_rows, labels) if label in keep]
    dropped = len(cards) - len(trio)
    if dropped:
        log(f"Skipping {dropped} nest(s) you unticked - they stay queued on "
            f"the schedule and are offered again next run.")
    return ([c for c, _, _ in trio],
            [n for _, n, _ in trio],
            [r for _, _, r in trio])


def _run_teams_cards(params: dict, progress_callback, cancel_event,
                     qtdr_override: str, lo: int = 0, hi: int = 100) -> bool:
    """The Generate Teams Cards stage. Returns True when the payload posted
    (or dry-ran) cleanly, False when the stage could not run."""
    log = params.get("log", print)
    settings = params.get("settings", {}) or {}

    log(f"\n{'='*50}")
    log("Generate Teams Cards")
    log(f"{'='*50}")

    try:
        template = _load_card_template()
    except (OSError, json.JSONDecodeError) as exc:
        log(f"ERROR: could not read card_template.json: {exc}")
        return False

    def _pct(frac):
        progress_callback(lo + int((hi - lo) * frac))

    rows, problem = _read_schedule_rows(params, template, log, cancel_event)
    if problem:
        log(f"ERROR: {problem}")
        sdk.show_warning(params, "911 Teams Cards - nothing created", problem)
        return False
    if not rows:
        log(f"No rows on '{_SCHED_SHEET}' are DEPT. "
            f"{template.get('schedule_dept', '911')} + STATUS "
            f"'{template.get('schedule_status', 'NEED TEAMS/SETUP')}' - "
            f"nothing to card.")
        _pct(1.0)
        return True
    log(f"Work list     : {len(rows)} nest(s) marked "
        f"'{template.get('schedule_status', 'NEED TEAMS/SETUP')}'.")
    _pct(0.25)

    warnings: list = []
    unlabelled: list = []
    skipped = [r for r in rows if not (r["batch"] and r["nest"])]
    for r in skipped:
        warnings.append(f"Schedule row {r['excel_row']} ('{r['raw_key']}') does "
                        f"not read as 'BATCH NEST' - no card created.")
    rows = [r for r in rows if r["batch"] and r["nest"]]

    # --- No source material listed -> no card (C.D. 2026-08-03) ------------
    # A nest whose NOTES cell is still blank has not been specified yet, so a
    # card for it would carry neither a machine label nor a Program decision.
    # Skip it and say so; it gets a card on a later run, once planning fills
    # the cell in.
    if bool(template.get("require_material_notes", True)):
        no_material = [r for r in rows if not str(r.get("notes") or "").strip()]
        if no_material:
            warnings.append(
                f"No source material in the schedule's NOTES column for "
                f"{len(no_material)} nest(s) - NO card was created for them. "
                f"They will be picked up on a later run once the cell is "
                f"filled in: "
                + ", ".join(f"{r['batch']} {r['nest']}" for r in no_material[:15])
                + (" ..." if len(no_material) > 15 else ""))
        rows = [r for r in rows if str(r.get("notes") or "").strip()]
    if not rows:
        log("Every queued nest was skipped - nothing to card.")
        for w in warnings:
            log(f"  ! {w}")
        if warnings:
            sdk.show_warning(params, "911 Teams Cards - warnings",
                             "\n\n".join(warnings))
        _pct(1.0)
        return True

    # --- Source-material stock codes: one BATCH LIST read per batch ---------
    qtdr_root = _base_qtdr(qtdr_override)
    materials: dict = {}
    for batch in sorted({r["batch"] for r in rows}):
        sdk.raise_if_cancelled(cancel_event)
        mapping, warn = _read_batch_list_materials(qtdr_root, batch, log)
        materials[batch] = mapping
        if warn:
            warnings.append(warn)
    _pct(0.6)

    # --- Build the cards ----------------------------------------------------
    label_map = {_norm_text(name): slot
                 for name, slot in (template.get("label_map") or {}).items()}

    # --- No stock code -> no card ------------------------------------------
    # This is the ONE path that defeats the flow's title-based dedupe: a card
    # created as "BATCH: x - NEST: y" (BATCH LIST unreadable that run) does not
    # match "BATCH: x - NEST: y (code)" later, so the next run creates a SECOND
    # card for the same nest. Skipping is the fix — the nest is re-offered once
    # the BATCH LIST reads cleanly.
    require_code = bool(template.get("require_material_code", True))
    no_code = [r for r in rows
               if not ((materials.get(r["batch"]) or {}).get(r["nest"]) or {}).get("code")]
    if no_code:
        warnings.append(
            f"No BATCH LIST 'Material' code found for {len(no_code)} nest(s), so "
            + ("NO card was created for them (a card without the code would not "
               "match the real one on a later run, and you would end up with two)"
               if require_code else
               "their card titles carry no '(code)'")
            + ": " + ", ".join(f"{r['batch']} {r['nest']}" for r in no_code[:15])
            + (" ..." if len(no_code) > 15 else ""))
        if require_code:
            skip = {(r["batch"], r["nest"]) for r in no_code}
            rows = [r for r in rows if (r["batch"], r["nest"]) not in skip]

    # card_rows tracks each card's ORIGINATING schedule row, so the status
    # write-back below advances exactly the rows that got a card -- not the
    # whole work list, which still holds everything skipped along the way.
    cards, card_labels, card_rows = [], [], []
    for r in rows:
        sdk.raise_if_cancelled(cancel_event)
        material = (materials.get(r["batch"]) or {}).get(r["nest"])
        card, names = _build_card(r, material, template, label_map,
                                  warnings, unlabelled)
        cards.append(card)
        card_labels.append(names)
        card_rows.append(r)

    # --- Drop what this machine has already posted -------------------------
    already = _load_posted_titles(log)
    if already:
        keep = [(c, n, r) for c, n, r in zip(cards, card_labels, card_rows)
                if c["title"] not in already]
        suppressed = len(cards) - len(keep)
        if suppressed:
            log(f"Already carded: {suppressed} nest(s) were posted from this "
                f"machine before and are not being re-sent.")
            log(f"  (Ledger: {_ledger_path()} - delete it to re-offer them.)")
        cards = [c for c, _, _ in keep]
        card_labels = [n for _, n, _ in keep]
        card_rows = [r for _, _, r in keep]

    # --- Pick which of the queued nests to card (C.D. 2026-08-06) ----------
    # "Sometimes I want to make only a couple Teams cards. Ideally I'd be able
    # to select which of the orders in the schedule I want and only make
    # those." Everything is ticked by default, so the common case is still one
    # click, and the list is exactly what would be POSTED -- it runs after the
    # skips and the already-carded ledger, so nothing on screen is a nest that
    # was never going to be carded anyway.
    #
    # Lives here, in the shared engine, so BOTH entry points get it: this app
    # and 911 Setup's optional Teams Cards stage.
    if len(cards) > 0:
        chosen = _choose_cards(params, cards, card_labels, card_rows, log)
        if chosen is None:
            log("\nNest selection cancelled - no cards were created.")
            return False
        cards, card_labels, card_rows = chosen
        if not cards:
            log("\nNo nests selected - nothing to card.")
            _pct(1.0)
            return True

    if not cards:
        log("\nNothing new to card - every queued nest either has no source "
            "material yet or already has its card.")
        if warnings:
            log("\nWarnings:")
            for w in warnings:
                log(f"  ! {w}")
            sdk.show_warning(params, "911 Teams Cards - warnings",
                             "\n\n".join(warnings))
        _pct(1.0)
        return True

    # A card with no difficulty label looks identical to a rated one at a
    # glance, so an uncoloured RATING cell is surfaced the same way the packet
    # stamp surfaces it -- loudly -- rather than passing as a clean run.
    titles_being_posted = {c["title"] for c in cards}
    unrated = [f"{r['batch']} {r['nest']}" for r in rows
               if not r.get("difficulty")
               and any(r["nest"] in t for t in titles_being_posted)]
    if unrated:
        warnings.append(f"No difficulty rating colour on the EB 922 Schedule "
                        f"(CURRENT PIPELINE, column E) for {len(unrated)} "
                        f"nest(s), so their cards carry NO difficulty label: "
                        f"{', '.join(unrated[:15])}"
                        + (" ..." if len(unrated) > 15 else ""))
    if unlabelled:
        warnings.append(f"No SAW CUT / TUBE LASER label could be decided for "
                        f"{len(unlabelled)} nest(s) - those cards were created "
                        f"without a machine label: {'; '.join(unlabelled[:15])}"
                        + (" ..." if len(unlabelled) > 15 else ""))

    payload = {
        "plan": template.get("plan", "SOPO D911 PIPELINE"),
        "bucket": template.get("bucket", "MODELING"),
        # Posted in REVERSE: Planner's "Create a task" top-inserts each new
        # card, so posting the schedule order straight through makes the
        # bucket read bottom-up (same fix as 922 Setup's _order_for_planner).
        "tasks": list(reversed(cards)),
    }

    log(f"\nWill create {len(cards)} card(s) in plan '{payload['plan']}', "
        f"bucket '{payload['bucket']}':")
    for card, names in zip(cards, card_labels):
        bits = ", ".join(names) if names else "no labels"
        due = card["dueDate"][:10] if card.get("dueDate") else "no due date"
        prog = "" if "Program" in card["checklist"] else "  (no Program)"
        log(f"  - {card['title']}   [{bits}]  due {due}{prog}")

    if warnings:
        log("\nWarnings:")
        for w in warnings:
            log(f"  ! {w}")
        sdk.show_warning(params, "911 Teams Cards - warnings",
                         "\n\n".join(warnings))
    _pct(0.8)
    if cancel_event.is_set():
        return False

    # --- Post (or dry-run) --------------------------------------------------
    url = (settings.get("card_webhook_url", "") or "").strip() or DEFAULT_CARD_WEBHOOK_URL
    dry_run = bool(settings.get("card_dry_run", False))
    if not url:
        log("\nNo Teams card webhook URL is configured - running as a DRY RUN.")
        log("Build the flow (docs/TEAMS_CARDS.md, flow #3) and paste its URL "
            "into Settings -> '911 Setup' -> 'Teams Webhook URL'.")
        dry_run = True
    elif dry_run:
        log("\nDry run enabled in Settings -> not posting.")

    if dry_run:
        sdk.write_payload_preview(payload, _CARD_PREVIEW_FILENAME, log)
        _pct(1.0)
        log("\nTeams cards: DONE (dry run - nothing was posted).")
        return True

    log("\nPosting cards to the webhook...")
    ok = sdk.post_webhook(url, payload, log)
    _pct(1.0)
    if ok:
        # Only on a confirmed 2xx: a failed post must stay re-offerable.
        _record_posted_titles([c["title"] for c in cards], log)
        log(f"\nTeams cards: DONE. Requested {len(cards)} card(s) in "
            f"'{payload['bucket']}'.")
        log(f"Check the {payload['plan']} tab in the D922 channel to confirm.")
        # These nests are now carded, so they leave the card queue and join
        # the setup queue. Gated on the confirmed 2xx for the same reason the
        # ledger is: a failed post must leave the row exactly as it was.
        _advance_schedule_status(
            params, template, log,
            [(r["batch"], r["nest"]) for r in card_rows],
            [template.get("schedule_status", "NEED TEAMS/SETUP")],
            template.get("status_after_cards", _STATUS_AFTER_CARDS_DEFAULT),
            cancel_event)
        return True
    log("\nTeams cards: FAILED - see the errors above. No cards were created.")
    return False


# ---------------------------------------------------------------------------
# Main run() function -- TechDeck plugin interface
# ---------------------------------------------------------------------------

def run(params: dict, progress_callback, cancel_event: threading.Event):
    """
    TechDeck plugin entry point.

    No prompts at all: the work list is the EB 922 Schedule's queue, so there
    is nothing to pick and no batch to enter. Tick the app and it runs.
    """
    log = params.get("log", print)
    settings = params.get("settings", {}) or {}
    qtdr_override = (settings.get("qtdr_base_path") or "").strip()

    ok = _run_teams_cards(params, progress_callback, cancel_event,
                          qtdr_override, lo=0, hi=100)
    if not ok and not cancel_event.is_set():
        # The stage reports its own reason (and pops a warning) -- raise so the
        # run is recorded as FAILED rather than a silent green tick.
        raise RuntimeError(
            "Teams cards were not created - see the log above for the reason.")


# ---------------------------------------------------------------------------
# CLI entry point for local testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    def _prog(v):
        print(f"  [Progress] {v}%")

    run({"log": print, "settings": {}}, _prog, threading.Event())
