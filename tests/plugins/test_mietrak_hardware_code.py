"""MieTrak Tools - Hardware Code Generator assembly rule.

The tables and the rule are a port of a colleague's standalone
``ASA_Hardware_Code_Generator.exe``; these pin the codes it produced so the
part numbers keep matching MieTrak after the port.
"""

import importlib.util
from pathlib import Path

import pytest

PLUGIN = (Path(__file__).resolve().parents[2]
          / "plugins" / "mietrak_tools" / "run.py")


@pytest.fixture(scope="module")
def mt():
    spec = importlib.util.spec_from_file_location("mietrak_tools_run", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cap_screw_takes_thread_and_length(mt):
    assert mt.build_hardware_code("ZP5", "HHCS", thread_code="H13",
                                  length_code="2") == "HWZP5-HHCS-H13-2"


def test_stud_takes_thread_and_length(mt):
    assert mt.build_hardware_code("304", "STUD", thread_code="M10150",
                                  length_code="40") == "HW304-STUD-M10150-40"


def test_nut_takes_thread_only(mt):
    assert mt.build_hardware_code("188", "HNUT", thread_code="F16",
                                  length_code="2") == "HW188-HNUT-F16"


def test_washer_takes_screw_size_only(mt):
    assert mt.build_hardware_code("G", "FWSH", screw_code="D",
                                  thread_code="H13") == "HWG-FWSH-D"


@pytest.mark.parametrize("kwargs", [
    dict(material_code="", hardware_code="HHCS", thread_code="H13", length_code="2"),
    dict(material_code="ZP5", hardware_code="", thread_code="H13", length_code="2"),
    dict(material_code="ZP5", hardware_code="HHCS", thread_code="", length_code="2"),
    dict(material_code="ZP5", hardware_code="HHCS", thread_code="H13", length_code=""),
    dict(material_code="ZP5", hardware_code="HNUT"),
    dict(material_code="ZP5", hardware_code="LWSH"),
])
def test_blank_required_field_is_an_error(mt, kwargs):
    with pytest.raises(mt.HardwareCodeError):
        mt.build_hardware_code(**kwargs)


def test_fields_needed_by_type(mt):
    assert mt.hardware_fields_needed("FWSH") == ("screw",)
    assert mt.hardware_fields_needed("LWSH") == ("screw",)
    for nut in ("ANUT", "HHNUT", "HNUT"):
        assert mt.hardware_fields_needed(nut) == ("thread",)
    for other in ("BHCS", "FHCS", "HHCS", "SHCS", "STUD"):
        assert mt.hardware_fields_needed(other) == ("thread", "length")


def test_option_tables_have_no_duplicate_labels(mt):
    for name, table in (("material", mt.MATERIAL_OPTIONS),
                        ("hardware", mt.HARDWARE_OPTIONS)):
        labels = [k for k, _ in table]
        assert len(labels) == len(set(labels)), name
    for system in mt.SYSTEMS:
        for name, table in (("thread", mt.THREAD_OPTIONS),
                            ("length", mt.LENGTH_OPTIONS),
                            ("screw", mt.SCREW_OPTIONS)):
            labels = [k for k, _ in table[system]]
            assert len(labels) == len(set(labels)), (name, system)
