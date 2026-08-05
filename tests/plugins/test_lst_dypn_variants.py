"""DYPN revision-letter matching (sdk helpers + the two LST organizers).

The fixtures are the REAL Batch 485 rows off 'LST Report - Batch 485.pdf'
(2026-08-05), where the PO said `R6455461-H51-4` and the file on disk said
`R6455461-H51-4A-STEP.lst` — one physical tube reported twice, as "missing"
AND as "needs review". That pairing is what these tests pin down, in both
directions, without loosening the guard that keeps a genuinely different piece
number (`-H12-2` vs `-H12-3`) apart.
"""

import importlib.util
from pathlib import Path

import pytest

from techdeck.core import plugin_sdk as sdk

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"


@pytest.fixture(scope="module")
def lst922():
    spec = importlib.util.spec_from_file_location(
        "lst922_run", PLUGINS / "922_lst_organizer" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── sdk.normalize_dypn ──────────────────────────────────────────────────────

@pytest.mark.parametrize("stem,want", [
    ("R6455461-H51-4A-STEP", "R6455461-H51-4A"),
    ("R6455461-H51-4a-step", "R6455461-H51-4A"),
    ("H7212565-H808-4", "H7212565-H808-4"),
    ("H5222069-H88-4A_P_Tube1", "H5222069-H88-4A"),
    ("H5222069-H88-4A-P-Tube", "H5222069-H88-4A"),
    ("H5222069-H88-4A_4A", "H5222069-H88-4A"),
    ("  h6521267-h4-3  ", "H6521267-H4-3"),
    ("", ""),
    (None, ""),
])
def test_normalize_dypn(stem, want):
    assert sdk.normalize_dypn(stem) == want


@pytest.mark.parametrize("part,want", [
    ("R6455461-H51-4A", ("R6455461-H51", "4", "A")),
    ("R6455461-H51-4", ("R6455461-H51", "4", "")),
    ("H4130401-22M", ("H4130401", "22", "M")),
    ("H5532004-19-2", ("H5532004-19", "2", "")),
    ("H4143481", ("H4143481", "", "")),          # no dash at all
    ("R7211263-H10", ("R7211263", "H10", "")),   # non-numeric last segment
])
def test_split_dypn(part, want):
    assert sdk.split_dypn(part) == want


# ── sdk.match_dypn_variant ──────────────────────────────────────────────────

def test_file_with_a_letter_matches_a_po_line_without_one():
    # The Batch 485 bug: file '-4A', PO '-4'.
    assert sdk.match_dypn_variant(
        "R6455461-H51-4A", ["R6455461-H51-4", "H8651461-H7-4"]
    ) == "R6455461-H51-4"


def test_file_without_a_letter_matches_a_po_line_with_one():
    # The reverse direction the user also asked for.
    assert sdk.match_dypn_variant(
        "R6455461-H51-4", ["R6455461-H51-4A"]) == "R6455461-H51-4A"


def test_the_step_tag_is_ignored_on_both_sides():
    assert sdk.match_dypn_variant(
        "R6455461-H51-4-STEP", ["R6455461-H51-4A"]) == "R6455461-H51-4A"
    assert sdk.match_dypn_variant(
        "R6455461-H51-4A", ["R6455461-H51-4-STEP"]) == "R6455461-H51-4-STEP"


def test_a_different_piece_number_never_matches():
    # Batch 485's third review item: file '-H12-3', PO '-H12-2'. Different
    # piece, must stay flagged.
    assert sdk.match_dypn_variant("H6455572-H12-3", ["H6455572-H12-2"]) is None


def test_a_different_ppn_never_matches():
    assert sdk.match_dypn_variant("R6455461-H51-4A", ["R6455461-H52-4"]) is None


def test_two_open_variants_are_ambiguous_without_a_tiebreak():
    assert sdk.match_dypn_variant(
        "R7653561-H10-3", ["R7653561-H10-3A", "R7653561-H10-3B"]) is None


def test_prefer_breaks_the_tie():
    orders = {"R7653561-H10-3A": "BL392386", "R7653561-H10-3B": "BL999999"}
    assert sdk.match_dypn_variant(
        "R7653561-H10-3", list(orders),
        prefer=lambda d: orders[d] == "BL392386") == "R7653561-H10-3A"


def test_prefer_is_ignored_when_it_would_eliminate_everything():
    # A lone unambiguous candidate still wins even if the order disagrees —
    # `prefer` narrows, it doesn't veto.
    assert sdk.match_dypn_variant(
        "R6455461-H51-4A", ["R6455461-H51-4"],
        prefer=lambda d: False) == "R6455461-H51-4"


def test_an_exact_letter_candidate_wins_over_the_variants():
    assert sdk.match_dypn_variant(
        "R7653561-H10-3B",
        ["R7653561-H10-3", "R7653561-H10-3A", "R7653561-H10-3B"],
    ) == "R7653561-H10-3B"


def test_a_part_with_no_piece_number_never_matches():
    # Nothing to vary -> no guessing.
    assert sdk.match_dypn_variant("R7211263-H10", ["R7211263-H11"]) is None


def test_empty_candidates():
    assert sdk.match_dypn_variant("R6455461-H51-4A", []) is None


# ── 922 LST Organizer: _resolve, replaying Batch 485 ────────────────────────

TUBE = "218003095"          # a STANDARD tube serial (sdk.STANDARD_TUBE_MATERIALS)
TUBE2 = "218019941"


def _resolve(lst922, files, master_map, tmp_path):
    """Run the plugin's resolver over (order folder, filename) pairs."""
    pairs = [(order, tmp_path / name) for order, name in files]
    return lst922._resolve(pairs, master_map, {TUBE: "2.0 X 2.0 X 0.188 NOM",
                                               TUBE2: "2.5 X 2.5 X 0.25 NOM"},
                           tmp_path, log=lambda *a, **k: None)


def test_batch_485_lettered_file_fills_the_unlettered_po_line(lst922, tmp_path):
    master = {"R6455461-H51-4": ("BK499434", TUBE)}
    pulled, expected, _ = _resolve(
        lst922, [("BK499434-R6455461-H51", "R6455461-H51-4A-STEP.lst")],
        master, tmp_path)

    assert len(pulled) == 1
    p = pulled[0]
    assert p.resolved and p.how == "suffix"
    assert p.part == "R6455461-H51-4"       # reported under the PO's spelling
    assert p.serial == TUBE and p.tube == "standard"
    # ...and nothing is left over on either side of the reconciliation.
    covered = {q.part for q in pulled if q.resolved}
    assert not [d for d, v in expected.items()
                if v[2] == "standard" and d not in covered]


def test_the_reverse_direction_unlettered_file_lettered_po_line(lst922, tmp_path):
    master = {"R6455461-H51-4A": ("BK499434", TUBE)}
    pulled, expected, _ = _resolve(
        lst922, [("BK499434-R6455461-H51", "R6455461-H51-4-STEP.lst")],
        master, tmp_path)

    assert pulled[0].how == "suffix"
    assert pulled[0].part == "R6455461-H51-4A"
    assert not [d for d, v in expected.items()
                if v[2] == "standard" and d not in {pulled[0].part}]


def test_a_different_piece_number_still_needs_review(lst922, tmp_path):
    # Batch 485's H6455572-H12-3 file against a PO holding only -H12-2.
    master = {"H6455572-H12-2": ("FK361265", TUBE2)}
    pulled, _expected, _ = _resolve(
        lst922, [("FK361265-H6455572-H12", "H6455572-H12-3.lst")],
        master, tmp_path)

    assert not pulled[0].resolved
    assert "piece number" in pulled[0].reason


def test_an_exact_hit_is_untouched(lst922, tmp_path):
    master = {"H7212565-H808-4": ("X6323599", TUBE)}
    pulled, _expected, _ = _resolve(
        lst922, [("X6323599-H7212565-H808", "H7212565-H808-4-STEP.lst")],
        master, tmp_path)

    assert pulled[0].how == "exact"
    assert pulled[0].part == "H7212565-H808-4"


def test_two_open_variants_are_flagged_not_guessed(lst922, tmp_path):
    # Both -3A and -3B are open on the same order, so a bare '-3' file is a
    # coin flip: it must land in Needs Review, not be assigned.
    master = {"R7653561-H10-3A": ("BL392386", TUBE),
              "R7653561-H10-3B": ("BL392386", TUBE)}
    pulled, _expected, _ = _resolve(
        lst922, [("BL392386-R7653561-H10", "R7653561-H10-3.lst")],
        master, tmp_path)

    assert not pulled[0].resolved
    assert "ambiguous" in pulled[0].reason
    assert pulled[0].folder == lst922.NEEDS_REVIEW_FOLDER


def test_the_order_number_breaks_a_tie_across_orders(lst922, tmp_path):
    master = {"R7653561-H10-3A": ("BL392386", TUBE),
              "R7653561-H10-3B": ("BL999999", TUBE2)}
    pulled, _expected, _ = _resolve(
        lst922, [("BL392386-R7653561-H10", "R7653561-H10-3.lst")],
        master, tmp_path)

    assert pulled[0].how == "suffix"
    assert pulled[0].part == "R7653561-H10-3A"
    assert pulled[0].serial == TUBE


def test_an_already_pulled_tube_is_not_claimed_twice(lst922, tmp_path):
    # -4A arrives exactly; the stray -4 file must NOT then claim the same PO
    # line (it is no longer missing) — it needs a human.
    master = {"R6455461-H51-4A": ("BK499434", TUBE)}
    pulled, _expected, _ = _resolve(
        lst922,
        [("BK499434-R6455461-H51", "R6455461-H51-4A-STEP.lst"),
         ("BK499434-R6455461-H51", "R6455461-H51-4.lst")],
        master, tmp_path)

    resolved = [p for p in pulled if p.resolved]
    review = [p for p in pulled if not p.resolved]
    assert len(resolved) == 1 and resolved[0].how == "exact"
    assert len(review) == 1 and review[0].src.name == "R6455461-H51-4.lst"


def test_a_foreign_part_still_reads_as_foreign(lst922, tmp_path):
    master = {"R6455461-H51-4": ("BK499434", TUBE)}
    pulled, _expected, _ = _resolve(
        lst922, [("BK499434-R6455461-H51", "Z9999999-H1-4.lst")],
        master, tmp_path)

    assert not pulled[0].resolved
    assert "foreign" in pulled[0].reason
