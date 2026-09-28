"""The Puppet Master's card game - a homebrew in the spirit of Inscryption's first act.

He sits across a board that floats in a phosphor void and plays you with the
things people have feared or prayed to: gods, monsters, dead stars. Sacrifice is
the core verb, damage is weight on a scale, and you can always see what he is
about to play.

Layers (each knows nothing about the ones below it in this list):
    rules.py     the game itself. Pure Python, no Qt, fully unit-tested.
    cards.py     the card and sigil definitions (data).
    art.py       card faces, silhouette portraits, sigil icons (Qt painting).
    render3d.py  our own small software 3D renderer (camera, projection, bloom).
    dialogue.py  his lines: text + an emotion tag -> what his face does.
    window.py    the playable window: input, animation, the turn loop on screen.

ORIGINAL art, names and text only. The game that inspired this is a reference,
never a source: nothing from its assets or fonts belongs in this repo.
"""
