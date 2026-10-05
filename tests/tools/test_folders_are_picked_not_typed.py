"""A folder a plugin needs is PICKED, never typed.

Reported 2026-09-23. Six apps still made the user type their way to a folder,
in two shapes:

  * Three asked for the whole path in the console -- "Enter folder path
    containing PDFs" (911 Sketch Extractor, 911 PO PDF Extractor, 911 Remove
    Ticket). A Pilot Program path is ~190 characters before you reach the batch
    folder. Nobody types that correctly, and a mistyped one fails as
    FileNotFoundError naming a folder that plainly exists (MAX_PATH) or as a
    plain "that folder doesn't exist".

  * Three typed the BATCH and then went hunting for its folder (922 Batch
    Repeater, Batch Auditor, 911 Setup). The Repeater was the dangerous one: it
    scanned the 922 root for the first folder whose name contained the typed
    number, so `os.listdir` order decided which batch you got, a batch moved
    into "1 - Completed" was invisible, and a typo quietly CREATED an empty
    "Batch {n}" instead of failing.

The pickers are the single home: `sdk.request_922_batch_folder`,
`sdk.request_911_batch_folder`, `sdk.request_directory`. They cannot typo, they
open in the right place, they are Sentry Drone capable, and the batch pickers
seed the family cache so a queued run of several same-family apps asks once.

This test is the gate. It is deliberately two narrow rules rather than one
clever one -- each is exact for the shape it names, so it fails loudly on a
regression and never on honest code.
"""

import re
from pathlib import Path

import pytest

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"

# Rule 1. A prompt that asks the user to TYPE a path.
#
# A picker's title reads "Select the ..."; only a typed prompt says "Enter".
# Matching on the prompt STRING catches it wherever it is passed -- sdk.
# request_text, a plugin's own get_console_input helper, or console.
# request_input directly, which is how two of the three did it.
_TYPED_PATH_PROMPT_RE = re.compile(
    r'''["'][^"']*\benter\b[^"']*\b(path|folder|directory)\b[^"']*["']''',
    re.IGNORECASE)

# Rule 2. A TYPED batch used to go find that batch's folder.
#
# `request_batch_number` is still right for a batch used as a LABEL (911 Remove
# Ticket stamps it on page 1; Baked Beans names an output file with it), so the
# ban is not on typing a batch -- it is on typing one and then locating a folder
# with it. The folder lookups are the tell, and a plugin that legitimately holds
# one got its batch from a pick or a file, never from this prompt.
_TYPED_BATCH = "request_batch_number"
_FOLDER_LOOKUPS = ("find_922_batch_path", "find_911_batch_folder")


PLUGIN_IDS = sorted(d.name for d in PLUGINS.iterdir() if (d / "run.py").is_file())


# An f-string placeholder holds CODE, not prompt text, and code is full of the
# words we are looking for: Customer DXF Analysis asks "Enter plate thickness -
# {Path(self._queue[0]).name}", which is a number prompt that happens to
# mention Path(). Blank the placeholders before matching so the rule reads only
# what the user is actually shown.
_FSTRING_PLACEHOLDER_RE = re.compile(r"\{[^{}]*\}")


