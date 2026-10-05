"""Is this console line an invitation to play him? No Qt, so it is cheap to test.

The chat script answers the words ("Yes. Sit."); this decides whether the
table then opens. Kept deliberately narrow: "play" plus a word about a game,
or the classic line itself.
"""
from __future__ import annotations

import re

_GAME_WORDS = ("game", "games", "cards", "card game", "match", "hand", "round")
_CLASSIC = re.compile(r"\b(shall|should|want|wanna|lets|let us|can) we play\b")


def is_invitation(text: str) -> bool:
    if text.lstrip().startswith("/"):
        return False                      # commands have their own door
    s = re.sub(r"[^a-z0-9 ]+", " ", text.lower().replace("'", ""))
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return False
    if _CLASSIC.search(s):
        return True
    if re.search(r"\bplay\b", s) and any(re.search(rf"\b{w}\b", s) for w in _GAME_WORDS):
        return True
    return bool(re.fullmatch(r"(lets |let us )?play( me| you)?", s))
