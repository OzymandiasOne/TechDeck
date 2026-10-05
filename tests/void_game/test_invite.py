import pytest

from techdeck.ui.void_game.invite import is_invitation


@pytest.mark.parametrize("line", [
    "shall we play a game?", "Shall we play a game", "wanna play a game", "lets play",
    "let's play a game", "can we play cards", "play a game with me", "play", "play me",
    "do you want to play a round",
])
def test_invitations(line):
    assert is_invitation(line)


@pytest.mark.parametrize("line", [
    "", "what game", "I play guitar", "the display is broken", "playground", "who are you",
    "games are boring", "/play",
])
def test_not_invitations(line):
    assert not is_invitation(line)
