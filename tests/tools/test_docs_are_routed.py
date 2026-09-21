"""Every doc must be reachable from something that LOADS.

The knowledge here sits on three shelves: what loads every session (CLAUDE.md),
what loads itself when a task matches (the skills), and what is only read when
something points to it (docs/, LESSONS_LEARNED.md). That third shelf is ~96% of
everything written down - and a doc on it that NOTHING points to is a doc that
never gets used, however good it is.

Found 2026-09-18: three docs were orphans. One was 45,000 characters of game
event design reachable only from inside another doc. Nobody decided that; docs
just get written, and the pointer is the step that gets forgotten. It is
mechanically checkable, so it is a gate (Fix Protocol step 3).

The rule: every top-level `docs/*.md`, plus LESSONS_LEARNED.md, is named by
CLAUDE.md or by at least one SKILL.md. Being named only from another doc does
not count - that doc has to be open already.

All of these paths are stripped from the public mirror, so they are resolved
through `private_doc` (skips there; see tests/conftest.py).
"""


def test_every_doc_is_named_by_the_guide_or_a_skill(private_doc):
    routers = {"CLAUDE.md": private_doc("CLAUDE.md").read_text(encoding="utf-8")}
    for skill in sorted(private_doc(".claude/skills").glob("*/SKILL.md")):
        routers[f"skill {skill.parent.name}"] = skill.read_text(encoding="utf-8")

    docs = sorted(private_doc("docs").glob("*.md")) + [private_doc("LESSONS_LEARNED.md")]
    orphans = [d.name for d in docs
               if not any(d.name in text for text in routers.values())]
    assert not orphans, (
        "these docs are not named by CLAUDE.md or by any skill, so nothing ever "
        "loads them:\n  " + "\n  ".join(orphans)
        + "\nAdd a one-line pointer in the skill that owns the topic (preferred: "
          "skills load themselves), or a Reference Docs Map row in CLAUDE.md if "
          "no skill fits. Do not delete the doc to make this pass.")