def _code_lines(source: str):
    """(line number, text) for lines that are not a comment.

    The fix left the old behaviour described in comments on purpose -- that is
    the record of why the code looks like it does -- so a comment saying "it
    used to ask the user to enter a folder path" must not trip the gate.
    """
    for n, line in enumerate(source.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        yield n, line


def _prompt_text(line: str) -> str:
    """`line` with f-string placeholders blanked - what the user would read."""
    return _FSTRING_PLACEHOLDER_RE.sub("", line)


@pytest.mark.parametrize("plugin_id", PLUGIN_IDS)
def test_no_plugin_asks_the_user_to_type_a_path(plugin_id):
    run_py = PLUGINS / plugin_id / "run.py"
    hits = [(n, line.strip())
            for n, line in _code_lines(run_py.read_text(encoding="utf-8"))
            if _TYPED_PATH_PROMPT_RE.search(_prompt_text(line))]
    assert not hits, (
        f"{plugin_id} asks the user to TYPE a folder path:\n"
        + "\n".join(f"  {run_py.name}:{n}  {text}" for n, text in hits)
        + "\n\nUse sdk.request_directory (or sdk.request_922_batch_folder / "
          "sdk.request_911_batch_folder for a batch) and title it "
          '"Select the ...". A Pilot Program path is ~190 chars before the '
          "batch folder; typing it is a guess the app then has to survive.")


@pytest.mark.parametrize("plugin_id", PLUGIN_IDS)
def test_no_plugin_types_a_batch_then_hunts_for_its_folder(plugin_id):
    source = (PLUGINS / plugin_id / "run.py").read_text(encoding="utf-8")
    code = "\n".join(line for _, line in _code_lines(source))
    if _TYPED_BATCH not in code:
        return
    found = [name for name in _FOLDER_LOOKUPS if name in code]
    assert not found, (
        f"{plugin_id} types a batch number ({_TYPED_BATCH}) and then looks its "
        f"folder up ({', '.join(found)}).\n\n"
        "Pick the folder instead - sdk.request_922_batch_folder or "
        "sdk.request_911_batch_folder - and read the batch off the folder's "
        "name. Typing the batch is how 922 Batch Repeater could land on the "
        "wrong batch, miss one filed under '1 - Completed', and create an "
        "empty folder from a typo.\n"
        "Typing a batch is still fine where it is only a LABEL (a stamp, an "
        "output file name) - just don't locate a folder with it.")


@pytest.mark.parametrize("line", [
    # the three real prompts, verbatim as they shipped
    'folder_input = get_console_input(params, "Enter folder path containing PDFs")',
    'get_console_input(params, "Enter folder path containing PO packet PDFs")',
    'raw_dir = prompt("Enter path to PDF directory:")',
    # and the shapes a future one could take
    'sdk.request_text(params, "Enter the directory to scan:")',
    'console.request_input("Enter the batch folder")',
])
def test_rule_1_fires_on_the_prompts_that_caused_this(line):
    """A gate that cannot fail is decoration. These are the strings that were
    really in the repo on 2026-09-23."""
    assert _TYPED_PATH_PROMPT_RE.search(_prompt_text(line)), line


@pytest.mark.parametrize("line", [
    # prompts that are NOT a path - the gate must stay quiet on these
    'f"Enter plate thickness - {Path(self._queue[0]).name}"',
    'sdk.request_batch_number(params, "Enter batch number:")',
    'sdk.request_text(params, "Enter nest number:")',
    'sdk.request_directory(params, "Select the 922 batch folder", str(root))',
    'sdk.request_directory(params, "Select the folder with the PDFs", start)',
])
def test_rule_1_stays_quiet_on_honest_prompts(line):
    assert not _TYPED_PATH_PROMPT_RE.search(_prompt_text(line)), line


def test_rule_2_fires_on_the_code_that_caused_this():
    """922 Batch Repeater and Batch Auditor, as they were."""
    was_batch_auditor = (
        'raw_batch = sdk.request_batch_number(params, "Enter batch number:")\n'
        'batch_path = sdk.find_922_batch_path(root, batch_no)\n'
        'batch_folder = sdk.find_911_batch_folder(root, batch)\n')
    code = "\n".join(line for _, line in _code_lines(was_batch_auditor))
    assert _TYPED_BATCH in code
    assert [n for n in _FOLDER_LOOKUPS if n in code] == list(_FOLDER_LOOKUPS)

    # ...and stays quiet on a batch typed only to be used as a LABEL
    remove_ticket = (
        'batch = sdk.normalize_911_batch(\n'
        '    sdk.request_batch_number(params, "Enter the 911 batch number:"))\n'
        'stamp_first_page(pdf, batch)\n')
    code = "\n".join(line for _, line in _code_lines(remove_ticket))
    assert _TYPED_BATCH in code
    assert not [n for n in _FOLDER_LOOKUPS if n in code]


def test_the_pickers_exist_and_are_what_plugins_use():
    """The gate is only worth having while the alternative it names is real."""
    from techdeck.core import plugin_sdk as sdk
    for name in ("request_922_batch_folder", "request_911_batch_folder",
                 "request_directory"):
        assert callable(getattr(sdk, name, None)), f"sdk.{name} is missing"

    # Every app that resolves a batch folder for the user goes through a picker.
    expected = {
        "922_difficulty_stamper": "request_922_batch_folder",
        "922_formingfinder": "request_922_batch_folder",
        "922_kitting": "request_922_batch_folder",
        "922_lst_organizer": "request_922_batch_folder",
        "922_pallet_stamper": "request_922_batch_folder",
        "922_runtime_genie": "request_922_batch_folder",
        "922_batch_repeater": "request_922_batch_folder",
        "911_setup": "request_911_batch_folder",
        "batch_auditor": "request_911_batch_folder",
    }
    for plugin_id, picker in expected.items():
        source = (PLUGINS / plugin_id / "run.py").read_text(encoding="utf-8")
        assert picker in source, f"{plugin_id} no longer uses sdk.{picker}"
