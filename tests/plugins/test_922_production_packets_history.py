"""What the sweep of batches 380-502 found, pinned so it cannot come back.

A read-only pass over 122 past batches on 2026-10-30 (~6,500 tubes, 23,292
shop-print PDFs). Every item below is a defect it found in the live code, with
the batches that prove it.
"""
import importlib.util
import pathlib

import pytest

from techdeck.core import plugin_sdk as sdk

PDIR = (pathlib.Path(__file__).resolve().parents[2]
        / "plugins" / "922_production_packets")


def _load(name):
    spec = importlib.util.spec_from_file_location(f"hist_{name}",
                                                  PDIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def mod():
    return _load("run")


@pytest.fixture(scope="module")
def pk():
    return _load("packets")


# ───────────────────────────────────── one size, two serials (426/474/491/…)

def test_the_retired_serial_resolves_to_the_current_one():
    """Carrie, 2026-10-30: 3.0 x 3.0 x 0.25 is 218136140 going forward."""
    assert sdk.canonical_tube_material("218003095") == "218136140"
    assert sdk.canonical_tube_material("218136140") == "218136140"
    # a serial with no alias is returned untouched, whitespace and all
    assert sdk.canonical_tube_material(" 218019941 ") == "218019941"
    assert sdk.canonical_tube_material(None) == ""
    # both numbers stay on the tube lists - the old one is still on paperwork
    for s in ("218003095", "218136140"):
        assert sdk.tube_class(s) is not None


def test_two_serials_of_one_size_make_one_sheet(mod):
    """Keyed on the serial, both groups claimed ONE packet name and the second
    binder overwrote the first - batches 426, 474, 491, 496 and 497."""
    pallet_map = {mod._norm_material("HSS 3.0 X 3.0 X 0.25 NOM"): [
        {"pallet": "1", "idx": "1", "order": 0,
         "text": "HSS 3.0 X 3.0 X 0.25 NOM", "saw": False}]}
    tubes = []
    for part, serial in (("H900000-H1-4", "218003095"),
                         ("H900000-H2-4", "218003095"),
                         ("H900000-H3-4", "218136140")):
        tubes.append({"part": part, "order": "AA100", "serial": serial,
                      "desc": "3.0 X 3.0 X 0.25 NOM", "qty": 1,
                      "length": 10.0, "review": False, "pallet": "1"})

    materials = mod._group_materials(tubes, pallet_map, None, "900",
                                     lambda *_a: None)
    assert len(materials) == 1, "one size on one pallet is one sheet"
    serial, entries = materials[0]
    assert serial == "218136140", "A1 carries the serial stocked today"
    assert len(entries) == 3
    assert entries[0]["serials"] == ["218003095", "218136140"], \
        "both numbers are kept, so the prints wanting a restamp can be named"
    assert entries[0]["packet"] == "1.1"


def test_a_packet_name_is_never_claimed_twice(mod):
    """The property that makes the overwrite impossible: the group key and the
    packet-name key are now the same thing - the SIZE."""
    pallet_map = {}
    for i, text in enumerate(("HSS 3.0 X 3.0 X 0.25 NOM",
                              "HSS 2.5 X 2.5 X 0.25 NOM",
                              "HSS 2.0 X 2.0 X 0.188 NOM")):
        pallet_map[mod._norm_material(text)] = [
            {"pallet": "1", "idx": str(i + 1), "order": i, "text": text,
             "saw": False}]
    tubes = []
    for n, (desc, serial) in enumerate((
            ("3.0 X 3.0 X 0.25 NOM", "218003095"),
            ("3.0 X 3.0 X 0.25 NOM", "218136140"),
            ("2.5 X 2.5 X 0.25 NOM", "218019939"),
            ("2.0 X 2.0 X 0.188 NOM", "218019941"))):
        tubes.append({"part": f"H900000-H{n}-4", "order": "AA100",
                      "serial": serial, "desc": desc, "qty": 1,
                      "length": 10.0 + n, "review": False, "pallet": "1"})

    materials = mod._group_materials(tubes, pallet_map, None, "900",
                                     lambda *_a: None)
    packets = [e[0]["packet"] for _s, e in materials]
    assert len(packets) == len(set(packets)), packets


# ──────────────────────────────────────────────── size wording (391/406/486)

def test_thk_is_noise_like_nom(mod):
    """Batch 391's PO writes `3.0 X 3.0 X 0.50 THK` where the organizer writes
    `... NOM`; keeping THK meant they never matched and it fell to UNKNOWN."""
    assert (mod._norm_material("3.0 X 3.0 X 0.50 THK")
            == mod._norm_material("HSS 3.0 X 3.0 X 0.50 NOM"))


def test_a_round_tube_still_gets_a_size(mod, pk):
    """Batch 486 carries 211031252, `1.66 OD X 0.166 NOM` - a pipe, so two
    numbers, not three. It used to yield no size key at all."""
    assert mod._size_triple("1.66 OD X 0.166 NOM") == (1.66, 0.0, 0.166)
    # and it is NOT confused with any square tube
    assert mod._size_triple("1.66 OD X 0.166 NOM") != \
        mod._size_triple("1.66 X 1.66 X 0.166 NOM")
    # the file name drops the noise words rather than carrying NOM through
    assert pk._size_name("1.66 OD X 0.166 NOM") == "1.66 OD X 0.166"
    # the ordinary cases are untouched
    assert pk._size_name("HSS 4.0 X 4.0 X 0.25 NOM") == "4.0 SQ X 0.25"
    assert pk._size_name("6.0 X 4.0 X 0.50 NOM") == "6.0 X 4.0 X 0.50"


# ─────────────────────────────────── which COPY of a drawing (every batch)

def test_the_order_s_own_copy_beats_the_repeat_copy(pk):
    """46% of drawing names appear more than once in a batch, and the repeat
    copy was picked 49% of the time - a previous job's print."""
    own = pathlib.Path(r"C:\B\X7456885-PART\CAD-AND-SHOP-PRINTS\P\P.pdf")
    rep = pathlib.Path(
        r"C:\B\REPEAT BATCHES\X6429162-PART\CAD-AND-SHOP-PRINTS\P\P.pdf")
    assert sorted((rep, own), key=pk._copy_rank)[0] == own


def test_a_plain_folder_beats_a_numeric_one(pk):
    """`...\\<part>\\7000\\<part>.pdf` carries no readable part number, so
    `classify` calls it 'other' and the tube is reported as having no drawing.
    `7` sorts before a letter, so plain path order picked it every time - that
    is what put 14 of batch 506's tubes outside every binder."""
    plain = pathlib.Path(r"C:\B\ORD\CAD-AND-SHOP-PRINTS\P\P.pdf")
    seven = pathlib.Path(r"C:\B\ORD\CAD-AND-SHOP-PRINTS\P\7000\P.pdf")
    assert sorted((seven, plain), key=pk._copy_rank)[0] == plain
    # and the repeat rule outranks the numeric one
    rep_plain = pathlib.Path(
        r"C:\B\REPEAT BATCHES\ORD\CAD-AND-SHOP-PRINTS\P\P.pdf")
    assert sorted((rep_plain, seven), key=pk._copy_rank)[0] == seven


def test_readable_means_it_names_a_part(pk):
    assert pk._readable([(0, "tube", ["H900000-H1-4"])])
    assert pk._readable([(0, "assembly", ["A", "B"])])
    assert not pk._readable([(0, "other", [])])
    assert not pk._readable([])
    # a mixed document still counts - one usable page is enough
    assert pk._readable([(0, "other", []), (1, "tube", ["H900000-H1-4"])])


# ──────────────────────────────── a wrong PO part number vs a missing print

def test_a_mis_numbered_part_is_told_apart_from_a_missing_print(mod, tmp_path):
    """Batch 507, verified against Carrie's own hand corrections 2026-10-30.

    Her PO Info Drop has two assemblies' tube suffixes swapped: it says
    `H7421762-H55` needs -5 and -8, while the batch carries sheets for -4, -6
    and -10. She corrected it by hand to exactly -4, -6 and -10. So "no
    individual drawing" was covering two different problems, and only one of
    them is somebody's missing print.
    """
    prints = tmp_path / "ORD" / "CAD-AND-SHOP-PRINTS"
    for name in ("H7421762-H55-2", "H7421762-H55-4", "H7421762-H55-6",
                 "H7421762-H55-10", "H5222068-H12-2 PLT"):
        d = prints / name
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.pdf").write_bytes(b"%PDF-1.4 not a real pdf")

    # the PO's own roster: the two mis-numbered tubes, a missing-print one,
    # and -2, which is a PLATE on this assembly and so must NOT be suggested
    # as a tube number even though a sheet for it exists
    all_parts = {"H7421762-H55-5", "H7421762-H55-8", "H7421762-H55-2",
                 "H7212562-H780-12"}
    no_sheet = [
        {"part": "H7421762-H55-5", "desc": "6.0 X 6.0 X 0.50 NOM"},
        {"part": "H7421762-H55-8", "desc": "6.0 X 6.0 X 0.50 NOM"},
        {"part": "H7212562-H780-12", "desc": "5.0 X 5.0 X 0.50 NOM"}]

    mod._diagnose_no_sheet(tmp_path, no_sheet, all_parts, lambda *_a: None)
    by_part = {e["part"]: e for e in no_sheet}

    wrong = by_part["H7421762-H55-5"]
    assert wrong["why"] == "part number looks wrong"
    # it names the three Carrie actually used, and nothing else - in
    # particular not -2, the plate
    assert wrong["suggest"] == ("H7421762-H55-4, H7421762-H55-6, "
                                "H7421762-H55-10")
    assert "H7421762-H55-2" not in wrong["suggest"]
    assert by_part["H7421762-H55-8"]["suggest"] == wrong["suggest"]

    absent = by_part["H7212562-H780-12"]
    assert absent["why"] == "no print for this assembly at all"
    assert absent["suggest"] == "", "nothing to suggest, somebody must look"


def test_a_suffix_the_po_already_claims_is_not_suggested(mod, tmp_path):
    """Only part numbers NO tube on the PO claims are a candidate - otherwise
    every assembly would suggest its own siblings."""
    prints = tmp_path / "ORD" / "CAD-AND-SHOP-PRINTS"
    for name in ("H900000-H1-4", "H900000-H1-5"):
        d = prints / name
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.pdf").write_bytes(b"%PDF-1.4")

    # -4 and -5 are both on the PO; -4 just has no readable sheet
    all_parts = {"H900000-H1-4", "H900000-H1-5"}
    no_sheet = [{"part": "H900000-H1-4", "desc": "2.0 X 2.0 X 0.188 NOM"}]
    mod._diagnose_no_sheet(tmp_path, no_sheet, all_parts, lambda *_a: None)
    assert no_sheet[0]["why"] == "no sheet for this part"
    assert no_sheet[0]["suggest"] == ""
