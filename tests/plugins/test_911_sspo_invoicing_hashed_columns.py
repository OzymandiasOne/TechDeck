"""A date too narrow to show prints as ###### in the supplement PDF.

A.T. via the Feedback button, 2026-10-29 (0.8.8): "During invoice
supplement PDF generation, dates in Excel cells that are too narrow to display
properly appear as XXXXXX. The PDF reproduces the same text instead of
displaying the date."

Excel fills a too-narrow DATE or NUMBER cell with hashes, and
`ExportAsFixedFormat` prints exactly what is on screen. `_widen_hashed_columns`
asks Excel which cells it is hashing and widens only those columns.

Driven here through a stand-in for the COM sheet, so the rules are pinned on a
machine with no Excel. The real path was verified against live Excel on
2026-11-02: a supplement whose Ship Date and Amount columns were 4.0 wide
printed `### ###` before and `10/29/2026 $123,456.78` after, and the workbook
on disk kept its original widths.
"""
import datetime
import importlib.util
import pathlib

import pytest

PLUGIN = (pathlib.Path(__file__).resolve().parents[2]
          / "plugins" / "911_sspo_invoicing_prep" / "run.py")


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("inv_hash_test", PLUGIN)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _Column:
    def __init__(self, sheet, index):
        self._sheet, self._index = sheet, index

    @property
    def EntireColumn(self):
        return self

    @property
    def ColumnWidth(self):
        return self._sheet.widths[self._index]

    @ColumnWidth.setter
    def ColumnWidth(self, value):
        self._sheet.widths[self._index] = value

    def AutoFit(self):
        self._sheet.autofits.append(self._index)
        self._sheet.widths[self._index] = self._sheet.autofit_to[self._index]


class _Cell:
    def __init__(self, text):
        self.Text = text


class _Count:
    def __init__(self, n):
        self.Count = n


class _Sheet:
    """The few COM members `_widen_hashed_columns` actually touches.

    `values` is the grid as `UsedRange.Value` hands it over (row-major tuples);
    `shown` is what Excel RENDERS in each cell, which is the only thing that
    says whether a column is too narrow.
    """

    def __init__(self, values, shown, widths, autofit_to):
        self.values = values
        self.shown = shown
        self.widths = dict(widths)
        self.autofit_to = dict(autofit_to)
        self.autofits = []

    # UsedRange is the sheet itself here - every member below is on both
    @property
    def UsedRange(self):
        return self

    @property
    def Rows(self):
        return _Count(len(self.shown))

    @property
    def Columns(self):
        return _ColumnsOf(self)

    @property
    def Value(self):
        """Shaped the way Excel COM really hands a range over.

        This is not pedantry - it is the thing the stub has to get right. A
        single-ROW range comes back FLAT (`(a, b)`, not `((a, b),)`), a
        single-COLUMN range as a tuple of scalars, and a single cell as a bare
        scalar. `_widen_hashed_columns` reshapes all three, and a stub that
        handed over a tidy grid would never exercise that.
        """
        rows, cols = len(self.values), len(self.values[0])
        if rows == 1 and cols == 1:
            return self.values[0][0]
        if rows == 1:
            return tuple(self.values[0])
        if cols == 1:
            return tuple(row[0] for row in self.values)
        return self.values

    def Cells(self, row, col):
        return _Cell(self.shown[row - 1][col - 1])


class _ColumnsOf:
    def __init__(self, sheet):
        self._sheet = sheet

    @property
    def Count(self):
        return len(self._sheet.shown[0]) if self._sheet.shown else 0

    def __call__(self, index):
        return _Column(self._sheet, index)


def _sheet(values, shown, widths, autofit_to):
    return _Sheet(values, shown, widths, autofit_to)


DATE = datetime.datetime(2026, 10, 29)


def test_a_hashed_date_column_is_widened(mod):
    sheet = _sheet(
        values=((DATE, "H4524555-12M"), (DATE, "H4524555-12M")),
        shown=(("######", "H4524555-12M"), ("######", "H4524555-12M")),
        widths={1: 4.0, 2: 20.0},
        autofit_to={1: 11.5, 2: 12.0})
    assert mod._SupplementPdfExporter._widen_hashed_columns(
        sheet, lambda *_a: None) == 1
    assert sheet.autofits == [1], "only the hashed column is touched"
    assert sheet.widths[1] == 11.5
    assert sheet.widths[2] == 20.0, "a roomy column is left exactly as it was"


def test_a_column_is_never_made_narrower(mod):
    """Invoicing tuned INV_COL_WIDTHS; AutoFit can SHRINK, and a quietly
    re-laid-out supplement would be a worse bug than the hashes."""
    sheet = _sheet(
        values=((DATE, 1234.5),),
        shown=(("######", "######"),),
        widths={1: 30.0, 2: 4.0},
        autofit_to={1: 11.5, 2: 12.0})     # column 1 would SHRINK to 11.5
    mod._SupplementPdfExporter._widen_hashed_columns(sheet, lambda *_a: None)
    assert sheet.widths[1] == 30.0, "AutoFit shrank it and we put it back"
    assert sheet.widths[2] == 12.0, "the genuinely narrow one still grew"


def test_text_is_never_treated_as_hashed(mod):
    """Text overflows or wraps - it does not hash. A cell whose VALUE is a
    string of hashes is somebody's data, not a width problem."""
    sheet = _sheet(
        values=(("######", "NOTE"),),
        shown=(("######", "NOTE"),),
        widths={1: 4.0, 2: 9.0},
        autofit_to={1: 11.5, 2: 12.0})
    assert mod._SupplementPdfExporter._widen_hashed_columns(
        sheet, lambda *_a: None) == 0
    assert sheet.autofits == []


def test_a_tidy_sheet_is_left_completely_alone(mod):
    sheet = _sheet(
        values=((DATE, 1234.5),),
        shown=(("10/29/2026", "$1,234.50"),),
        widths={1: 13.0, 2: 14.0},
        autofit_to={1: 11.5, 2: 12.0})
    assert mod._SupplementPdfExporter._widen_hashed_columns(
        sheet, lambda *_a: None) == 0
    assert sheet.widths == {1: 13.0, 2: 14.0}


def test_a_partly_hashed_column_still_counts_once(mod):
    """One hit settles the column - no need to read every row below it."""
    sheet = _sheet(
        values=((DATE,), (DATE,), (DATE,)),
        shown=(("10/29/2026",), ("######",), ("######",)),
        widths={1: 9.0},
        autofit_to={1: 13.0})
    assert mod._SupplementPdfExporter._widen_hashed_columns(
        sheet, lambda *_a: None) == 1
    assert sheet.autofits == [1]


def test_a_sheet_that_will_not_answer_is_survived(mod):
    """Best effort: a COM member that raises must not lose the PDF."""
    class _Broken:
        @property
        def UsedRange(self):
            raise RuntimeError("RPC server unavailable")

    said = []
    assert mod._SupplementPdfExporter._widen_hashed_columns(
        _Broken(), said.append) == 0
    assert any("couldn't measure" in m for m in said), said
