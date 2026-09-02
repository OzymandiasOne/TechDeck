"""CLAUDE.md loads into context on EVERY session, so its size is a permanent tax
on every task - and the real cost is attention, not tokens: a rule buried in a
wall of trivia gets followed less reliably than one in a short list.

The file has carried a written budget for a long time. Prose did not hold it. On
2026-09-02 it stood at 41,916 chars against a stated 14k limit - three times over,
with HALF the file being a plugin roster whose detail already lived in
docs/PLUGINS.md. Every other rule in this repo that matters got a build gate
(E12-E15, ship-readiness, version consistency, ref hygiene); the doc budget was
the one that stayed advisory, so it was the one that rotted.

This is that gate. It is deliberately dumb: one number, checked on every build.

It reads CLAUDE.md through the `private_doc` fixture rather than by a fixed
path, because publishing STRIPS CLAUDE.md from the public mirror - reading it
directly turned public main red on the v0.8.7.3 push. See tests/conftest.py.
"""

# Ratchet DOWN as sections are extracted; never up. Raising this number is the
# exact move that produced the 42k file, so treat a failure as "what should
# move to docs/?", not "what should this number be?".
BUDGET = 20_000


def test_claude_md_is_within_budget(private_doc):
    path = private_doc("CLAUDE.md")
    size = len(path.read_text(encoding="utf-8"))
    assert size <= BUDGET, (
        f"CLAUDE.md is {size:,} chars, over the {BUDGET:,} budget by "
        f"{size - BUDGET:,}.\n"
        f"Do NOT raise BUDGET and do NOT trim words. Extract the heaviest "
        f"section into the doc that owns it and leave a one-line pointer - the "
        f"routing table is in CLAUDE.md's 'Doc Governance' section. Detail about "
        f"one plugin goes to docs/PLUGINS.md; the story behind a rule goes to "
        f"LESSONS_LEARNED.md; a procedure goes to the matching skill.")


def test_roster_rows_stay_one_liners(private_doc):
    """The roster is a table of contents, not documentation. It was 21k chars of
    paragraph-length rows - half the file - all of it duplicating docs/PLUGINS.md."""
    text = private_doc("CLAUDE.md").read_text(encoding="utf-8")
    start = text.index("## Installed Plugins")
    end = text.index("## Corporate Environment Notes")
    fat = [l for l in text[start:end].splitlines()
           if l.startswith("| `") and len(l) > 160]
    assert not fat, (
        "roster rows have grown into documentation again:\n  "
        + "\n  ".join(f"{len(l)} chars: {l[:70]}..." for l in fat)
        + "\nPut the detail in that plugin's docs/PLUGINS.md section; the roster "
          "row is one short line saying what the plugin does.")
